import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, File, UploadFile, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import shutil
import jwt
import datetime
import uuid
import time
import requests
import uuid
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from database import engine, Base, get_db
import models
from graph import compile_workflow, run_workflow
from meta_agent import run_agent_turn
import discord_bot
import scheduler

JWT_SECRET = os.environ.get("JWT_SECRET", "super-secret-key")
JWT_ALGORITHM = "HS256"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# Create DB tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Business Automation API")

# Ensure uploads directory exists
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    with open("error_log.txt", "a") as f:
        f.write(f"{datetime.datetime.now()} - {str(request.url)} - {str(exc)}\n")
        traceback.print_exc(file=f)
    return JSONResponse(status_code=500, content={"message": "Internal Server Error", "details": str(exc)})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    with open("error_log.txt", "a") as f:
        f.write(f"{datetime.datetime.now()} - {str(request.url)} - Validation Error: {exc.errors()}\n")
        f.write(f"Body: {exc.body}\n")
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "body": exc.body})

# Setup CORS to allow requests from the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], # Vite default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    db = next(get_db())
    try:
        discord_bot.boot_existing_discord_bots(db)
    except Exception as e:
        print(f"Failed to boot discord bots: {e}")
    try:
        scheduler.start_scheduler()
        scheduler.sync_all_schedules(db)
    except Exception as e:
        print(f"Failed to boot scheduler: {e}")
    finally:
        db.close()

class FlowPayload(BaseModel):
    project_id: Optional[int] = None
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

class DeployPayload(BaseModel):
    mode: str
    discord_bot_token: str = None

class ExecutePayload(BaseModel):
    inputs: Dict[str, Any]

class ChatPayload(BaseModel):
    project_id: str
    message: str
    graph_data: Dict[str, Any]

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Receives a file from the frontend and saves it to the uploads/ directory.
    Returns the file path.
    """
    file_path = os.path.join("uploads", file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"status": "success", "file_path": file_path, "filename": file.filename}

security = HTTPBearer(auto_error=False)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    if not credentials:
        return None
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            return None
        return db.query(models.User).filter(models.User.id == user_id).first()
    except jwt.PyJWTError:
        return None

def get_current_user_required(user: models.User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user

class AuthPayload(BaseModel):
    token: str

EXCHANGE_RATE_CACHE = {
    "rate": 1400.0,
    "last_fetched": 0
}

@app.get("/api/exchange-rate")
def get_exchange_rate():
    current_time = time.time()
    # Cache for 12 hours (43200 seconds)
    if current_time - EXCHANGE_RATE_CACHE["last_fetched"] > 43200:
        try:
            res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
            if res.status_code == 200:
                data = res.json()
                rate = data.get("rates", {}).get("KRW")
                if rate:
                    EXCHANGE_RATE_CACHE["rate"] = float(rate)
                    EXCHANGE_RATE_CACHE["last_fetched"] = current_time
        except Exception as e:
            print(f"Failed to fetch exchange rate: {e}")
            
    return {"status": "success", "krw_rate": EXCHANGE_RATE_CACHE["rate"]}

@app.post("/api/auth/google")
def auth_google(payload: AuthPayload, db: Session = Depends(get_db)):
    try:
        idinfo = id_token.verify_oauth2_token(
            payload.token, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID, 
            clock_skew_in_seconds=600
        )
        google_id = idinfo['sub']
        email = idinfo.get('email')
        name = idinfo.get('name')
        picture = idinfo.get('picture')

        user = db.query(models.User).filter(models.User.google_id == google_id).first()
        if not user:
            user = models.User(google_id=google_id, email=email, name=name, picture=picture)
            db.add(user)
            db.commit()
            db.refresh(user)
        
        access_token = jwt.encode(
            {"user_id": user.id, "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)},
            JWT_SECRET,
            algorithm=JWT_ALGORITHM
        )
        return {"access_token": access_token, "user": {"id": user.id, "name": user.name, "email": user.email, "picture": user.picture}}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google token: {str(e)}")

@app.delete("/api/users/me")
async def delete_user_account(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    # 1. Anonymize execution logs
    db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.user_id == user.id).update({models.FlowExecutionLog.user_id: None})
    
    # 2. Delete bot logs and stop bots for their projects
    projects = db.query(models.Project).filter(models.Project.user_id == user.id).all()
    project_ids = [p.id for p in projects]
    if project_ids:
        # Stop any running discord bots
        for pid in project_ids:
            discord_bot.stop_discord_bot(pid)
            
        db.query(models.BotLog).filter(models.BotLog.project_id.in_(project_ids)).delete(synchronize_session=False)
        # 3. Delete projects
        db.query(models.Project).filter(models.Project.user_id == user.id).delete(synchronize_session=False)
        
    # 4. Delete user
    db.delete(user)
    db.commit()
    return {"status": "success", "message": "Account deleted"}

class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    graph_data: Dict[str, Any]
    visibility: str = "private"

@app.get("/api/projects/public")
def get_public_projects(db: Session = Depends(get_db)):
    projects = db.query(models.Project).filter(models.Project.visibility == 'public').all()
    return [{"id": p.id, "title": p.title, "description": p.description, "owner": p.owner.name if p.owner else "Unknown", "updated_at": p.updated_at, "share_token": p.share_token} for p in projects]

@app.get("/api/projects/my")
def get_my_projects(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    projects = db.query(models.Project).filter(models.Project.user_id == user.id).all()
    return [{"id": p.id, "title": p.title, "description": p.description, "visibility": p.visibility, "updated_at": p.updated_at, "share_token": p.share_token} for p in projects]

@app.post("/api/projects")
def create_project(payload: ProjectCreate, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = models.Project(
        user_id=user.id,
        title=payload.title,
        description=payload.description,
        graph_data=payload.graph_data,
        visibility=payload.visibility
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"status": "success", "id": project.id}

@app.get("/api/projects/{project_id}")
def get_project(project_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if project.visibility == 'private' and (not user or project.user_id != user.id):
        raise HTTPException(status_code=403, detail="Not authorized to view this project")
    elif project.visibility == 'friends':
        if not user or (project.user_id != user.id and not db.query(models.Friendship).filter(models.Friendship.user_id == project.user_id, models.Friendship.friend_id == user.id).first()):
            raise HTTPException(status_code=403, detail="Not authorized to view this project")

    return {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "graph_data": project.graph_data,
        "visibility": project.visibility,
        "deploy_mode": project.deploy_mode,
        "owner_id": project.user_id,
        "owner_name": project.owner.name if project.owner else "Unknown"
    }

@app.get("/api/webhooks")
def get_my_webhooks(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    projects = db.query(models.Project).filter(models.Project.user_id == user.id).all()
    webhooks = []
    
    for p in projects:
        graph_data = p.graph_data or {}
        nodes = graph_data.get('nodes', []) if isinstance(graph_data, dict) else []
        for n in nodes:
            if isinstance(n, dict) and n.get('type') == 'webhookNode':
                # Get last run time
                last_run = db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.project_id == p.id).order_by(models.FlowExecutionLog.execution_time.desc()).first()
                last_triggered = "최근 실행 기록 없음"
                if last_run:
                    diff = datetime.datetime.utcnow() - last_run.execution_time
                    if diff.days > 0:
                        last_triggered = f"{diff.days}일 전"
                    elif diff.seconds >= 3600:
                        last_triggered = f"{diff.seconds // 3600}시간 전"
                    elif diff.seconds >= 60:
                        last_triggered = f"{diff.seconds // 60}분 전"
                    else:
                        last_triggered = "방금 전"
                node_url = n.get('data', {}).get('webhookUrl', '').strip()
                if not node_url:
                    node_url = f"/webhook/{p.id}"
                elif not node_url.startswith('/webhook/'):
                    if node_url.startswith('/'):
                        node_url = f"/webhook{node_url}"
                    else:
                        node_url = f"/webhook/{node_url}"
                    
                webhooks.append({
                    "id": f"wh-{p.id}-{n.get('id')}",
                    "projectId": p.id,
                    "title": p.title,
                    "url": f"http://localhost:8000{node_url}",
                    "status": "Active" if p.graph_data.get("is_live", False) else "Stopped",
                    "lastTriggered": last_triggered
                })
                break
                
    return webhooks

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this project")
    

    try:
        if scheduler.scheduler.get_job(f"project_{project_id}"):
            scheduler.scheduler.remove_job(f"project_{project_id}")
    except Exception as e:
        print(f"Failed to remove schedule: {e}")

    # Stop bot if running
    discord_bot.stop_discord_bot(project_id)
    
    # Delete bot logs to avoid IntegrityError
    db.query(models.BotLog).filter(models.BotLog.project_id == project_id).delete(synchronize_session=False)

    db.delete(project)
    db.commit()
    return {"status": "success"}

@app.put("/api/projects/{project_id}")
def update_project(project_id: int, payload: ProjectCreate, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this project")
    
    project.title = payload.title
    project.description = payload.description

    old_graph_data = project.graph_data or {}
    new_graph_data = payload.graph_data or {}
    if isinstance(old_graph_data, dict) and isinstance(new_graph_data, dict):
        if "discord_bot_token" in old_graph_data:
            new_graph_data["discord_bot_token"] = old_graph_data["discord_bot_token"]
            
    project.graph_data = new_graph_data
    flag_modified(project, "graph_data")
    project.visibility = payload.visibility

    db.commit()
    
    try:
        if isinstance(new_graph_data, dict) and new_graph_data.get("is_live") is True:
            scheduler.sync_project_schedule(project_id, project)
        else:
            scheduler.sync_project_schedule(project_id, project) # sync_project_schedule will remove if not live
    except Exception as e:
        print(f"Failed to sync schedule: {e}")
        
    return {"status": "success"}

@app.post("/api/projects/{project_id}/live")
def toggle_project_live(project_id: int, payload: dict, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    is_live = payload.get("is_live", False)
    graph_data = dict(project.graph_data) if isinstance(project.graph_data, dict) else {}
    graph_data["is_live"] = is_live
    project.graph_data = graph_data
    flag_modified(project, "graph_data")
    db.commit()
    
    # Sync triggers based on the new state
    try:
        scheduler.sync_project_schedule(project_id, project)
    except Exception as e:
        print(f"Failed to sync schedule on live toggle: {e}")
        
    # If discord node is present, we might want to start/stop the bot
    has_discord = any(n.get('type') == 'discordNode' for n in graph_data.get('nodes', []))
    if has_discord:
        token = graph_data.get("discord_bot_token")
        if is_live and token:
            discord_bot.start_discord_bot(project_id, token)
        else:
            discord_bot.stop_discord_bot(project_id)
            
    return {"status": "success", "is_live": is_live}

@app.post("/api/projects/{project_id}/deploy")
def deploy_project(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    if not project.share_token:
        project.share_token = str(uuid.uuid4())
        db.commit()
    return {"status": "success", "share_token": project.share_token}

@app.get("/api/apps/{share_token}")
def get_app_info(share_token: str, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.share_token == share_token).first()
    if not project:
        raise HTTPException(status_code=404, detail="App not found")
    
    return {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "visibility": project.visibility,
        "owner_name": project.owner.name if project.owner else "Unknown",
        "graph_data": project.graph_data
    }

class AppExecutePayload(BaseModel):
    inputs: dict = {}

@app.post("/api/apps/{share_token}/execute")
def execute_app(share_token: str, request: Request, payload: AppExecutePayload = None, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.share_token == share_token).first()
    if not project:
        raise HTTPException(status_code=404, detail="App not found")
    
    user = None
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(" ")[1]
        try:
            payload_jwt = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user = db.query(models.User).filter(models.User.id == payload_jwt.get("user_id")).first()
        except:
            pass
            
    if project.visibility == 'private' and (not user or project.user_id != user.id):
        raise HTTPException(status_code=403, detail="Authentication required for private app")
    elif project.visibility == 'friends':
        if not user or (project.user_id != user.id and not db.query(models.Friendship).filter(models.Friendship.user_id == project.user_id, models.Friendship.friend_id == user.id).first()):
            raise HTTPException(status_code=403, detail="Friends-only access required")

    owner = db.query(models.User).filter(models.User.id == project.user_id).first()
    if owner and owner.token_balance <= 0:
        raise HTTPException(status_code=403, detail="앱 소유자의 토큰이 모두 소진되어 앱을 실행할 수 없습니다.")

    nodes = project.graph_data.get('nodes', [])
    edges = project.graph_data.get('edges', [])
    
    try:
        kwargs = payload.inputs if payload and payload.inputs else {}
        result_text, tokens, logs = run_workflow(nodes, edges, db=db, session_id='app_runner', project_id=project.id, **kwargs)
        
        total_tokens = tokens.get('total_tokens', 0) if tokens else 0
        if owner and total_tokens > 0:
            owner.token_balance -= total_tokens

        db_log = models.FlowExecutionLog(
            user_id=user.id if user else None,
            project_id=project.id,
            payload="App Runner Execution",
            result=result_text,
            total_tokens=total_tokens,
            token_usage_details=tokens,
            status="success"
        )
        db.add(db_log)
        db.flush()
        for step in logs:
            node_log = models.NodeExecutionLog(
                flow_execution_id=db_log.id,
                node_id=step.get('node_id'),
                node_type=step.get('node_type'),
                start_time=step.get('start_time'),
                end_time=step.get('end_time'),
                status=step.get('status'),
                result_data=str(step.get('result_data')) if step.get('result_data') else None,
                error_message=step.get('error_message')
            )
            db.add(node_log)
        db.commit()
        return {"status": "success", "result": result_text}
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/estimate")
def estimate_tokens(payload: FlowPayload):
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
    except Exception:
        return {"status": "error", "message": "Tokenizer not available"}
        
    total_estimated_tokens = 0
    total_max_tokens = 0
    node_details = {}
    
    # Simple mapping of model to max output tokens
    max_output_map = {
        'gemini-1.5-flash': 8192,
        'gemini-1.5-pro': 8192,
        'gpt-4o-mini': 16384,
        'gpt-4o': 4096,
        'claude-3-haiku-20240307': 4096,
        'claude-3-5-sonnet-20240620': 4096
    }
    
    for node in payload.nodes:
        if node.get('type') in ['llmNode', 'promptNode']:
            text = node.get('data', {}).get('systemPrompt', '') + " " + node.get('data', {}).get('userPrompt', '')
            tokens = len(encoding.encode(text)) if text else 0
            
            max_out = 0
            if node.get('type') == 'llmNode':
                model = node.get('data', {}).get('model', 'gemini-1.5-flash')
                max_out = max_output_map.get(model, 4096)
                
            node_details[node['id']] = {
                'min_tokens': tokens,
                'max_tokens': tokens + max_out
            }
            total_estimated_tokens += tokens
            total_max_tokens += tokens + max_out
            
    return {
        "status": "success",
        "total_estimated_tokens": total_estimated_tokens,
        "total_max_tokens": total_max_tokens,
        "node_details": node_details
    }

@app.post("/api/execute")
def execute_flow(payload: FlowPayload, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """
    Receives graph data from frontend, runs LangGraph logic,
    saves execution to DB, and returns the result.
    """
    if user and user.token_balance <= 0:
        raise HTTPException(status_code=403, detail="토큰을 모두 소진하여 실행할 수 없습니다. 토큰을 충전해 주세요.")

    import json
    with open("payload_debug.json", "w", encoding="utf-8") as f:
        json.dump(payload.dict(), f, ensure_ascii=False, indent=2)
        
    # 1. Run LangGraph
    try:
        result_text, tokens, logs = run_workflow(payload.nodes, payload.edges, db=db, session_id='editor', project_id=payload.project_id)
        
        # Check if run_workflow returned an error string
        if "► Flow 1 Error:" in result_text or "Error calling model" in result_text:
            if "RESOURCE_EXHAUSTED" in result_text or "429" in result_text:
                result_text = "❌ AI API 크레딧이 소진되었습니다. AI Studio 또는 OpenAI에서 크레딧을 충전해 주세요."
            elif "AuthenticationError" in result_text or "401" in result_text:
                result_text = "❌ AI API 키가 유효하지 않습니다. .env 파일의 API 키를 확인해 주세요."
            elif "Network" in result_text or "Connection" in result_text:
                result_text = f"❌ 네트워크 오류가 발생했습니다."
            else:
                result_text = f"❌ 워크플로우 실행 중 오류가 발생했습니다: {result_text}"
    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = str(e)
        tokens = {}
        logs = []
        # API 크레딧 소진 오류 안내
        if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
            result_text = "❌ AI API 크레딧이 소진되었습니다. AI Studio 또는 OpenAI에서 크레딧을 충전해 주세요."
        elif "AuthenticationError" in error_msg or "401" in error_msg:
            result_text = "❌ AI API 키가 유효하지 않습니다. .env 파일의 API 키를 확인해 주세요."
        elif "Network" in error_msg or "Connection" in error_msg:
            result_text = f"❌ 네트워크 오류가 발생했습니다: {error_msg}"
        else:
            result_text = f"❌ 워크플로우 실행 중 오류가 발생했습니다: {error_msg}"
    
    import json
    # 2. Save log to PostgreSQL (or SQLite fallback)
    try:
        flow_status = "error" if "❌" in result_text or "Error" in result_text else "success"
        
        total_tokens = tokens.get('total_tokens', 0) if isinstance(tokens, dict) else 0
        if user and total_tokens > 0:
            user.token_balance -= total_tokens

        db_log = models.FlowExecutionLog(
            user_id=user.id if user else None,
            project_id=payload.project_id,
            payload=json.dumps(payload.dict()),
            result=result_text,
            total_tokens=total_tokens,
            token_usage_details=tokens if isinstance(tokens, dict) else None,
            status=flow_status,
            error_message=result_text if flow_status == "error" else None
        )
        db.add(db_log)
        db.flush() # To get db_log.id
        
        for step in logs:
            start_dt = datetime.datetime.fromisoformat(step['start_time']) if step.get('start_time') else None
            end_dt = datetime.datetime.fromisoformat(step['end_time']) if step.get('end_time') else None
            node_log = models.NodeExecutionLog(
                flow_execution_id=db_log.id,
                node_id=step.get('node_id'),
                node_type=step.get('node_type'),
                start_time=start_dt,
                end_time=end_dt,
                status=step.get('status', 'success'),
                result_data=step.get('result_data'),
                error_message=step.get('error_message')
            )
            db.add(node_log)
            
        db.commit()
        db.refresh(db_log)
    except Exception as e:
        print(f"Failed to save log to DB: {e}")
        db.rollback()

    # 3. Return response to frontend
    return {"status": "success", "result": result_text, "token_usage": tokens, "logs": logs}

@app.get("/api/projects/{project_id}/runs")
def get_project_runs(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user_required)):
    # Verify project access
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if project.visibility == 'private' and project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this project")
    elif project.visibility == 'friends':
        if project.user_id != user.id and not db.query(models.Friendship).filter(models.Friendship.user_id == project.user_id, models.Friendship.friend_id == user.id).first():
            raise HTTPException(status_code=403, detail="Not authorized to view this project")
        
    runs = db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.project_id == project_id).order_by(models.FlowExecutionLog.execution_time.desc()).limit(100).all()
    
    return [
        {
            "id": run.id,
            "execution_time": run.execution_time,
            "status": run.status,
            "total_tokens": run.total_tokens,
            "result_summary": run.result[:100] + "..." if run.result and len(run.result) > 100 else run.result
        } for run in runs
    ]

@app.get("/api/runs/{run_id}")
def get_run_details(run_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user_required)):
    run = db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    project = db.query(models.Project).filter(models.Project.id == run.project_id).first()
    if project:
        if project.visibility == 'private' and project.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not authorized to view this run")
        elif project.visibility == 'friends':
            if project.user_id != user.id and not db.query(models.Friendship).filter(models.Friendship.user_id == project.user_id, models.Friendship.friend_id == user.id).first():
                raise HTTPException(status_code=403, detail="Not authorized to view this run")
        
    steps = db.query(models.NodeExecutionLog).filter(models.NodeExecutionLog.flow_execution_id == run.id).order_by(models.NodeExecutionLog.id).all()
    
    return {
        "run": {
            "id": run.id,
            "project_id": run.project_id,
            "execution_time": run.execution_time,
            "status": run.status,
            "result": run.result,
            "total_tokens": run.total_tokens,
            "error_message": run.error_message
        },
        "steps": [
            {
                "id": step.id,
                "node_id": step.node_id,
                "node_type": step.node_type,
                "start_time": step.start_time,
                "end_time": step.end_time,
                "status": step.status,
                "result_data": step.result_data,
                "error_message": step.error_message
            } for step in steps
        ]
    }

@app.post("/api/compile")
def compile_flow(payload: FlowPayload):
    """
    Parses graph data from frontend and returns raw Python code representation.
    """
    compiled_code = compile_workflow(payload.nodes, payload.edges)
    return {"status": "success", "code": compiled_code}

@app.post("/api/chat")
def chat_with_agent(payload: ChatPayload, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    자연어로 flow(graph_data)를 생성/수정하는 메타 에이전트 챗봇.
    project_id를 LangGraph thread_id로 써서 같은 프로젝트 안에서는 대화 맥락이 이어진다.
    graph_data는 여기서 저장하지 않는다 — 프론트가 매번 현재 캔버스 상태를 보내고,
    돌아온 graph_data를 캔버스에 반영한 뒤 원할 때 /api/projects로 별도 저장한다.
    """
    if user and user.token_balance <= 0:
        raise HTTPException(status_code=403, detail="토큰을 모두 소진하여 AI를 사용할 수 없습니다.")

    try:
        reply, graph_data = run_agent_turn(
            payload.graph_data,
            payload.message,
            thread_id=f"project-{payload.project_id}",
        )
        
        # ChatSession 저장 로직
        if user:
            session = db.query(models.ChatSession).filter(
                models.ChatSession.user_id == user.id,
                models.ChatSession.project_id == str(payload.project_id)
            ).first()
            
            if not session:
                title = payload.message[:30] + "..." if len(payload.message) > 30 else payload.message
                session = models.ChatSession(
                    user_id=user.id,
                    project_id=str(payload.project_id),
                    title=title,
                    messages=[]
                )
                db.add(session)
                db.commit()
                db.refresh(session)
            
            # messages는 리스트인데, SQLAlchemy JSON 필드는 기본적으로 리스트를 반환할 수 있으나 할당 시 새 객체로 줘야 변경감지가 됨
            msgs = list(session.messages) if session.messages else []
            msgs.append({"role": "user", "content": payload.message})
            msgs.append({"role": "ai", "content": reply})
            session.messages = msgs
            db.commit()

        return {"status": "success", "reply": reply, "graph_data": graph_data}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"챗봇 처리 중 오류: {str(e)}")

@app.get("/api/chat/sessions")
def get_chat_sessions(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    sessions = db.query(models.ChatSession).filter(models.ChatSession.user_id == user.id).order_by(models.ChatSession.updated_at.desc()).all()
    
    result = []
    for s in sessions:
        # Check if project exists if project_id is numeric
        is_existing_project = False
        if s.project_id and s.project_id.isdigit():
            proj = db.query(models.Project).filter(models.Project.id == int(s.project_id)).first()
            if proj:
                is_existing_project = True

        result.append({
            "id": s.id,
            "project_id": s.project_id,
            "title": s.title,
            "messages": s.messages,
            "updated_at": s.updated_at.isoformat(),
            "is_existing_project": is_existing_project
        })
    return {"status": "success", "sessions": result}

@app.get("/api/chat/session/{project_id}")
def get_chat_session(project_id: str, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    session = db.query(models.ChatSession).filter(
        models.ChatSession.user_id == user.id,
        models.ChatSession.project_id == project_id
    ).first()
    
    if not session:
        return {"status": "success", "session": None}
        
    return {
        "status": "success", 
        "session": {
            "id": session.id,
            "project_id": session.project_id,
            "title": session.title,
            "messages": session.messages,
            "updated_at": session.updated_at.isoformat()
        }
    }

@app.post("/api/deploy/{project_id}")
async def deploy_project(project_id: int, payload: DeployPayload, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project.deploy_mode = payload.mode
    
    # 디스코드 봇 배포 로직
    if payload.mode == "discord":
        if payload.discord_bot_token:
            # 기존 딕셔너리를 복사하여 업데이트 (SQLAlchemy JSON 업데이트 감지)
            new_data = dict(project.graph_data)
            new_data["discord_bot_token"] = payload.discord_bot_token
            project.graph_data = new_data
            flag_modified(project, "graph_data")
            db.commit()
            
            # 봇 시작
            discord_bot.start_discord_bot(project.id, payload.discord_bot_token)
    else:
        # 다른 모드로 변경 시 디스코드 봇 정지
        discord_bot.stop_discord_bot(project.id)

    db.commit()

    if payload.mode in ["fastapi", "mcp"]:
        compiled_code = compile_workflow(project.graph_data.get('nodes', []), project.graph_data.get('edges', []))
        if payload.mode == "fastapi":
            # Wrap in FastAPI boilerplate
            code = f"""from fastapi import FastAPI
import uvicorn

app = FastAPI()

{compiled_code}

@app.post("/execute")
def execute_endpoint(inputs: dict):
    res_text, tokens, logs = run_workflow(**inputs)
    return {{"result": res_text, "tokens": tokens}}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""
        else: # mcp
            # Wrap in basic MCP boilerplate
            code = f"""import sys
import json

{compiled_code}

def main():
    # Simple stdio MCP server loop
    while True:
        line = sys.stdin.readline()
        if not line: break
        try:
            req = json.loads(line)
            inputs = req.get('params', {{}})
            res_text, tokens, logs = run_workflow(**inputs)
            print(json.dumps({{"result": res_text}}))
            sys.stdout.flush()
        except Exception as e:
            print(json.dumps({{"error": str(e)}}))
            sys.stdout.flush()

if __name__ == "__main__":
    main()
"""
        return {"status": "success", "code": code}

    return {"status": "success"}

@app.post("/api/deploy/{project_id}/execute")
def execute_deployed_project(project_id: int, payload: ExecutePayload, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if user and user.token_balance <= 0:
        raise HTTPException(status_code=403, detail="토큰을 모두 소진하여 실행할 수 없습니다.")

    result_text, tokens, logs = run_workflow(project.graph_data.get('nodes', []), project.graph_data.get('edges', []), db=db, session_id='api_call_' + str(project.id), project_id=project.id, **payload.inputs)
    
    import json
    try:
        total_tokens = tokens.get('total_tokens', 0) if isinstance(tokens, dict) else 0
        if user and total_tokens > 0:
            user.token_balance -= total_tokens

        db_log = models.FlowExecutionLog(
            user_id=user.id if user else None,
            payload=json.dumps({"project_id": project_id, "inputs": payload.inputs}),
            result=result_text,
            total_tokens=total_tokens,
            token_usage_details=tokens if isinstance(tokens, dict) else None
        )
        db.add(db_log)
        db.commit()
    except Exception as e:
        print(f"Failed to save deploy log: {e}")
        db.rollback()
        
    return {"status": "success", "result": result_text, "token_usage": tokens}

@app.api_route("/webhook/{endpoint_id}", methods=["GET", "POST"])
async def receive_webhook(endpoint_id: str, request: Request, db: Session = Depends(get_db)):
    projects = db.query(models.Project).all()
    project = None
    webhook_node_id = None
    
    # 1. Search by custom webhook URL defined in the node
    for p in projects:
        graph_data = p.graph_data or {}
        # Skip inactive projects
        if not (isinstance(graph_data, dict) and graph_data.get('is_live', False)):
            continue
            
        nodes = graph_data.get('nodes', []) if isinstance(graph_data, dict) else []
        for n in nodes:
            if isinstance(n, dict) and n.get('type') == 'webhookNode':
                node_url = n.get('data', {}).get('webhookUrl', '').strip()
                node_endpoint = node_url.rstrip('/').split('/')[-1] if node_url else ''
                print(f"Checking project {p.id}: node_url='{node_url}', node_endpoint='{node_endpoint}' against '{endpoint_id}'")
                if node_endpoint == endpoint_id:
                    project = p
                    webhook_node_id = n.get('id')
                    print(f"Matched project {p.id}!")
                    break
        if project:
            break
            
    # 2. Fallback to Project ID (backward compatibility)
    if not project:
        try:
            project_id = int(endpoint_id)
            project = db.query(models.Project).filter(models.Project.id == project_id).first()
            if project:
                graph_data = project.graph_data or {}
                nodes = graph_data.get('nodes', []) if isinstance(graph_data, dict) else []
                for n in nodes:
                    if isinstance(n, dict) and n.get('type') == 'webhookNode':
                        webhook_node_id = n.get('id')
                        break
        except ValueError:
            pass
            
    if not project or not webhook_node_id:
        return JSONResponse(status_code=404, content={"status": "error", "detail": "Webhook endpoint not found, or project is not active (Live Mode is OFF)"})
        
    # Get payload
    try:
        if request.method == "POST":
            payload = await request.json()
        else:
            payload = dict(request.query_params)
    except Exception:
        payload = {}
        
    graph_data = project.graph_data or {}
    nodes = graph_data.get('nodes', []) if isinstance(graph_data, dict) else []
    edges = graph_data.get('edges', []) if isinstance(graph_data, dict) else []
    
    # Run the workflow
    import json
    inputs = {webhook_node_id: json.dumps(payload, ensure_ascii=False)}
    
    try:
        result_text, tokens, logs = run_workflow(nodes, edges, db=db, session_id='webhook_' + str(project.id), project_id=project.id, **inputs)
        flow_status = "error" if "❌" in result_text or "Error" in result_text else "success"
        
        db_log = models.FlowExecutionLog(
            user_id=project.user_id,
            project_id=project.id,
            payload=json.dumps(payload, ensure_ascii=False),
            result="Success (Webhook)" if flow_status == "success" else result_text,
            total_tokens=tokens.get('total_tokens', 0) if isinstance(tokens, dict) else 0,
            token_usage_details=tokens if isinstance(tokens, dict) else None,
            status=flow_status,
            error_message=result_text if flow_status == "error" else None
        )
        db.add(db_log)
        db.commit()
        return {"status": "success", "result": result_text}
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})


@app.get("/api/bots")
def get_active_bots(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    projects = db.query(models.Project).filter(models.Project.user_id == user.id, models.Project.deploy_mode == "discord").all()
    
    result = []
    for p in projects:
        client = discord_bot._active_bots.get(p.id)
        status = "offline"
        bot_name = None
        if client:
            status = "online" if client.is_ready() else "connecting"
            bot_name = str(client.user) if client.user else None
            
        result.append({
            "project_id": p.id,
            "project_title": p.title,
            "status": status,
            "bot_name": bot_name,
            "updated_at": p.updated_at
        })
    return result

@app.post("/api/bots/{project_id}/stop")
async def stop_bot_endpoint(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Toggle live state
    graph_data = dict(project.graph_data) if project.graph_data else {}
    graph_data["is_live"] = False
    project.graph_data = graph_data
    flag_modified(project, "graph_data")
    db.commit()
    
    discord_bot.stop_discord_bot(project_id)
    
    from scheduler import sync_project_schedule
    try:
        sync_project_schedule(project_id, project)
    except Exception:
        pass
    
    return {"status": "success", "message": "Bot stopped and project live status disabled"}

@app.post("/api/bots/{project_id}/start")
async def start_bot_endpoint(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    token = project.graph_data.get("discord_bot_token")
    if not token:
        raise HTTPException(status_code=400, detail="No Discord token saved for this project")
    
    # Check tokens before starting
    if user and user.token_balance <= 0:
        raise HTTPException(status_code=403, detail="토큰을 모두 소진하여 봇을 시작할 수 없습니다.")
        
    # Toggle live state
    graph_data = dict(project.graph_data) if project.graph_data else {}
    graph_data["is_live"] = True
    project.graph_data = graph_data
    flag_modified(project, "graph_data")
    db.commit()

    discord_bot.start_discord_bot(project_id, token)
    
    from scheduler import sync_project_schedule
    try:
        sync_project_schedule(project_id, project)
    except Exception:
        pass
        
    return {"status": "success", "message": "Bot started and project live status enabled"}

@app.delete("/api/bots/{project_id}")
async def delete_bot_endpoint(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    discord_bot.stop_discord_bot(project_id)
    
    if project.graph_data:
        new_data = dict(project.graph_data)
        if "discord_bot_token" in new_data:
            del new_data["discord_bot_token"]
            project.graph_data = new_data
            flag_modified(project, "graph_data")
            
    project.deploy_mode = "chatbot"
    db.commit()
    
    return {"status": "success", "message": "Bot deleted"}

class TokenActionPayload(BaseModel):
    google_token: str
    new_discord_token: Optional[str] = None

@app.post("/api/bots/{project_id}/reveal-token")
def reveal_bot_token(project_id: int, payload: TokenActionPayload, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    try:
        idinfo = id_token.verify_oauth2_token(
            payload.google_token, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID, 
            clock_skew_in_seconds=600
        )
        google_id = idinfo['sub']
        if user.google_id != google_id:
            raise HTTPException(status_code=403, detail="Google authentication mismatch")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid Google token")
        
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    token = project.graph_data.get("discord_bot_token") if project.graph_data else None
    return {"status": "success", "token": token}

@app.put("/api/bots/{project_id}/update-token")
def update_bot_token(project_id: int, payload: TokenActionPayload, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    try:
        idinfo = id_token.verify_oauth2_token(
            payload.google_token, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID, 
            clock_skew_in_seconds=600
        )
        google_id = idinfo['sub']
        if user.google_id != google_id:
            raise HTTPException(status_code=403, detail="Google authentication mismatch")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid Google token")
        
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if project.graph_data:
        new_data = dict(project.graph_data)
        new_data["discord_bot_token"] = payload.new_discord_token
        project.graph_data = new_data
        flag_modified(project, "graph_data")
        db.commit()
        
    if project.id in discord_bot._active_bots:
        discord_bot.start_discord_bot(project.id, payload.new_discord_token)
        
    return {"status": "success", "message": "Token updated"}

@app.get("/api/bots/{project_id}/logs")
def get_bot_logs(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    logs = db.query(models.BotLog).filter(models.BotLog.project_id == project_id).order_by(models.BotLog.created_at.desc()).limit(50).all()
    
    return [
        {
            "id": log.id,
            "username": log.username,
            "message": log.message,
            "response": log.response,
            "created_at": log.created_at
        } for log in logs
    ]

@app.get("/api/schedules")
def get_schedules(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    projects = db.query(models.Project).filter(models.Project.user_id == user.id).all()
    schedules = []
    
    from scheduler import scheduler
    
    for p in projects:
        if p.graph_data:
            nodes = p.graph_data.get('nodes', [])
            schedule_node = next((n for n in nodes if n.get('type') == 'scheduleNode'), None)
            if schedule_node:
                job_id = f"project_{p.id}"
                job = scheduler.get_job(job_id)
                cron_expr = schedule_node.get('data', {}).get('cronExpression', '0 7 * * *')
                
                status = "Stopped"
                next_run = None
                
                # Use is_live to determine status if job is missing
                is_live = p.graph_data.get("is_live", False)
                if is_live and job:
                    status = "Active" if job.next_run_time else "Paused"
                    if job.next_run_time:
                        next_run = job.next_run_time.isoformat()
                elif is_live and not job:
                    status = "Stopped" # Error state technically
                else:
                    status = "Stopped"
                    if job and job.next_run_time:
                        next_run = job.next_run_time.isoformat()
                        
                schedules.append({
                    "project_id": p.id,
                    "title": p.title,
                    "cron": cron_expr,
                    "status": status,
                    "next_run": next_run
                })
    return schedules

@app.post("/api/schedules/{project_id}/pause")
def pause_schedule(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    graph_data = dict(project.graph_data) if project.graph_data else {}
    graph_data["is_live"] = False
    project.graph_data = graph_data
    flag_modified(project, "graph_data")
    db.commit()
    
    from scheduler import sync_project_schedule
    try:
        sync_project_schedule(project_id, project)
    except Exception:
        pass
        
    # Also stop discord bot if exists
    has_discord = any(n.get('type') == 'discordNode' for n in graph_data.get('nodes', []))
    if has_discord:
        discord_bot.stop_discord_bot(project_id)
        
    return {"status": "success", "message": "Schedule paused and project live status disabled"}

@app.post("/api/schedules/{project_id}/resume")
def resume_schedule(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    graph_data = dict(project.graph_data) if project.graph_data else {}
    graph_data["is_live"] = True
    project.graph_data = graph_data
    flag_modified(project, "graph_data")
    db.commit()
    
    from scheduler import sync_project_schedule
    try:
        sync_project_schedule(project_id, project)
    except Exception as e:
        print(f"Schedule sync failed: {e}")
        
    # Also start discord bot if exists
    has_discord = any(n.get('type') == 'discordNode' for n in graph_data.get('nodes', []))
    if has_discord:
        token = graph_data.get("discord_bot_token")
        if token:
            discord_bot.start_discord_bot(project_id, token)
            
    return {"status": "success", "message": "Schedule resumed and project live status enabled"}

@app.delete("/api/schedules/{project_id}")
def delete_schedule(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if project.graph_data:
        new_data = dict(project.graph_data)
        nodes = new_data.get('nodes', [])
        # Remove scheduleNode
        new_nodes = [n for n in nodes if n.get('type') != 'scheduleNode']
        new_data['nodes'] = new_nodes
        project.graph_data = new_data
        db.commit()
        
    from scheduler import sync_project_schedule
    sync_project_schedule(project_id, project)
    
    return {"status": "success", "message": "Schedule deleted"}

@app.get("/api/schedules/{project_id}/logs")
def get_schedule_logs(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    logs = db.query(models.FlowExecutionLog).filter(
        models.FlowExecutionLog.project_id == project_id,
        models.FlowExecutionLog.payload.like('%"trigger": "scheduler"%')
    ).order_by(models.FlowExecutionLog.execution_time.desc()).limit(50).all()
    
    return [
        {
            "id": log.id,
            "result": log.result,
            "total_tokens": log.total_tokens,
            "execution_time": log.execution_time
        } for log in logs
    ]

@app.get("/api/statistics")
def get_statistics(time_range: str = "weekly", user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    from sqlalchemy import func
    import datetime
    
    total_used = db.query(func.sum(models.FlowExecutionLog.total_tokens)).filter(models.FlowExecutionLog.user_id == user.id).scalar() or 0
    remaining = user.token_balance
    total_allocated = remaining + total_used # Just a fallback calculation
    print(f"[DEBUG] /api/statistics called by User ID {user.id} ({user.name}). Returning remaining: {remaining}, total_used: {total_used}")
    
    now = datetime.datetime.utcnow()
    chart_data = []

    if time_range == "hourly":
        start_time = now - datetime.timedelta(hours=23)
        start_time = start_time.replace(minute=0, second=0, microsecond=0)
        recent_logs = db.query(models.FlowExecutionLog).filter(
            models.FlowExecutionLog.user_id == user.id,
            models.FlowExecutionLog.execution_time >= start_time
        ).all()
        usage = {}
        for i in range(24):
            t = start_time + datetime.timedelta(hours=i)
            usage[t.strftime("%Y-%m-%d %H:00")] = 0
        for log in recent_logs:
            if log.execution_time:
                t_str = log.execution_time.strftime("%Y-%m-%d %H:00")
                if t_str in usage:
                    usage[t_str] += log.total_tokens
        chart_data = [{"date": k[-5:], "tokens": v, "fullDate": k} for k, v in sorted(usage.items())]

    elif time_range == "monthly":
        start_time = now - datetime.timedelta(days=29)
        start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        recent_logs = db.query(models.FlowExecutionLog).filter(
            models.FlowExecutionLog.user_id == user.id,
            models.FlowExecutionLog.execution_time >= start_time
        ).all()
        usage = {}
        for i in range(30):
            d = (start_time + datetime.timedelta(days=i)).date().isoformat()
            usage[d] = 0
        for log in recent_logs:
            if log.execution_time:
                d_str = log.execution_time.date().isoformat()
                if d_str in usage:
                    usage[d_str] += log.total_tokens
        chart_data = [{"date": k[-5:], "tokens": v, "fullDate": k} for k, v in sorted(usage.items())]

    elif time_range == "yearly":
        usage = {}
        m = now.month
        y = now.year
        for i in range(12):
            usage[f"{y}-{m:02d}"] = 0
            
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        
        start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=365)
        recent_logs = db.query(models.FlowExecutionLog).filter(
            models.FlowExecutionLog.user_id == user.id,
            models.FlowExecutionLog.execution_time >= start_time
        ).all()
        for log in recent_logs:
            if log.execution_time:
                m_str = log.execution_time.strftime("%Y-%m")
                if m_str in usage:
                    usage[m_str] += log.total_tokens
        chart_data = [{"date": k, "tokens": v, "fullDate": k} for k, v in sorted(usage.items())]

    else: # weekly
        start_time = now - datetime.timedelta(days=6)
        start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        recent_logs = db.query(models.FlowExecutionLog).filter(
            models.FlowExecutionLog.user_id == user.id,
            models.FlowExecutionLog.execution_time >= start_time
        ).all()
        usage = {}
        for i in range(7):
            d = (start_time + datetime.timedelta(days=i)).date().isoformat()
            usage[d] = 0
        for log in recent_logs:
            if log.execution_time:
                d_str = log.execution_time.date().isoformat()
                if d_str in usage:
                    usage[d_str] += log.total_tokens
        chart_data = [{"date": k[-5:], "tokens": v, "fullDate": k} for k, v in sorted(usage.items())]

    # Project usage
    project_usage_rows = db.query(
        models.FlowExecutionLog.project_id,
        func.sum(models.FlowExecutionLog.total_tokens).label("total")
    ).filter(
        models.FlowExecutionLog.user_id == user.id,
        models.FlowExecutionLog.project_id.isnot(None)
    ).group_by(models.FlowExecutionLog.project_id).all()

    project_usage = []
    deleted_project_tokens = 0
    
    for pid, tot in project_usage_rows:
        project = db.query(models.Project).filter(models.Project.id == pid).first()
        if project:
            project_usage.append({"project_id": pid, "title": project.title, "tokens": tot})
        else:
            deleted_project_tokens += tot
            
    if deleted_project_tokens > 0:
        project_usage.append({"project_id": -1, "title": "삭제된 프로젝트", "tokens": deleted_project_tokens})
    
    none_usage = db.query(func.sum(models.FlowExecutionLog.total_tokens)).filter(
        models.FlowExecutionLog.user_id == user.id,
        models.FlowExecutionLog.project_id.is_(None)
    ).scalar()
    
    if none_usage:
        project_usage.append({"project_id": None, "title": "미지정 프로젝트", "tokens": none_usage})

    project_usage.sort(key=lambda x: x['tokens'], reverse=True)

    return {
        "total_used": total_used,
        "remaining": remaining,
        "total_allocated": total_allocated,
        "chart_data": chart_data,
        "project_usage": project_usage
    }

class FriendAddPayload(BaseModel):
    email: str

@app.get("/api/friends")
def get_friends(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    friends = db.query(models.Friendship).filter(models.Friendship.user_id == user.id).all()
    return [{"id": f.friend.id, "name": f.friend.name, "email": f.friend.email, "picture": f.friend.picture} for f in friends]

@app.delete("/api/friends/{friend_id}")
def remove_friend(friend_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    db.query(models.Friendship).filter(models.Friendship.user_id == user.id, models.Friendship.friend_id == friend_id).delete()
    db.query(models.Friendship).filter(models.Friendship.user_id == friend_id, models.Friendship.friend_id == user.id).delete()
    db.commit()
    return {"status": "success"}

# --- Friend Request Endpoints ---

@app.post("/api/friends/request")
def send_friend_request(payload: FriendAddPayload, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    if payload.email == user.email:
        raise HTTPException(status_code=400, detail="자기 자신에게는 친구 신청을 보낼 수 없습니다.")

    target = db.query(models.User).filter(models.User.email == payload.email).first()
    if not target:
        raise HTTPException(status_code=404, detail="해당 이메일의 사용자를 찾을 수 없습니다.")

    # Already friends?
    already = db.query(models.Friendship).filter(models.Friendship.user_id == user.id, models.Friendship.friend_id == target.id).first()
    if already:
        raise HTTPException(status_code=400, detail="이미 친구 상태입니다.")

    # Pending request already sent?
    pending = db.query(models.FriendRequest).filter(
        models.FriendRequest.from_user_id == user.id,
        models.FriendRequest.to_user_id == target.id,
        models.FriendRequest.status == "pending"
    ).first()
    if pending:
        raise HTTPException(status_code=400, detail="이미 친구 신청을 보냈습니다.")

    req = models.FriendRequest(from_user_id=user.id, to_user_id=target.id, status="pending")
    db.add(req)
    db.commit()
    return {"status": "success", "message": f"{target.name}님께 친구 신청을 보냈습니다."}

@app.get("/api/friends/requests")
def get_friend_requests(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """Get all pending friend requests received by the current user."""
    requests = db.query(models.FriendRequest).filter(
        models.FriendRequest.to_user_id == user.id,
        models.FriendRequest.status == "pending"
    ).all()
    return [{
        "id": r.id,
        "from_user_id": r.from_user_id,
        "name": r.from_user.name,
        "email": r.from_user.email,
        "picture": r.from_user.picture,
        "created_at": r.created_at
    } for r in requests]

@app.get("/api/friends/pending-count")
def get_pending_count(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    count = db.query(models.FriendRequest).filter(
        models.FriendRequest.to_user_id == user.id,
        models.FriendRequest.status == "pending"
    ).count()
    return {"count": count}

@app.post("/api/friends/requests/{request_id}/accept")
def accept_friend_request(request_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    req = db.query(models.FriendRequest).filter(
        models.FriendRequest.id == request_id,
        models.FriendRequest.to_user_id == user.id,
        models.FriendRequest.status == "pending"
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="친구 신청을 찾을 수 없습니다.")

    req.status = "accepted"
    # Create mutual friendship
    f1 = models.Friendship(user_id=user.id, friend_id=req.from_user_id)
    f2 = models.Friendship(user_id=req.from_user_id, friend_id=user.id)
    db.add(f1)
    db.add(f2)
    db.commit()
    return {"status": "success", "message": "친구 신청을 수락했습니다."}

@app.post("/api/friends/requests/{request_id}/reject")
def reject_friend_request(request_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    req = db.query(models.FriendRequest).filter(
        models.FriendRequest.id == request_id,
        models.FriendRequest.to_user_id == user.id,
        models.FriendRequest.status == "pending"
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="친구 신청을 찾을 수 없습니다.")

    db.delete(req)
    db.commit()
    return {"status": "success", "message": "친구 신청을 거절했습니다."}

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import mimetypes

# Fix mimetypes for Windows where .js might be text/plain
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

# Serve frontend static files
# Calculate the absolute path to the frontend/dist directory
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")

if os.path.exists(FRONTEND_DIST):
    # Mount the static files (assets, JS, CSS)
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    # Catch-all route for SPA routing (returns index.html)
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
