import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, File, UploadFile, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import shutil
import jwt
import datetime
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from database import engine, Base, get_db
import models
from graph import compile_workflow, run_workflow
import discord_bot

JWT_SECRET = os.environ.get("JWT_SECRET", "super-secret-key")
JWT_ALGORITHM = "HS256"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# Create DB tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Business Automation API")

# Ensure uploads directory exists
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

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
    finally:
        db.close()

class FlowPayload(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

class DeployPayload(BaseModel):
    mode: str
    discord_bot_token: str = None

class ExecutePayload(BaseModel):
    inputs: Dict[str, Any]

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

class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    graph_data: Dict[str, Any]
    is_public: bool = False

@app.get("/api/projects/public")
def get_public_projects(db: Session = Depends(get_db)):
    projects = db.query(models.Project).filter(models.Project.is_public == True).all()
    return [{"id": p.id, "title": p.title, "description": p.description, "owner": p.owner.name if p.owner else "Unknown", "updated_at": p.updated_at} for p in projects]

@app.get("/api/projects/my")
def get_my_projects(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    projects = db.query(models.Project).filter(models.Project.user_id == user.id).all()
    return [{"id": p.id, "title": p.title, "description": p.description, "is_public": p.is_public, "updated_at": p.updated_at} for p in projects]

@app.post("/api/projects")
def create_project(payload: ProjectCreate, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = models.Project(
        user_id=user.id,
        title=payload.title,
        description=payload.description,
        graph_data=payload.graph_data,
        is_public=payload.is_public
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
    if not project.is_public and (not user or project.user_id != user.id):
        raise HTTPException(status_code=403, detail="Not authorized to view this project")
    return {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "graph_data": project.graph_data,
        "is_public": project.is_public,
        "deploy_mode": project.deploy_mode,
        "owner_id": project.user_id,
        "owner_name": project.owner.name if project.owner else "Unknown"
    }

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this project")
    
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
    project.graph_data = payload.graph_data
    project.is_public = payload.is_public
    db.commit()
    return {"status": "success"}

@app.post("/api/execute")
def execute_flow(payload: FlowPayload, db: Session = Depends(get_db)):
    """
    Receives graph data from frontend, runs LangGraph logic,
    saves execution to DB, and returns the result.
    """
    # 1. Run LangGraph with Gemini
    result_text = run_workflow(payload.nodes, payload.edges)
    
    import json
    # 2. Save log to PostgreSQL (or SQLite fallback)
    try:
        db_log = models.FlowExecutionLog(
            payload=json.dumps(payload.dict()),
            result=result_text
        )
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
    except Exception as e:
        print(f"Failed to save log to DB: {e}")
        db.rollback()

    # 3. Return response to frontend
    return {"status": "success", "result": result_text}

@app.post("/api/compile")
def compile_flow(payload: FlowPayload):
    """
    Parses graph data from frontend and returns raw Python code representation.
    """
    compiled_code = compile_workflow(payload.nodes, payload.edges)
    return {"status": "success", "code": compiled_code}

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
    res = run_workflow(**inputs)
    return {{"result": res}}

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
            res = run_workflow(**inputs)
            print(json.dumps({{"result": res}}))
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
def execute_deployed_project(project_id: int, payload: ExecutePayload, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    result_text = run_workflow(project.graph_data.get('nodes', []), project.graph_data.get('edges', []), **payload.inputs)
    return {"status": "success", "result": result_text}

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
    
    discord_bot.stop_discord_bot(project_id)
    return {"status": "success", "message": "Bot stopped"}

@app.post("/api/bots/{project_id}/start")
async def start_bot_endpoint(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    token = project.graph_data.get("discord_bot_token")
    if not token:
        raise HTTPException(status_code=400, detail="No Discord token saved for this project")
        
    discord_bot.start_discord_bot(project_id, token)
    return {"status": "success", "message": "Bot started"}

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
        db.commit()
        
    if project.id in discord_bot._active_bots:
        discord_bot.start_discord_bot(project.id, payload.new_discord_token)
        
    return {"status": "success", "message": "Token updated"}
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
