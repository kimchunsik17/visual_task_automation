import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Body, Depends, File, Form, UploadFile, HTTPException, status, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import jwt
import datetime
import uuid
import time
import re
import requests
import uuid
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from database import engine, Base, get_db
import db_migrate
import models
from graph import compile_workflow, run_workflow
from node_errors import runtime as node_error_runtime
from dry_run import dry_run_workflow
from meta_agent import FLOW_REPAIR_PROMPT_VERSION, run_agent_turn
import meta_agent
import node_definition
import project_revisions
import mock_service
from connectors import oauth_flow as connector_oauth_flow
from connectors import providers as connector_providers
import app_agent
import ui_generator
from generation_trace import (
    build_generation_trace,
    persist_generation_trace,
    record_trace_adoption,
    trace_to_dict,
)
from llm.operations import summarize_generation_operations
from llm.routing import probe_local_provider, routing_config_snapshot, routing_metrics
import discord_bot
import telegram_bot
import scheduler
from rag_utils import process_and_store_chat_context
import upload_security
from upload_security import (
    CONTEXT_UPLOAD_EXTENSIONS,
    GENERAL_UPLOAD_EXTENSIONS,
    max_context_bytes,
    max_context_files,
    max_upload_bytes,
    save_upload_limited,
)
from credential_crypto import decrypt_secret, encrypt_secret, migrate_plaintext_credentials
from usage_tracking import (
    EVENT_APP_GENERATION,
    EVENT_WORKFLOW_EXECUTION,
    EVENT_WORKFLOW_GENERATION,
    ensure_usage_tracking_schema,
    outcome_from_result,
    record_usage,
)
import project_access
from statistics_service import VALID_TIME_RANGES, build_statistics

# 기본값을 두지 않는다. 'super-secret-key' 가 기본값이던 동안에는, .env 에 JWT_SECRET 을
# 넣는 것을 잊어도 서버가 조용히 떠서 **공개된 문자열로 토큰에 서명**했다 — 누구나 임의의
# user_id 로 토큰을 만들 수 있다는 뜻이다. 설정 누락은 부팅 실패로 드러나야 한다.
#
# ⚠️ 이미 뜬 서비스에서 이 값을 바꾸면 user_api_keys 의 자격증명이 복호화 불가가 된다 —
# credential_crypto 가 CREDENTIAL_ENCRYPTION_KEY 가 없을 때 JWT_SECRET 으로 폴백하기
# 때문이다(:19-33). 재암호화 스크립트는 저장소에 없다. 바꾸려면 CREDENTIAL_ENCRYPTION_KEY 를
# 먼저 독립된 값으로 넣고 기존 자격증명을 옮긴 뒤에 한다.
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET 이 설정되지 않았다. backend/.env 에 충분히 긴 임의 문자열을 넣어라 "
        "(backend/.env.example 참고). 예전에는 'super-secret-key' 로 조용히 폴백했는데, "
        "그러면 공개된 문자열로 토큰에 서명하게 된다."
    )
JWT_ALGORITHM = "HS256"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "off", "no"}


# Create DB tables
# 스키마는 Alembic 마이그레이션으로 맞춘다(ADR-0006). 예전에는 create_all 을 썼는데,
# 이미 있는 테이블에 컬럼을 추가해주지 않아서 모델 변경이 운영 DB에 조용히 누락됐다.
# create_all 로 만들어진 기존 DB 는 ensure_schema 가 기준선으로 stamp 한 뒤 인계받는다.
#
# ■ AUTO_MIGRATE_ON_BOOT (기본 1 = 지금까지의 동작)
#   임포트 시점에 마이그레이션을 **적용**한다. 이 말은 "재기동 = 운영 스키마 변경" 이라는
#   뜻이고, 크래시 루프가 돌면 매 사이클마다 그것이 실행된다(운영에서 4.2일간 6,645회
#   재기동이 관측됐다). scripts/deploy.sh 가 alembic 을 먼저 완주시키는 레일을 쓰기
#   시작하면 0 으로 내려라 — 그때부터 앱은 스키마를 **확인만** 하고, 어긋나면 뜨지 않는다.
#
#   순서를 뒤집지 말 것: 배포 스크립트가 alembic 을 돌리기 전에 이 값을 0 으로 내리면
#   다음 마이그레이션이 있는 배포에서 서비스가 서 버린다.
if _env_flag("AUTO_MIGRATE_ON_BOOT", True):
    print(f"[db] {db_migrate.ensure_schema(engine)}")
else:
    _head = db_migrate.head_revision()
    _current = db_migrate.current_revision(engine)
    if _current != _head:
        raise RuntimeError(
            f"DB 스키마가 head 가 아니다 (current={_current}, head={_head}). "
            "마이그레이션을 적용하지 않은 채로 뜨면 첫 쿼리에서 사용자에게 오류로 드러난다. "
            "`alembic upgrade head` 를 먼저 돌려라 — scripts/deploy.sh 가 그것을 한다."
        )
    print(f"[db] 스키마 확인만 했다 (revision={_current}, AUTO_MIGRATE_ON_BOOT=0)")
ensure_usage_tracking_schema(engine)

app = FastAPI(title="Business Automation API")

# Ensure uploads directory exists
os.makedirs("uploads", exist_ok=True)

# /uploads 서빙 라우트는 get_current_user_required 정의 뒤(아래)로 옮겼다 — 모듈 로드 순서 때문.

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import traceback

import logging

from node_errors.redaction import redact_text

# 예전에는 두 처리기가 error_log.txt 에 직접 append 했다. 회전이 없어 무한히 자라고,
# 프로세스가 여럿이면 같은 파일에 섞여 쓴다. logging 으로 내보내면 journald/logrotate 가
# 맡는다. 이 파일을 읽는 코드는 저장소에 없었다(추적도 PR #29 에서 해제됐다).
logger = logging.getLogger("app")


def _safe_validation_errors(errors) -> list:
    """검증 오류에서 사용자가 보낸 값을 떼어낸다.

    pydantic 의 `exc.errors()` 는 각 항목에 `input`(제출된 값 원본)과 `ctx` 를 싣는다.
    그대로 돌려주면 **검증에 실패한 요청 본문이 응답과 로그에 그대로 되비친다** — 토큰이나
    비밀번호를 잘못된 형식으로 보내면 그 값이 그대로 나온다. `loc`/`msg`/`type` 만 남기면
    클라이언트가 어느 필드가 왜 틀렸는지 아는 데는 충분하다.

    덤으로 `ctx` 에 직렬화 불가능한 값이 들어와 500 이 되던 경로도 함께 닫힌다.
    """
    safe = []
    for item in errors or []:
        if not isinstance(item, dict):
            continue
        safe.append({
            "loc": list(item.get("loc") or []),
            "msg": redact_text(item.get("msg"), max_length=300),
            "type": item.get("type"),
        })
    return safe


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = uuid.uuid4().hex
    logger.exception(
        "unhandled error %s %s error_id=%s: %s",
        request.method, request.url.path, error_id, redact_text(exc, max_length=500),
    )
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "error_id": error_id},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    safe_errors = _safe_validation_errors(exc.errors())
    logger.warning(
        "validation error %s %s: %s", request.method, request.url.path, safe_errors,
    )
    return JSONResponse(status_code=422, content={"detail": safe_errors})

# Setup CORS to allow requests from the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "https://wa-pnu.duckdns.org"], # Vite default port + production domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    db = next(get_db())
    migrated_credentials = migrate_plaintext_credentials(db)
    if migrated_credentials:
        print(f"Encrypted {migrated_credentials} legacy credential fields.")
    try:
        discord_bot.boot_existing_discord_bots(db)
    except Exception as e:
        print(f"Failed to boot discord bots: {e}")
    try:
        telegram_bot.sync_all_telegram_webhooks(db)
    except Exception as e:
        print(f"Failed to sync telegram webhooks: {e}")
    try:
        scheduler.start_scheduler()
        scheduler.sync_all_schedules(db)
    except Exception as e:
        print(f"Failed to boot scheduler: {e}")
    finally:
        db.close()
    # 노드 지식 색인(ADR-0013)을 백그라운드에서 증분 동기화한다. embedding provider가 없거나
    # 실패하면 hybrid 선별이 lexical 폴백으로만 동작할 뿐, 서버 기동과 생성에는 영향이 없다.
    try:
        import node_knowledge
        node_knowledge.sync_node_index_in_background()
    except Exception as e:
        print(f"Failed to start node knowledge index sync: {e}")

@app.get("/api/health")
def health():
    """프로세스가 살아 있는가만 본다. 의존성을 타지 않아 DB 가 죽어도 200 이다.

    /api/ready 와 나누는 이유: 이걸로 재기동을 판단하는데 DB 를 함께 보면, DB 가 잠깐
    흔들릴 때 멀쩡한 프로세스를 죽이게 된다.
    """
    return {"status": "ok"}


@app.get("/api/ready")
def ready():
    """트래픽을 받아도 되는 상태인가. 배포 스모크가 이걸 보고 성공·실패를 가른다.

    스키마 확인이 핵심이다 — 리비전이 head 가 아닌 채로 서비스가 서면 첫 쿼리에서
    사용자에게 오류로 드러난다. 실패해도 예외를 올리지 않고 503 + 어디가 깨졌는지를
    돌려준다(프로브가 스택트레이스를 받아봐야 쓸 데가 없다).
    """
    from sqlalchemy import text as _sql_text

    import db_migrate as _db_migrate

    checks: dict = {}
    detail: dict = {}

    try:
        with engine.connect() as connection:
            connection.execute(_sql_text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:
        checks["database"] = False
        detail["database"] = type(exc).__name__

    try:
        head = _db_migrate.head_revision()
        current = _db_migrate.current_revision(engine)
        checks["schema"] = head is not None and head == current
        if not checks["schema"]:
            detail["schema"] = {"head": head, "current": current}
    except Exception as exc:
        checks["schema"] = False
        detail["schema"] = type(exc).__name__

    # 스케줄러는 기동 시 꺼둘 수 있다(DISABLE_SCHEDULER). 끈 것을 고장으로 보지 않는다.
    if os.environ.get("DISABLE_SCHEDULER"):
        checks["scheduler"] = None
    else:
        try:
            checks["scheduler"] = bool(scheduler.scheduler.running)
        except Exception as exc:
            checks["scheduler"] = False
            detail["scheduler"] = type(exc).__name__

    ok = all(v for v in checks.values() if v is not None)
    body = {"status": "ready" if ok else "not_ready", "checks": checks}
    if detail:
        body["detail"] = detail
    return JSONResponse(status_code=200 if ok else 503, content=body)


class FlowPayload(BaseModel):
    project_id: Optional[int] = None
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    # 사용자 승인 노드별 결정({node_id: 'Y'|'N'}). 에디터가 실행 전에 사용자에게 물어 채운다.
    # 없으면 승인 노드는 fail-closed 로 실행을 중단한다(P0 — 자동 승인 제거).
    approval_decisions: Optional[Dict[str, str]] = None
    # 부분 실행(에디터의 "이 노드부터 실행", EDITOR_SHORTCUTS §7.4): 지정한 노드를 진입점으로
    # 하류만 실행하고, entry_input이 직전 노드 출력 자리에 들어간다(승인 재개와 같은 메커니즘).
    entry_node_id: Optional[str] = None
    entry_input: Optional[str] = None
    # 범위 실행의 나머지 축(EDITOR_SHORTCUTS §7.4)과 고정 출력(§7.3).
    stop_node_id: Optional[str] = None
    scope_node_ids: Optional[List[str]] = None
    pinned_outputs: Optional[Dict[str, str]] = None

class DeployPayload(BaseModel):
    mode: str

class ExecutePayload(BaseModel):
    inputs: Dict[str, Any]

class ChatPayload(BaseModel):
    project_id: str
    message: str
    graph_data: Dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})
    complexity_level: str = "low"
    training_consent: bool = False
    target_type: Optional[str] = "auto"
    # 사용자가 캔버스에서 지목한 대상(백로그 28 POINT-0). 없으면 예전과 똑같이 동작한다.
    pointing_context: Optional[Dict[str, Any]] = None

security = HTTPBearer(auto_error=False)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    if not credentials:
        return None
    token = credentials.credentials

    # (제거됨) 예전에는 'dev-mock-token' 문자열 하나로 더미 유저(id 9999)를 만들어 인증을
    # 통과시켰다. 프론트엔드는 이 값을 보낸 적이 없고, 운영에 남으면 헤더 한 줄로 누구나
    # 남의 계정 경로에 들어올 수 있는 인증 우회다. 검증은 아래 서명 확인 하나로만 한다.

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            return None
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            # For local testing, if user doesn't exist, create a dummy one with this ID
            user = models.User(id=user_id, email=f"dummy_{user_id}@test.com", name="Test User")
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    except jwt.PyJWTError:
        return None

# 프로젝트 행위 권한을 강제하는 한 곳(ADR-0024). project_access 에 RUN/DEPLOY 가 선언돼 있는데
# 강제하는 호출부가 0곳이어서, 정수 id 만으로 남의 워크플로우를 실행·배포할 수 있었다(2026-08-31).
# 조회 권한조차 없으면 존재를 알리지 않는다 — project_access.require 의 주석이 요구하는 규약이다.
def _require_project_action(db, user, project, action: str):
    if project_access.can(db, user, project, action):
        return project
    if action != project_access.VIEW and not project_access.can(db, user, project, project_access.VIEW):
        raise HTTPException(status_code=404, detail="Project not found")
    raise HTTPException(status_code=403, detail=f"Not authorized to {action} this project")


# 공개 앱은 로그아웃 방문자도 실행할 수 있어야 한다(링크를 받은 사람이 쓰는 것이 기능이다).
# 그래서 실행 경로는 "공개면 익명 허용, 아니면 RUN 권한" 으로 판정한다 — project_access.can 은
# 공개 범위에 VIEW 만 주므로(의도된 설계) 이 규칙을 여기서 따로 적는다.
def _can_run_project(db, user, project) -> bool:
    if project is None:
        return False
    if getattr(project, "visibility", "private") == "public":
        return True
    return project_access.can(db, user, project, project_access.RUN)


def get_current_user_required(user: models.User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


# ⚠️ 예전에는 app.mount("/uploads", StaticFiles(...)) 로 업로드·생성 산출물을 인증 없이 전부
# 노출했다(2026-08-31 적대적 리뷰: 인터넷에서 output.hwpx 등 고정 파일명이 200 으로 다운로드됐다).
# 파일 접근은 이미 artifact_id 라우트로 이관됐고 /uploads/ 정적 URL 을 참조하는 프론트·백엔드
# 코드가 없다. 정적 마운트를 없애고, stored_name 으로 소유자를 확인하는 라우트로 대체한다.
@app.get("/uploads/{stored_name}")
def serve_upload(stored_name: str, user: models.User = Depends(get_current_user_required),
                 db: Session = Depends(get_db)):
    import artifacts as _artifacts
    # 경로 순회 차단 — stored_name 은 파일명 하나여야 한다.
    if "/" in stored_name or "\\" in stored_name or stored_name in ("", ".", ".."):
        raise HTTPException(status_code=404, detail="Not found")
    # per-user 물리 이동 후 stored_name 은 (owner, name) 복합 unique 다 — 같은 이름의 남의
    # 행이 있어도 내 것만 본다. 소유자가 아니면 존재를 알리지 않는다.
    record = db.query(models.UploadedFile).filter(
        models.UploadedFile.stored_name == stored_name,
        models.UploadedFile.owner_user_id == user.id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Not found")
    root = _artifacts.upload_root()
    # 실제 파일은 소유자 디렉토리(uploads/u<id>/) 에 있고, 이관 전 파일은 레거시 루트에 있다.
    candidate = upload_security.stored_file_path(record.stored_name, record.owner_user_id).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(candidate)


def _optional_user(request: Request, db: Session):
    """Authorization 헤더가 있으면 사용자를 돌려주고, 없거나 잘못됐으면 None."""
    auth_header = request.headers.get("Authorization") or ""
    if not auth_header.startswith("Bearer "):
        return None
    try:
        claims = jwt.decode(auth_header.split(" ", 1)[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    return db.query(models.User).filter(models.User.id == claims.get("user_id")).first()


def _resolve_upload_owner(user, project_id: Optional[str], db: Session):
    """이 업로드의 용량을 누구 몫으로 계산할지 정한다 (ADR-0010).

    배포된 앱(`/viewer/:projectId`, `/custom-app/:appId`)에는 로그인 요구가 없다. 그래서
    "로그인한 사람만 업로드" 로 막으면 익명으로 쓰라고 만든 앱이 파일을 못 받는다. 대신
    익명 업로드는 **공개된 프로젝트에 한해** 허용하고 그 소유자의 용량으로 계산한다.
    """
    if user:
        return user.id, user.id

    if project_id and str(project_id).isdigit():
        project = db.query(models.Project).filter(models.Project.id == int(project_id)).first()
        # 비공개 프로젝트 id 를 찍어보며 남의 용량을 소모시키는 것을 막는다.
        if project and project.visibility == "public":
            return project.user_id, None

    raise HTTPException(
        status_code=401,
        detail="파일을 올리려면 로그인하거나, 공개된 앱에서 업로드해야 합니다.",
    )


@app.post("/api/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    purpose: str = Form("node"),
    db: Session = Depends(get_db),
):
    """검증된 업로드를 서버가 지은 이름으로 저장하고, 소유·용량·보존 기간을 기록한다.

    예전에는 인증이 전혀 없어서 누구나 서버 디스크를 채울 수 있었고, 올라간 파일이 누구
    것인지 알 방법이 없어 용량 제한도 정리도 불가능했다(ADR-0010).
    """
    user = _optional_user(request, db)
    owner_user_id, uploaded_by_user_id = _resolve_upload_owner(user, project_id, db)

    # 허용 확장자는 용도별로 다르다(ADR-0010) — 문서 목록에 영상이 없고, 영상 목록에 문서가
    # 없다. purpose='video' 는 앱 빌더 파일 컴포넌트가 영상 업로드(YouTube 노드 등)에 쓴다.
    if purpose == "video":
        allowed_extensions = upload_security.VIDEO_UPLOAD_EXTENSIONS
        max_bytes = int(os.getenv("MAX_VIDEO_UPLOAD_BYTES", 256 * 1024 * 1024))
    elif purpose == "community":
        # 커뮤니티 글 이미지. 익명 업로드를 받지 않는 이유는 정리할 주인이 없어지기 때문이다.
        if user is None:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
        allowed_extensions = upload_security.IMAGE_UPLOAD_EXTENSIONS
        max_bytes = int(os.getenv("MAX_COMMUNITY_IMAGE_BYTES", 5 * 1024 * 1024))
    else:
        allowed_extensions = GENERAL_UPLOAD_EXTENSIONS
        max_bytes = max_upload_bytes()

    # 파일 수 한도는 저장 전에 본다. 용량은 실제 크기를 알아야 하므로 저장한 뒤 확인하고,
    # 넘으면 방금 쓴 파일을 지운다(대략치로 미리 막으면 정상 업로드까지 거절된다).
    upload_security.ensure_quota(db, owner_user_id, 0)

    file_path, original_name = await save_upload_limited(
        file,
        allowed_extensions=allowed_extensions,
        max_bytes=max_bytes,
        owner_user_id=owner_user_id,
    )

    try:
        size_bytes = file_path.stat().st_size
        upload_security.ensure_quota(db, owner_user_id, size_bytes)
        record = upload_security.record_upload(
            db,
            stored_path=file_path,
            original_name=original_name,
            owner_user_id=owner_user_id,
            uploaded_by_user_id=uploaded_by_user_id,
            project_id=int(project_id) if project_id and str(project_id).isdigit() else None,
            purpose=purpose if purpose in {"node", "app", "context", "video", "community"} else "node",
            content_type=file.content_type,
            size_bytes=size_bytes,
        )
        db.commit()
    except Exception:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise

    return {
        "status": "success",
        # 공개 문자열은 물리 위치(uploads/u<id>/...)가 아니라 늘 uploads/<이름> 이다 —
        # 프론트 링크·legacy 정규식·서빙 URL(/uploads/<이름>) 계약이 이 형태를 전제한다.
        "file_path": f"uploads/{file_path.name}",
        "filename": original_name,
        # artifact_id 를 함께 준다 — 커뮤니티 이미지처럼 경로가 아니라 식별자로 붙이는 곳이 있다.
        "artifact_id": record.artifact_id,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
    }


@app.get("/api/uploads/usage")
def get_upload_usage(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """내 업로드 사용량. 한도에 걸렸을 때 왜 걸렸는지 보여주기 위한 것이다."""
    used_bytes, used_files = upload_security.current_usage(db, user.id)
    return {
        "status": "success",
        "used_bytes": used_bytes,
        "used_files": used_files,
        "max_bytes": upload_security.quota_bytes_per_user(),
        "max_files": upload_security.quota_files_per_user(),
        "retention_days": upload_security.retention_days(),
    }


@app.get("/api/artifacts")
def list_artifacts(
    project_id: Optional[int] = None,
    limit: int = 50,
    user: models.User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """첨부로 고를 수 있는 내 파일 목록 (ADR-0018). Inspector 의 파일 선택기가 읽는다.

    저장 이름과 서버 경로는 응답에 들어가지 않는다 — `artifactId` 와 표시 이름·크기·형식만 나간다.
    """
    import artifacts as artifact_service

    if project_id is not None:
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if not project or project.user_id != user.id:
            raise HTTPException(status_code=404, detail="Project not found")

    refs = artifact_service.list_for_project(db, owner_user_id=user.id, project_id=project_id, limit=limit)
    return {"status": "success", "artifacts": [ref.to_public_dict() for ref in refs]}


@app.post("/api/artifacts/validate")
def validate_artifacts(
    payload: dict = Body(...),
    user: models.User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """실제 전송 없이 첨부만 검증한다 (ADR-0018 FILE-SEND-4 ②).

    편집기의 "첨부 검증" 버튼과 런타임이 **같은** 함수를 쓴다 — 편집기에서 통과한 첨부가 실행에서
    거절되면 사용자는 이유를 알 수 없다.
    """
    import delivery_attachments
    from artifacts import ArtifactError

    provider = str(payload.get("provider") or "discord").lower()
    project_id = payload.get("projectId")
    artifact_ids = payload.get("artifactIds") or []
    if not isinstance(artifact_ids, list):
        raise HTTPException(status_code=400, detail="artifactIds must be a list")
    if project_id is not None:
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if not project or project.user_id != user.id:
            raise HTTPException(status_code=404, detail="Project not found")

    policy = delivery_attachments.policy_for(provider)
    try:
        resolved = delivery_attachments.validate_attachments(
            db, artifact_ids, owner_user_id=user.id, project_id=project_id, policy=policy,
        )
    except ArtifactError as exc:
        return {
            "status": "error", "ok": False,
            "policy": policy.to_public_dict(),
            "error": exc.error.to_dict(),
        }
    return {
        "status": "success", "ok": True,
        "policy": policy.to_public_dict(),
        "attachments": [item.ref.to_public_dict() for item in resolved],
        "totalBytes": sum(item.ref.size_bytes for item in resolved),
    }


@app.get("/api/artifacts/policies")
def artifact_policies():
    """채널별 첨부 한도. Node Definition·Inspector 사전 검증·런타임이 같은 값을 읽게 한다."""
    import delivery_attachments

    return {
        "status": "success",
        "enabled": delivery_attachments.delivery_v1_enabled(),
        "connectors": {
            name: {**policy, "enabled": delivery_attachments.connector_enabled(name)}
            for name, policy in delivery_attachments.policies_public().items()
        },
    }


@app.post("/api/chat/upload_context")
async def upload_chat_context(
    project_id: str = Form(...),
    files: List[UploadFile] = File(...),
    user: models.User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Validate context documents and restrict existing projects to their owner."""
    if not project_id or len(project_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid project id")
    if len(files) > max_context_files():
        raise HTTPException(status_code=413, detail=f"At most {max_context_files()} files may be uploaded.")

    if project_id.isdigit():
        project = db.query(models.Project).filter(models.Project.id == int(project_id)).first()
        if not project or project.user_id != user.id:
            raise HTTPException(status_code=404, detail="Project not found")
    elif not re.fullmatch(r"draft-[0-9]{10,20}", project_id):
        raise HTTPException(status_code=400, detail="Invalid project id")

    processed_files = []
    total_chunks = 0
    for file in files:
        file_path, original_name = await save_upload_limited(
            file,
            allowed_extensions=CONTEXT_UPLOAD_EXTENSIONS,
            max_bytes=max_context_bytes(),
            owner_user_id=user.id,
        )
        try:
            chunks_added = process_and_store_chat_context(project_id, str(file_path), original_name)
        finally:
            file_path.unlink(missing_ok=True)
        total_chunks += chunks_added
        processed_files.append(original_name)

    return {"status": "success", "processed_files": processed_files, "total_chunks": total_chunks}


@app.delete("/api/training-data/me")
def delete_my_training_data(
    user: models.User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    deleted = db.query(models.TrainingExample).filter(
        models.TrainingExample.user_id == user.id,
    ).delete(synchronize_session=False)
    db.commit()
    return {"status": "success", "deleted": deleted}


# ── 문서 포맷 라이브러리 (포맷 스튜디오 계획 Phase 1) ─────────────────────
# 프리셋은 저장소 정본(document_formats/*.json → 프론트 번들)이라 API 는 사용자 포맷만 다룬다.
# 프리셋 조회 API 는 실행기(load_format)와 노드 UI 폴백을 위해 함께 둔다.

class DocumentFormatPayload(BaseModel):
    name: str
    spec: dict


def _format_row_public(row) -> dict:
    return {"id": row.id, "name": row.name, "layout": row.layout,
            "spec": row.spec, "updated_at": row.updated_at.isoformat() if row.updated_at else None}


@app.get("/api/formats/presets")
def list_format_presets():
    from documents import format_presets
    return {"formats": format_presets.PRESETS}


class FormatGeneratePayload(BaseModel):
    prompt: str
    layout: str = ""  # "" | "document" | "design"


@app.post("/api/formats/generate")
def generate_document_format(payload: FormatGeneratePayload,
                             user: models.User = Depends(get_current_user_required)):
    """포맷 스튜디오의 AI 생성 — 저장이 아니라 편집기에 로드할 초안을 돌려준다."""
    from documents.format_spec import FormatSpecError
    from format_studio import generate_format_spec
    try:
        spec = generate_format_spec(payload.prompt, payload.layout)
    except FormatSpecError as exc:
        raise HTTPException(status_code=422, detail=f"생성된 포맷이 규칙에 어긋납니다: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"포맷 생성에 실패했습니다: {exc}")
    return {"spec": spec}


# 가져오기 파일은 파싱만 하고 버린다 — 업로드 저장소·쿼터에 남기지 않으므로 상한만 지킨다.
MAX_FORMAT_IMPORT_BYTES = int(os.getenv("MAX_FORMAT_IMPORT_BYTES", 15 * 1024 * 1024))


@app.post("/api/formats/import")
async def import_document_format(file: UploadFile = File(...), use_ai: str = Form("1"),
                                 user: models.User = Depends(get_current_user_required)):
    """서식 파일(.hwpx/.docx) → 스튜디오에 로드할 FormatSpec 초안 (계획 보류 항목 '역변환').

    결정적 추출(format_import)이 정본이고, use_ai 면 그 초안을 근거로 빈칸을 제안한다 —
    AI 가 실패해도 초안은 돌려주되 `ai` 필드에 건너뛴 이유를 명시한다(조용한 실패 금지).
    """
    import tempfile
    from documents.format_import import IMPORT_EXTENSIONS, spec_from_file
    from documents.format_spec import FormatSpecError

    original_name = file.filename or ""
    extension = os.path.splitext(original_name)[1].lower()
    if extension not in IMPORT_EXTENSIONS:
        raise HTTPException(status_code=422,
                            detail=f"지원하지 않는 파일 형식입니다 — {', '.join(IMPORT_EXTENSIONS)} 만 가져올 수 있습니다.")

    data = await file.read(MAX_FORMAT_IMPORT_BYTES + 1)
    if len(data) > MAX_FORMAT_IMPORT_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"파일이 너무 큽니다(상한 {MAX_FORMAT_IMPORT_BYTES // (1024 * 1024)}MB).")
    if not data:
        raise HTTPException(status_code=422, detail="파일이 비어 있습니다.")

    handle, temp_path = tempfile.mkstemp(suffix=extension)
    try:
        with os.fdopen(handle, "wb") as temp_file:
            temp_file.write(data)
        try:
            spec, source_info = spec_from_file(temp_path, original_name=original_name)
        except FormatSpecError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        ai_status = "off"
        if str(use_ai).strip().lower() not in ("0", "false", "no", ""):
            from format_studio import refine_imported_spec
            try:
                spec = refine_imported_spec(spec)
                ai_status = "applied"
            except Exception as exc:
                ai_status = f"skipped: {exc}"
        return {"spec": spec, "source": source_info, "ai": ai_status}
    finally:
        os.unlink(temp_path)


@app.get("/api/formats")
def list_document_formats(user: models.User = Depends(get_current_user_required),
                          db: Session = Depends(get_db)):
    rows = (db.query(models.DocumentFormat)
            .filter(models.DocumentFormat.owner_user_id == user.id)
            .order_by(models.DocumentFormat.updated_at.desc()).all())
    return {"formats": [_format_row_public(r) for r in rows]}


@app.post("/api/formats")
def create_document_format(payload: DocumentFormatPayload,
                           user: models.User = Depends(get_current_user_required),
                           db: Session = Depends(get_db)):
    from documents.format_spec import FormatSpecError, validate_format_spec
    try:
        spec = validate_format_spec({**payload.spec, "name": payload.name})
    except FormatSpecError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    row = models.DocumentFormat(id=f"fmt_{uuid.uuid4().hex}", owner_user_id=user.id,
                                name=payload.name, layout=spec["layout"], spec=spec)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _format_row_public(row)


@app.put("/api/formats/{format_id}")
def update_document_format(format_id: str, payload: DocumentFormatPayload,
                           user: models.User = Depends(get_current_user_required),
                           db: Session = Depends(get_db)):
    from documents.format_spec import FormatSpecError, validate_format_spec
    row = (db.query(models.DocumentFormat)
           .filter(models.DocumentFormat.id == format_id,
                   models.DocumentFormat.owner_user_id == user.id).first())
    if row is None:
        raise HTTPException(status_code=404, detail="포맷을 찾을 수 없습니다.")
    try:
        spec = validate_format_spec({**payload.spec, "name": payload.name})
    except FormatSpecError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    row.name, row.layout, row.spec = payload.name, spec["layout"], spec
    db.commit()
    db.refresh(row)
    return _format_row_public(row)


@app.delete("/api/formats/{format_id}")
def delete_document_format(format_id: str,
                           user: models.User = Depends(get_current_user_required),
                           db: Session = Depends(get_db)):
    deleted = (db.query(models.DocumentFormat)
               .filter(models.DocumentFormat.id == format_id,
                       models.DocumentFormat.owner_user_id == user.id).delete())
    db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="포맷을 찾을 수 없습니다.")
    return {"status": "success"}


@app.post("/api/dry-run")
def dry_run_flow(
    payload: FlowPayload,
    user: models.User = Depends(get_current_user_required),
):
    return dry_run_workflow({"nodes": payload.nodes, "edges": payload.edges}).model_dump()

def is_admin_user(user: models.User) -> bool:
    """관리자 판정 (ADR-0020). `User.role` 을 먼저 보고, 없으면 환경변수로 폴백한다.

    폴백은 한 릴리스 뒤 제거한다 — `ADMIN_EMAILS` 는 그 뒤로 **첫 관리자를 만드는 부트스트랩**
    으로만 남는다(서버 시작 시 승격). 환경변수만 보면 조치 이력에 "누가"를 사용자 id 로 남길 수
    없고, 권한을 바꾸려면 재배포해야 한다.
    """
    import community_safety

    return community_safety.is_admin(user) or community_safety.is_bootstrap_admin(user)


def get_current_staff_user(user: models.User = Depends(get_current_user_required)):
    """moderator 이상. 신고 큐·조치는 admin 이 아니어도 다룰 수 있어야 운영이 굴러간다."""
    import community_safety

    if not community_safety.has_staff_access(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="운영 권한이 필요합니다.")
    return user

def get_current_admin_user(user: models.User = Depends(get_current_user_required)):
    if not is_admin_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized (Admin only)")
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

@app.get("/api/node-definitions")
def get_node_definitions():
    """NodeDefinition v1 정의 목록 (ADR-0005).

    에디터는 빌드 시점에 만들어진 frontend/src/generated/nodeDefinitions.json 을 쓰므로
    이 엔드포인트에 의존하지 않는다. 런타임에 정의가 필요한 소비자 — 목업 서버 탭,
    커뮤니티 노드 검증, 외부 도구 — 를 위한 공개 계약이다.
    """
    return {"status": "success", "definitions": node_definition.definitions_payload()}


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
        return {"access_token": access_token, "user": {"id": user.id, "name": user.name, "email": user.email, "picture": user.picture, "is_admin": is_admin_user(user)}}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google token: {str(e)}")


@app.get("/api/admin/users")
def get_admin_users(user: models.User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "picture": u.picture,
            "token_balance": u.token_balance,
            "is_admin": is_admin_user(u)
        }
        for u in users
    ]

@app.get("/api/admin/statistics")
def get_admin_statistics(user: models.User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    total_users = db.query(models.User).count()
    total_projects = db.query(models.Project).count()
    total_executions = db.query(models.FlowExecutionLog).count()
    return {
        "total_users": total_users,
        "total_projects": total_projects,
        "total_executions": total_executions
    }


@app.get("/api/admin/node-errors")
def get_admin_node_errors(days: int = 7, user: models.User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """NodeError v1 telemetry(ADR-0016) — code/category/effectState 별 발생 수, legacy 문구 비율,
    INTERNAL_UNKNOWN 이 반복되는 노드. 사용자 입력·provider 원문은 컬럼에 없으므로 응답에도 없다."""
    from node_errors import telemetry as node_error_telemetry
    return node_error_telemetry.summary(db, days=max(1, min(int(days), 90)))


@app.get("/api/admin/llm-operations")
def get_admin_llm_operations(
    user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    traces = db.query(models.GenerationTrace).order_by(
        models.GenerationTrace.created_at.desc()
    ).limit(1000).all()
    persistent = summarize_generation_operations(
        traces,
        training_example_count=db.query(models.TrainingExample).count(),
    )
    return {
        "persistent": persistent,
        "runtime_routing": routing_metrics.snapshot(),
        "routing_config": routing_config_snapshot(),
    }


@app.get("/api/admin/llm-health")
def get_admin_llm_health(user: models.User = Depends(get_current_admin_user)):
    return probe_local_provider()

@app.get("/api/admin/feedbacks")
def get_admin_feedbacks(user: models.User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    feedbacks = db.query(models.SiteFeedback).order_by(models.SiteFeedback.created_at.desc()).all()
    return [
        {
            "id": f.id,
            "user_name": f.user.name if f.user else "Anonymous",
            "user_email": f.user.email if f.user else "N/A",
            "scores": f.scores,
            "comment": f.comment,
            "created_at": f.created_at.isoformat() if f.created_at else None
        }
        for f in feedbacks
    ]

class TokenUpdatePayload(BaseModel):
    token_balance: int

@app.put("/api/admin/users/{target_user_id}/token")
def update_user_token(target_user_id: int, payload: TokenUpdatePayload, admin: models.User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    target_user = db.query(models.User).filter(models.User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    target_user.token_balance = payload.token_balance
    db.commit()
    db.refresh(target_user)
    return {"status": "success", "token_balance": target_user.token_balance}

class SudoAuthPayload(BaseModel):
    token: str

@app.post("/api/auth/sudo")
def verify_sudo_token(payload: SudoAuthPayload, db: Session = Depends(get_db)):
    try:
        idinfo = id_token.verify_oauth2_token(
            payload.token, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID, 
            clock_skew_in_seconds=600
        )
        google_id = idinfo['sub']
        user = db.query(models.User).filter(models.User.google_id == google_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
            
        sudo_token = jwt.encode(
            {"user_id": user.id, "sudo": True, "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=15)},
            JWT_SECRET,
            algorithm=JWT_ALGORITHM
        )
        return {"sudo_token": sudo_token}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid Google token for sudo")

def get_sudo_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    if not credentials:
        raise HTTPException(status_code=401, detail="No sudo token")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if not payload.get("sudo"):
            raise HTTPException(status_code=403, detail="Not a sudo token")
        user_id = payload.get("user_id")
        return db.query(models.User).filter(models.User.id == user_id).first()
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid sudo token")

class ApiKeyCreate(BaseModel):
    provider: str
    api_key: str
    # kakao_token 전용(다른 provider는 무시됨) — 카카오 access_token과 함께 받은 refresh_token,
    # 그리고 access_token의 남은 유효시간(초). expires_in을 안 주면 카카오 기본값인 6시간으로 가정한다.
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None

@app.get("/api/credential-providers")
def get_credential_providers(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """자격증명 provider 정본 목록과, 로그인한 사용자의 연결 상태 (ADR-0007).

    비밀값은 담지 않는다 — 무엇을 연결해뒀는지, 자동 갱신이 실제로 동작할 준비가 됐는지만
    알려준다. 그래서 sudo 토큰 없이도 호출할 수 있다(값을 보여주는 /api/user/apikeys 와 다르다).
    """
    registry = connector_providers.registry_payload()
    # 동의 절차로 연결하는 provider 는 콜백 주소를 provider 콘솔에 등록해야 한다. 그 값을
    # 사용자가 추측하게 두면 등록이 어긋나 "redirect_uri_mismatch" 만 보게 된다.
    for entry in registry:
        if entry.get("authorize"):
            entry["callback_url"] = connector_oauth_flow.callback_url(entry["id"])
    payload = {"status": "success", "providers": registry}
    if user:
        payload["connections"] = connector_providers.connection_status(db, user.id)
    return payload


@app.get("/api/user/apikeys")
def get_api_keys(user: models.User = Depends(get_sudo_user), db: Session = Depends(get_db)):
    keys = db.query(models.UserApiKey).filter(models.UserApiKey.user_id == user.id).all()
    def mask_key(k):
        if not k: return ""
        if len(k) > 12:
            return k[:6] + "*" * (len(k) - 10) + k[-4:]
        return "*" * len(k)

    result = []
    for k in keys:
        entry = {"id": k.id, "provider": k.provider, "label": k.label or "", "masked_key": mask_key(decrypt_secret(k.api_key))}
        if k.provider == "kakao_token":
            entry["has_refresh_token"] = bool(decrypt_secret(k.refresh_token))
            entry["token_expires_at"] = k.token_expires_at.isoformat() if k.token_expires_at else None
        result.append(entry)
    return result

@app.post("/api/user/apikeys")
def save_api_key(payload: ApiKeyCreate, user: models.User = Depends(get_sudo_user), db: Session = Depends(get_db)):
    key = db.query(models.UserApiKey).filter(models.UserApiKey.user_id == user.id, models.UserApiKey.provider == payload.provider).first()
    if key:
        key.api_key = encrypt_secret(payload.api_key)
    else:
        key = models.UserApiKey(user_id=user.id, provider=payload.provider, api_key=encrypt_secret(payload.api_key))
        db.add(key)

    if payload.provider == "kakao_token":
        if payload.refresh_token:
            key.refresh_token = encrypt_secret(payload.refresh_token)
        expires_in = payload.expires_in if payload.expires_in else 6 * 3600  # 카카오 access_token 기본 유효시간
        key.token_expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)

    db.commit()
    return {"status": "success"}

@app.delete("/api/user/apikeys/{provider}")
def delete_api_key(provider: str, user: models.User = Depends(get_sudo_user), db: Session = Depends(get_db)):
    db.query(models.UserApiKey).filter(models.UserApiKey.user_id == user.id, models.UserApiKey.provider == provider).delete()
    db.commit()
    return {"status": "success"}


# ── OAuth 인가 코드 흐름 (한국형 노드 계획 Phase 0) ────────────────────────────────────
# 지금까지 OAuth 토큰은 사용자가 provider 콘솔에서 직접 받아 붙여넣었다. 네이버·X·Instagram 을
# 붙이려면 동의 화면으로 보냈다가 받아오는 경로가 필요하고, 그 절차는 connectors/oauth_flow.py
# 한 곳에 있다. 여기는 HTTP 표면만 담당한다.
#
# 시작·해제는 자격증명을 만들고 지우므로 다른 API 키와 같이 sudo 토큰이 필요하다.
# **콜백만 공개다** — provider 가 브라우저를 그리로 보낼 때 Authorization 헤더가 없기 때문이다.
# 그래서 "누구의 토큰인가"는 세션이 아니라 state 가 정한다(oauth_flow.exchange_code 참고).

class OAuthStartPayload(BaseModel):
    # 동의 후 돌아올 우리 화면. 서버가 상대 경로인지 검증한다(열린 리다이렉터 방지).
    return_to: Optional[str] = None


@app.post("/api/oauth/{provider}/start")
def oauth_start(provider: str, payload: OAuthStartPayload = Body(default=OAuthStartPayload()),
                user: models.User = Depends(get_sudo_user), db: Session = Depends(get_db)):
    """동의 화면 URL 을 만들어 돌려준다. 클라이언트가 이 주소로 이동시킨다."""
    try:
        result = connector_oauth_flow.build_authorization_url(
            provider, user.id, db, return_to=payload.return_to
        )
    except connector_oauth_flow.OAuthFlowError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc), "reason": exc.reason})
    return {
        "status": "success",
        "url": result["url"],
        "callback_url": connector_oauth_flow.callback_url(provider),
    }


@app.get("/api/oauth/{provider}/callback")
def oauth_callback(provider: str, request: Request, db: Session = Depends(get_db)):
    """provider 가 사용자를 돌려보내는 자리. 로그인 세션 없이 호출된다."""
    params = request.query_params
    fallback = "/api-center"

    # 사용자가 동의를 거부하면 code 대신 error 가 온다.
    if params.get("error"):
        print(f"[oauth_flow] {provider} 동의 거부 또는 오류: {params.get('error')}")
        return RedirectResponse(f"{fallback}?oauth_error=denied&provider={provider}", status_code=303)

    try:
        result = connector_oauth_flow.exchange_code(
            provider, db, code=params.get("code", ""), state=params.get("state", "")
        )
    except connector_oauth_flow.OAuthFlowError as exc:
        return RedirectResponse(
            f"{fallback}?oauth_error={exc.reason}&provider={provider}", status_code=303
        )

    # 진행 중이 아닌 낡은 왕복 기록을 함께 치운다(표가 무한히 자라지 않게).
    try:
        connector_oauth_flow.purge_expired(db)
    except Exception as exc:
        print(f"[oauth_flow] state 정리 실패(무시): {type(exc).__name__}")

    destination = result.get("return_to") or fallback
    separator = "&" if "?" in destination else "?"
    return RedirectResponse(f"{destination}{separator}connected={provider}", status_code=303)


@app.delete("/api/oauth/{provider}")
def oauth_revoke(provider: str, user: models.User = Depends(get_sudo_user), db: Session = Depends(get_db)):
    """연결을 끊는다. 상대 통보가 실패해도 우리 쪽 값은 지운다."""
    connector_oauth_flow.revoke(provider, user.id, db)
    return {"status": "success"}


# ── Database Query v2: 명명된 자격증명 · 연결 진단 · schema 탐색 · 미리보기 (ADR-0017) ──────
# 자격증명 생성/삭제는 다른 API 키와 같이 sudo 토큰이 필요하다. 목록·연결 테스트·schema·미리보기는
# 비밀값을 돌려주지 않으므로 일반 로그인으로 충분하다(에디터의 노드 UI 가 부른다).
class DatabaseCredentialPayload(BaseModel):
    label: str = ""
    connection_string: str


class DatabasePreviewPayload(BaseModel):
    connection_string: str = "{{API_CENTER:database}}"
    query: str
    parameters: List[Dict[str, Any]] = Field(default_factory=list)
    # Test step 에서 사용자가 직접 넣은 값(source=input 파라미터의 시험용 값 등)
    parameter_values: Dict[str, Any] = Field(default_factory=dict)
    max_rows: int = 50
    timeout_seconds: int = 10
    allowed_schemas: Any = "public"
    output_format: str = "rows"


@app.get("/api/features")
def get_features():
    """클라이언트가 어떤 경로의 UI 를 그릴지 정하는 배포 플래그."""
    import db_query_runtime
    import python_runtime
    return {
        "database_query_v2": db_query_runtime.v2_enabled(),
        "node_error_v1": node_error_runtime.is_enabled(),
        # 꺼져 있으면 편집기가 팔레트에서 pythonNode 를 빼야 한다. 실행 경로는 이 값과 무관하게
        # 서버에서 다시 막으므로, 이건 UI 가 헛수고를 안 하게 하는 힌트다.
        "python_node_enabled": python_runtime.node_enabled(),
    }


@app.get("/api/database/credentials")
def list_database_credentials(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    import database_credentials
    return {"credentials": database_credentials.list_credentials(db, user.id)}


@app.post("/api/database/credentials")
def create_database_credential(payload: DatabaseCredentialPayload, user: models.User = Depends(get_sudo_user), db: Session = Depends(get_db)):
    import database_credentials
    try:
        row = database_credentials.create(db, user.id, label=payload.label, connection_string=payload.connection_string)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    summary = next((c for c in database_credentials.list_credentials(db, user.id) if c["id"] == row.id), None)
    return {"status": "success", "credential": summary}


@app.delete("/api/database/credentials/{credential_id}")
def delete_database_credential(credential_id: int, user: models.User = Depends(get_sudo_user), db: Session = Depends(get_db)):
    import database_credentials
    if not database_credentials.delete(db, user.id, credential_id):
        raise HTTPException(status_code=404, detail="자격증명을 찾을 수 없습니다.")
    return {"status": "success"}


def _owned_database_credential(db, user, credential_id: int):
    import database_credentials
    from credential_crypto import decrypt_secret as _decrypt
    row = database_credentials.get_owned(db, user.id, credential_id)
    if row is None:
        raise HTTPException(status_code=404, detail="자격증명을 찾을 수 없습니다.")
    return row, (_decrypt(row.api_key) or "")


@app.post("/api/database/credentials/{credential_id}/test")
def test_database_credential(credential_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """driver → dns → tcp → auth → readonly_probe 단계별 결과. 원문 예외·URI 는 없다."""
    import database_diagnostics
    _row, secret = _owned_database_credential(db, user, credential_id)
    return database_diagnostics.test_connection(secret, timeout_seconds=5)


@app.get("/api/database/credentials/{credential_id}/schema")
def get_database_schema(credential_id: int, schema: str = "public", refresh: bool = False,
                        user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    import database_diagnostics
    _row, secret = _owned_database_credential(db, user, credential_id)
    return database_diagnostics.fetch_schema(credential_id, secret, schema=schema, refresh=refresh)


@app.post("/api/database/preview")
def preview_database_query(payload: DatabasePreviewPayload, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """저장하지 않고 쿼리를 한 번 실행한다(Test step). 실행 경로·판별기·정책은 워크플로우 실행과 동일하다."""
    import db_query_runtime
    result = db_query_runtime.run_readonly_query_result(
        credential_ref=payload.connection_string, owner_user_id=user.id, db=db,
        query=payload.query, parameters=payload.parameters,
        parameter_overrides=payload.parameter_values or None,
        max_rows=max(1, min(int(payload.max_rows or 50), 200)), timeout_seconds=payload.timeout_seconds,
        allowed_schemas=payload.allowed_schemas, output_format=payload.output_format,
    )
    return {**result.to_dict(), "display": str(result)}

@app.delete("/api/users/me")
async def delete_user_account(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    # 1. Anonymize execution logs
    db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.user_id == user.id).update({models.FlowExecutionLog.user_id: None})
    # Opt-in training candidates and generation prompts must not outlive account deletion.
    db.query(models.TrainingExample).filter(
        models.TrainingExample.user_id == user.id,
    ).delete(synchronize_session=False)
    db.query(models.GenerationTrace).filter(
        models.GenerationTrace.user_id == user.id,
    ).delete(synchronize_session=False)

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
    draft_session_id: Optional[str] = None
    generation_trace_id: Optional[str] = None
    # 낙관적 동시성(ADR-0006). 편집을 시작한 시점의 revision 번호를 같이 보내면, 그 사이에
    # 다른 곳에서 저장된 경우 덮어쓰지 않고 409로 돌려보낸다. 값을 안 보내는 예전
    # 클라이언트는 지금까지처럼 그대로 저장된다(하위 호환).
    base_revision: Optional[int] = None
    # 충돌을 확인하고도 내 변경으로 덮어쓰겠다고 사용자가 선택한 경우.
    force_overwrite: bool = False


def _record_project_trace_adoption(db: Session, payload: ProjectCreate, user_id: int, project_id: int):
    if not payload.generation_trace_id:
        return None
    try:
        return record_trace_adoption(
            db,
            trace_id=payload.generation_trace_id,
            user_id=user_id,
            project_id=project_id,
            saved_graph_data=payload.graph_data or {},
        )
    except Exception as exc:
        db.rollback()
        print(f"Failed to record trace adoption {payload.generation_trace_id}: {exc}")
        return None

@app.get("/api/projects/public")
def get_public_projects(db: Session = Depends(get_db)):
    projects = db.query(models.Project).filter(models.Project.visibility == 'public').all()
    return [{"id": p.id, "title": p.title, "description": p.description, "owner": p.owner.name if p.owner else "Unknown", "updated_at": p.updated_at, "share_token": p.share_token} for p in projects]

@app.get("/api/projects/my")
def get_my_projects(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    projects = db.query(models.Project).filter(models.Project.user_id == user.id).order_by(models.Project.updated_at.desc()).all()
    result = []
    for project in projects:
        graph_data = project.graph_data if isinstance(project.graph_data, dict) else {}
        nodes = graph_data.get("nodes", []) if isinstance(graph_data.get("nodes", []), list) else []
        edges = graph_data.get("edges", []) if isinstance(graph_data.get("edges", []), list) else []
        result.append({
            "id": project.id,
            "title": project.title,
            "description": project.description,
            "visibility": project.visibility,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "share_token": project.share_token,
            "deploy_mode": project.deploy_mode,
            "current_revision": project.current_revision,
            "is_live": bool(graph_data.get("is_live", False)),
            "node_count": len(nodes),
            "edge_count": len(edges),
        })
    return result


def _revision_source(payload: ProjectCreate) -> str:
    """AI 생성 결과를 저장하는 경로면 'ai'. 생성 전후 비교에서 이 값으로 구분한다."""
    return "ai" if payload.generation_trace_id else "user"


def check_node_quotas(user_id: int, new_graph_data: dict, db: Session, exclude_project_id: int = None):
    projects = db.query(models.Project).filter(models.Project.user_id == user_id).all()
    manual_projects = [p for p in projects if not (p.description and p.description.startswith("Auto-generated backend workflow"))]

    total_webhooks = 0
    total_bots = 0
    total_schedules = 0

    for p in manual_projects:
        if exclude_project_id and p.id == exclude_project_id:
            continue
        g_data = p.graph_data if isinstance(p.graph_data, dict) else {}
        nodes = g_data.get("nodes", []) if isinstance(g_data.get("nodes", []), list) else []
        total_webhooks += sum(1 for n in nodes if isinstance(n, dict) and n.get("type") == "webhookNode")
        total_bots += sum(1 for n in nodes if isinstance(n, dict) and n.get("type") in ["telegramNode", "discordNode", "kakaoNode"])
        total_schedules += sum(1 for n in nodes if isinstance(n, dict) and n.get("type") == "schedulerNode")

    new_nodes = new_graph_data.get("nodes", []) if isinstance(new_graph_data.get("nodes", []), list) else []
    new_webhooks = sum(1 for n in new_nodes if isinstance(n, dict) and n.get("type") == "webhookNode")
    new_bots = sum(1 for n in new_nodes if isinstance(n, dict) and n.get("type") in ["telegramNode", "discordNode", "kakaoNode"])
    new_schedules = sum(1 for n in new_nodes if isinstance(n, dict) and n.get("type") == "schedulerNode")

    if total_webhooks + new_webhooks > 2:
        raise HTTPException(status_code=400, detail="Maximum 2 webhooks allowed per user.")
    if total_bots + new_bots > 2:
        raise HTTPException(status_code=400, detail="Maximum 2 bots allowed per user.")
    if total_schedules + new_schedules > 2:
        raise HTTPException(status_code=400, detail="Maximum 2 schedules allowed per user.")

@app.post("/api/projects")
def create_project(payload: ProjectCreate, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    if not (payload.description and payload.description.startswith("Auto-generated backend workflow")):
        manual_projects_count = db.query(models.Project).filter(
            models.Project.user_id == user.id,
            ~models.Project.description.startswith("Auto-generated backend workflow")
        ).count()
        if manual_projects_count >= 5:
            raise HTTPException(status_code=400, detail="Maximum 5 workflows allowed per user.")

    check_node_quotas(user.id, payload.graph_data, db)
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

    # 홈페이지(MainPage)에서 draft-<timestamp> 세션으로 대화하다가 이 워크플로우를 처음 저장하는
    # 경우, 그 draft 세션의 채팅 기록을 새로 생긴 실제 project_id로 옮겨서 에디터에서도 이어서
    # 보이게 한다 (안 옮기면 에디터가 project_id가 달라진 새 세션으로 취급해서 대화 기록이
    # 안 보이는 버그가 생긴다).
    if payload.draft_session_id:
        draft_session = db.query(models.ChatSession).filter(
            models.ChatSession.user_id == user.id,
            models.ChatSession.project_id == payload.draft_session_id
        ).first()
        if draft_session:
            draft_session.project_id = str(project.id)
            db.commit()

    adoption = _record_project_trace_adoption(db, payload, user.id, project.id)

    # 첫 저장도 되돌릴 수 있는 지점으로 남긴다(ADR-0006).
    project_revisions.record_revision(
        db, project, author_user_id=user.id, source=_revision_source(payload)
    )
    db.commit()

    return {
        "status": "success",
        "id": project.id,
        "trace_adoption": adoption,
        "current_revision": project.current_revision,
    }

@app.get("/api/projects/{project_id}")
def get_project(project_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # 권한 판정은 project_access 한 곳이다(ADR-0024) — 흩어져 있던 검사를 여기로 모았다.
    # 개인 프로젝트의 동작은 도입 전과 같고, workspace 멤버가 추가로 통과한다.
    if not project_access.can(db, user, project, project_access.VIEW):
        raise HTTPException(status_code=403, detail="Not authorized to view this project")

    return {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "graph_data": project.graph_data,
        "visibility": project.visibility,
        "deploy_mode": project.deploy_mode,
        "owner_id": project.user_id,
        "owner_name": project.owner.name if project.owner else "Unknown",
        # 클라이언트는 이 값을 들고 있다가 저장할 때 base_revision 으로 돌려보낸다.
        "current_revision": project.current_revision,
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
                if node_url.startswith('http://') or node_url.startswith('https://'):
                    from urllib.parse import urlparse
                    node_url = urlparse(node_url).path

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
                    "nodeId": n.get('id'),
                    "title": p.title,
                    "url": f"http://localhost:8000{node_url}",
                    "status": "Active" if p.graph_data.get("is_live", False) else "Stopped",
                    "lastTriggered": last_triggered,
                    "updatedAt": p.updated_at,
                    "methods": ["GET", "POST"],
                })
                break

    return webhooks

@app.delete("/api/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    # webhook_id는 get_my_webhooks가 만든 합성 id "wh-{projectId}-{nodeId}" 형식이다.
    # 웹훅은 별도 DB 테이블 없이 graph_data 안의 webhookNode 자체이므로, "삭제"는 그 노드와
    # 연결된 엣지를 그래프에서 제거하는 것을 뜻한다 (discordTriggerNode 삭제와 동일한 패턴).
    parts = webhook_id.split("-", 2)
    if len(parts) != 3 or parts[0] != "wh":
        raise HTTPException(status_code=400, detail="Invalid webhook id")
    try:
        project_id = int(parts[1])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook id")
    node_id = parts[2]

    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.graph_data:
        new_data = dict(project.graph_data)
        nodes = new_data.get('nodes', [])
        if not any(n.get('id') == node_id and n.get('type') == 'webhookNode' for n in nodes):
            raise HTTPException(status_code=404, detail="Webhook node not found")
        new_data['nodes'] = [n for n in nodes if n.get('id') != node_id]
        new_data['edges'] = [e for e in new_data.get('edges', []) if e.get('source') != node_id and e.get('target') != node_id]
        project.graph_data = new_data
        flag_modified(project, "graph_data")
        db.commit()

        try:
            scheduler.sync_project_schedule(project_id, project)
        except Exception as e:
            print(f"Failed to sync schedule after webhook delete: {e}")

    return {"status": "success", "message": "Webhook deleted"}

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project_access.can(db, user, project, project_access.DELETE):
        raise HTTPException(status_code=403, detail="Not authorized to delete this project")

    try:
        if scheduler.scheduler.get_job(f"project_{project_id}"):
            scheduler.scheduler.remove_job(f"project_{project_id}")
    except Exception as e:
        print(f"Failed to remove schedule: {e}")

    # Stop bots if running
    discord_bot.stop_discord_bot(project_id)
    try:
        tg_node_id, _ = telegram_bot.find_telegram_trigger_node(project.graph_data or {})
        if tg_node_id:
            tg_token = telegram_bot.resolve_telegram_token(project.graph_data, project.user_id, db)
            telegram_bot.delete_telegram_webhook(tg_token)
    except Exception as e:
        print(f"Failed to delete telegram webhook: {e}")

    # Delete bot logs to avoid IntegrityError
    db.query(models.BotLog).filter(models.BotLog.project_id == project_id).delete(synchronize_session=False)

    db.delete(project)
    db.commit()
    return {"status": "success"}

@app.put("/api/projects/{project_id}")
async def update_project(project_id: int, payload: ProjectCreate, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    check_node_quotas(user.id, payload.graph_data, db, exclude_project_id=project_id)
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project_access.can(db, user, project, project_access.EDIT):
        raise HTTPException(status_code=403, detail="Not authorized to edit this project")

    # 낙관적 동시성 검사(ADR-0006). 예전에는 마지막에 저장한 쪽이 앞선 변경을 조용히
    # 지웠다 — 이제는 덮어쓰기 전에 사용자에게 물어보게 409로 돌려보낸다.
    if payload.base_revision is not None and not payload.force_overwrite:
        if payload.base_revision != project.current_revision:
            raise HTTPException(
                status_code=409,
                detail=project_revisions.conflict_detail(
                    db, project, payload.base_revision, payload.graph_data or {}
                ),
            )

    project.title = payload.title
    project.description = payload.description

    new_graph_data = payload.graph_data or {}
    project.graph_data = new_graph_data
    flag_modified(project, "graph_data")
    project.visibility = payload.visibility

    project_revisions.record_revision(
        db, project, author_user_id=user.id, source=_revision_source(payload)
    )
    db.commit()
    adoption = _record_project_trace_adoption(db, payload, user.id, project_id)
    
    try:
        if isinstance(new_graph_data, dict) and new_graph_data.get("is_live") is True:
            scheduler.sync_project_schedule(project_id, project)
        else:
            scheduler.sync_project_schedule(project_id, project) # sync_project_schedule will remove if not live
    except Exception as e:
        print(f"Failed to sync schedule: {e}")

    # 스케줄과 동일하게, 저장할 때 이미 라이브 상태였다면 (예: 토큰을 방금 고친 경우를 반영해)
    # 봇을 최신 설정으로 재시작한다. start_discord_bot 자체가 "이미 떠 있으면 껐다가 다시 켠다"이므로
    # 매번 불러도 안전하다. 라이브가 아니면 혹시 떠 있던 봇을 정지한다.
    try:
        node_id, _ = discord_bot.find_discord_trigger_node(new_graph_data)
        if node_id and new_graph_data.get("is_live") is True:
            token = discord_bot.resolve_discord_token(new_graph_data, project.user_id, db)
            if token:
                discord_bot.start_discord_bot(project_id, token)
        else:
            # node_id가 없으면(트리거 노드를 캔버스에서 지우고 저장한 경우) is_live 값과 무관하게
            # 정지해야 한다 — 안 그러면 그래프에서 노드가 사라졌는데도 봇 프로세스는 계속 떠서
            # 메시지에 응답하는 상태가 된다. stop_discord_bot은 떠 있는 봇이 없으면 그냥 no-op.
            discord_bot.stop_discord_bot(project_id)
    except Exception as e:
        print(f"Failed to sync discord bot: {e}")

    # 텔레그램도 디스코드와 완전히 동일한 판단 로직 — 트리거 노드가 있고 라이브면 웹훅을
    # (재)등록하고, 없으면(노드가 지워졌거나 라이브가 꺼졌으면) 웹훅을 지운다.
    try:
        tg_node_id, _ = telegram_bot.find_telegram_trigger_node(new_graph_data)
        if tg_node_id and new_graph_data.get("is_live") is True:
            tg_token = telegram_bot.resolve_telegram_token(new_graph_data, project.user_id, db)
            if tg_token:
                telegram_bot.set_telegram_webhook(tg_token, project_id)
        else:
            tg_token = telegram_bot.resolve_telegram_token(new_graph_data, project.user_id, db) if tg_node_id else ""
            if tg_token:
                telegram_bot.delete_telegram_webhook(tg_token)
    except Exception as e:
        print(f"Failed to sync telegram bot: {e}")

    return {
        "status": "success",
        "trace_adoption": adoption,
        "current_revision": project.current_revision,
    }

def _owned_project_or_error(project_id: int, user: models.User, db: Session) -> models.Project:
    """편집 이력은 소유자만 볼 수 있다 — 공개 프로젝트라도 저장 이력까지 공개하지는 않는다."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this project's history")
    return project


@app.get("/api/projects/{project_id}/revisions")
def list_project_revisions(project_id: int, limit: int = 50, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """저장 이력 목록 (ADR-0006). 그래프 본문은 빼고 요약만 담는다."""
    project = _owned_project_or_error(project_id, user, db)
    return {
        "status": "success",
        "current_revision": project.current_revision,
        "revisions": project_revisions.list_revisions(db, project_id, limit=limit),
    }


@app.get("/api/projects/{project_id}/revisions/{revision}")
def get_project_revision(project_id: int, revision: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """특정 시점의 그래프 전체. 두 시점을 받아 클라이언트에서 diff 할 수 있다."""
    _owned_project_or_error(project_id, user, db)
    snapshot = project_revisions.revision_at(db, project_id, revision)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Revision not found")
    return {"status": "success", "revision": project_revisions.revision_to_dict(snapshot, include_graph=True)}


@app.get("/api/projects/{project_id}/revisions/{revision}/diff")
def diff_project_revision(project_id: int, revision: int, against: Optional[int] = None, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """두 시점 사이에 무엇이 바뀌었는지. `against` 를 비우면 현재 상태와 비교한다."""
    project = _owned_project_or_error(project_id, user, db)
    base = project_revisions.revision_at(db, project_id, revision)
    if base is None:
        raise HTTPException(status_code=404, detail="Revision not found")

    if against is None:
        target_graph, target_label = project.graph_data, project.current_revision
    else:
        target = project_revisions.revision_at(db, project_id, against)
        if target is None:
            raise HTTPException(status_code=404, detail="Revision to compare not found")
        target_graph, target_label = target.graph_data, target.revision

    return {
        "status": "success",
        "from_revision": base.revision,
        "to_revision": target_label,
        "diff": project_revisions.diff_graphs(base.graph_data, target_graph),
    }


@app.post("/api/projects/{project_id}/revisions/{revision}/restore")
def restore_project_revision(project_id: int, revision: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """예전 시점으로 되돌린다. 되돌리기 자체도 새 revision 으로 남기므로 이력이 잘리지 않는다."""
    project = _owned_project_or_error(project_id, user, db)
    snapshot = project_revisions.revision_at(db, project_id, revision)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Revision not found")

    project.title = snapshot.title
    project.description = snapshot.description
    project.graph_data = snapshot.graph_data
    flag_modified(project, "graph_data")
    project_revisions.record_revision(db, project, author_user_id=user.id, source="restore")
    db.commit()

    return {
        "status": "success",
        "restored_from": revision,
        "current_revision": project.current_revision,
        "graph_data": project.graph_data,
    }


class MockRunRequest(BaseModel):
    # 저장 전 캔버스 상태로도 돌려볼 수 있어야 한다 — "저장해야 테스트 가능"은 첫 성공까지의
    # 시간을 늘리는 마찰이다. 비우면 저장된 그래프를 쓴다.
    graph_data: Optional[Dict[str, Any]] = None
    entry_node_id: str = ""
    payload: Any = None
    scenario: str = "success"
    scenario_by_node: Dict[str, str] = Field(default_factory=dict)
    # 범위 실행(EDITOR_SHORTCUTS §7.4) — 목업으로 한 노드/구간만 돌린다. start_node_id 는
    # "그 노드부터 컴파일" 이고 entry_node_id(트리거 payload 주입)와는 다른 축이다.
    start_node_id: Optional[str] = None
    stop_node_id: Optional[str] = None
    scope_node_ids: Optional[List[str]] = None
    # 고정 출력(§7.3) — 상류를 다시 부르지 않고 저장해 둔 결과로 대체한다.
    pinned_outputs: Optional[Dict[str, str]] = None
    # start_node_id 로 시작할 때 직전 노드 출력 자리에 넣을 샘플 입력.
    sample_input: Optional[str] = None


@app.get("/api/projects/{project_id}/mock/scenarios")
def get_mock_scenarios(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """이 워크플로우에서 무엇을 목업으로 돌릴 수 있는지 (ADR-0009).

    노드별로 화면을 하드코딩하지 않고, 그래프에 실제로 놓인 노드의 정의에서 읽어낸다.
    """
    project = _owned_project_or_error(project_id, user, db)
    return {"status": "success", **mock_service.describe_graph(project.graph_data)}


@app.post("/api/projects/{project_id}/mock/run")
def run_mock(project_id: int, payload: MockRunRequest, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """실제 자격증명 없이 워크플로우를 끝까지 실행한다 (ADR-0009).

    Live Mode 와 무관하고, 바깥으로 나가는 요청이 하나도 없다. 실패 경로(인증 실패, 호출 한도,
    타임아웃)는 시나리오로 재현하므로 진짜 계정으로는 만들기 어려운 상황도 확인할 수 있다.
    """
    project = _owned_project_or_error(project_id, user, db)
    graph_data = payload.graph_data if payload.graph_data is not None else project.graph_data

    if payload.scenario not in mock_service.SCENARIO_LABELS:
        raise HTTPException(status_code=400, detail=f"알 수 없는 시나리오: {payload.scenario}")

    return {
        "status": "success",
        **mock_service.run(
            graph_data,
            db=db,
            project_id=project.id,
            entry_node_id=payload.entry_node_id,
            payload=payload.payload,
            scenario=payload.scenario,
            scenario_by_node=payload.scenario_by_node,
            start_node_id=payload.start_node_id,
            stop_node_id=payload.stop_node_id,
            scope_node_ids=payload.scope_node_ids,
            pinned_outputs=payload.pinned_outputs,
            sample_input=payload.sample_input,
        ),
    }


@app.post("/api/projects/{project_id}/live")
async def toggle_project_live(project_id: int, payload: dict, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
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
        
    # discordTriggerNode가 있으면 스케줄/웹훅과 동일하게 이 라이브 토글 하나로 봇을 켜고 끈다
    # (예전엔 별도 "배포" 모달에서 discordNode 유무 + graph_data.discord_bot_token으로 판단했다).
    warning = None
    node_id, _ = discord_bot.find_discord_trigger_node(graph_data)
    if node_id:
        if is_live:
            token = discord_bot.resolve_discord_token(graph_data, project.user_id, db)
            if token:
                discord_bot.start_discord_bot(project_id, token)
            else:
                # 토큰이 없으면 라이브 플래그는 켜졌지만 실제 봇은 뜨지 않는다 — 프론트에서
                # "라이브 시작됨" 성공 메시지만 보고 봇이 켜졌다고 착각하지 않도록 경고를 돌려준다.
                warning = "디스코드 봇(시작) 노드에 토큰이 설정되어 있지 않아 봇은 실제로 시작되지 않았습니다. 노드에서 토큰을 입력하거나 API 센터에 연동해주세요."
        else:
            discord_bot.stop_discord_bot(project_id)

    # telegramTriggerNode도 동일한 방식 — 이 라이브 토글 하나로 웹훅이 등록/해제된다.
    tg_node_id, _ = telegram_bot.find_telegram_trigger_node(graph_data)
    if tg_node_id:
        if is_live:
            tg_token = telegram_bot.resolve_telegram_token(graph_data, project.user_id, db)
            if tg_token:
                telegram_bot.set_telegram_webhook(tg_token, project_id)
            elif not warning:
                warning = "텔레그램 봇(시작) 노드에 토큰이 설정되어 있지 않아 봇은 실제로 시작되지 않았습니다. 노드에서 토큰을 입력하거나 API 센터에 연동해주세요."
        else:
            tg_token = telegram_bot.resolve_telegram_token(graph_data, project.user_id, db)
            if tg_token:
                telegram_bot.delete_telegram_webhook(tg_token)

    return {"status": "success", "is_live": is_live, "warning": warning}

@app.post("/api/projects/{project_id}/deploy")
def deploy_project(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    if not project.share_token:
        project.share_token = str(uuid.uuid4())
        db.commit()
    return {"status": "success", "share_token": project.share_token}

@app.get("/api/apps/custom")
def get_custom_apps(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    apps = db.query(models.CustomApp).filter(models.CustomApp.owner_id == user.id).order_by(models.CustomApp.created_at.desc()).all()
    def count_components(items):
        if not isinstance(items, list):
            return 0
        return sum(1 + count_components(item.get("children", [])) for item in items if isinstance(item, dict))

    result = []
    for custom_app in apps:
        combined = custom_app.ui_graph_data or {}
        ui_data = combined.get("ui") if "ui" in combined else combined
        result.append({
            "id": custom_app.id,
            "title": custom_app.title,
            "description": (ui_data or {}).get("description", ""),
            "created_at": custom_app.created_at,
            "updated_at": custom_app.updated_at,
            "component_count": count_components((ui_data or {}).get("components", [])),
            "binding_count": len(custom_app.workflow_mappings or {}),
        })
    return result

@app.delete("/api/apps/custom/{app_id}")
def delete_custom_app(app_id: str, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    custom_app = db.query(models.CustomApp).filter(models.CustomApp.id == app_id, models.CustomApp.owner_id == user.id).first()
    if not custom_app:
        raise HTTPException(status_code=404, detail="Custom app not found")
    db.delete(custom_app)
    db.commit()
    return {"status": "success"}

@app.get("/api/apps/custom/{app_id}")
def get_custom_app(app_id: str, db: Session = Depends(get_db)):
    custom_app = db.query(models.CustomApp).filter(models.CustomApp.id == app_id).first()
    if not custom_app:
        raise HTTPException(status_code=404, detail="Custom app not found")
        
    combined = custom_app.ui_graph_data or {}
    ui_data = combined.get("ui") if "ui" in combined else combined
    logic_data = combined.get("logic") if "logic" in combined else None
        
    return {
        "id": custom_app.id,
        "title": custom_app.title,
        "description": (ui_data or {}).get("description", ""),
        "ui_graph_data": ui_data,
        "logic_graph": logic_data,
        "workflow_mappings": custom_app.workflow_mappings,
        "owner_id": custom_app.owner_id
    }

@app.get("/api/apps/{share_token}")
def get_app_info(share_token: str, request: Request, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.share_token == share_token).first()
    if not project:
        raise HTTPException(status_code=404, detail="App not found")

    # 바로 아래 /execute 는 공개 범위를 확인하는데 이 GET 은 하지 않아서, 링크만 있으면 누구나
    # graph_data 전체(봇 토큰이 평문으로 사는 곳)를 받아갈 수 있었다 — 실행은 막고 열람은 열려
    # 있던 비대칭이다. 같은 판정을 여기에도 적용한다.
    _require_shared_app_visibility(db, request, project)

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


def _user_from_request(db, request: Request):
    """Authorization 헤더가 있으면 사용자를 돌려준다(없거나 잘못되면 None). 공유 링크 경로는
    익명 접근이 정상이라 의존성으로 강제하지 않고 여기서 옵션으로 읽는다."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    try:
        payload_jwt = jwt.decode(auth_header.split(" ")[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None
    return db.query(models.User).filter(models.User.id == payload_jwt.get("user_id")).first()


def _require_shared_app_visibility(db, request: Request, project):
    """공유 링크로 열리는 앱의 공개 범위 판정. GET(조회)과 POST(실행)가 같은 규칙을 보게 한다."""
    user = _user_from_request(db, request)
    if project.visibility == 'private' and (not user or project.user_id != user.id):
        raise HTTPException(status_code=403, detail="Authentication required for private app")
    if project.visibility == 'friends':
        if not user or (project.user_id != user.id and not db.query(models.Friendship).filter(
                models.Friendship.user_id == project.user_id,
                models.Friendship.friend_id == user.id).first()):
            raise HTTPException(status_code=403, detail="Friends-only access required")
    return user

@app.post("/api/apps/{share_token}/execute")
def execute_app(share_token: str, request: Request, payload: AppExecutePayload = None, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.share_token == share_token).first()
    if not project:
        raise HTTPException(status_code=404, detail="App not found")
    
    # GET /api/apps/{token} 과 같은 판정을 쓴다(두 곳이 갈라지면 한쪽이 다시 열린다).
    user = _require_shared_app_visibility(db, request, project)

    owner = db.query(models.User).filter(models.User.id == project.user_id).first()
    if owner and owner.token_balance <= 0:
        raise HTTPException(status_code=403, detail="앱 소유자의 토큰이 모두 소진되어 앱을 실행할 수 없습니다.")

    nodes = project.graph_data.get('nodes', [])
    edges = project.graph_data.get('edges', [])
    
    try:
        # 입력 키 이름은 앱 제작자가 정하므로 **kwargs 로 펼치면 안 된다(ADR 없음 — 버그 수정).
        user_inputs = dict(payload.inputs) if payload and payload.inputs else {}
        result_text, tokens, logs = run_workflow(nodes, edges, db=db, session_id='app_runner', project_id=project.id, user_inputs=user_inputs)
        
        db_log = record_usage(
            db,
            billable_user_id=project.user_id,
            actor_user_id=user.id if user else None,
            project_id=project.id,
            token_usage=tokens,
            payload="App Runner Execution",
            result=result_text,
            event_type=EVENT_WORKFLOW_EXECUTION,
            outcome=outcome_from_result(result_text),
            trigger_type="shared_app",
        )
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

class ProjectRunPayload(BaseModel):
    input_text: Optional[str] = None
    inputs: Optional[Dict[str, Any]] = None

@app.post("/api/projects/{project_id}/run")
def run_project_workflow(project_id: int, request: Request, payload: Optional[ProjectRunPayload] = None, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    user = None
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(" ")[1]
        try:
            payload_jwt = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user = db.query(models.User).filter(models.User.id == payload_jwt.get("user_id")).first()
        except:
            pass

    # 공개 앱은 링크를 받은 사람이 로그인 없이 실행하는 것이 기능이므로 익명을 허용하고,
    # private/friends 는 RUN 권한을 요구한다. 검사가 없어서 정수 id 만으로 남의 워크플로우를
    # 실행할 수 있었고(요금·발송·DB 변경이 소유자 몫으로 일어난다) 로그의 actor 도 비어 있었다.
    if not _can_run_project(db, user, project):
        if not project_access.can(db, user, project, project_access.VIEW):
            raise HTTPException(status_code=404, detail="Project not found")
        raise HTTPException(status_code=403, detail="Not authorized to run this project")

    owner = db.query(models.User).filter(models.User.id == project.user_id).first()
    if owner and owner.token_balance <= 0:
        raise HTTPException(status_code=403, detail="프로젝트 소유자의 토큰이 모두 소진되었습니다.")

    nodes = project.graph_data.get('nodes', [])
    edges = project.graph_data.get('edges', [])
    
    # 입력 키 이름은 앱 제작자가 정한다 — 'db'/'session_id'/'project_id' 같은 이름이 오면
    # **kwargs 로 펼칠 때 TypeError 가 나서 실행이 통째로 500 으로 죽었다.
    user_inputs = {}
    if payload:
        if payload.inputs:
            user_inputs.update(payload.inputs)
            first_value = next(iter(payload.inputs.values()), None)
            if first_value is not None:
                user_inputs.setdefault('input_text', first_value)
                user_inputs.setdefault('text', first_value)
                user_inputs.setdefault('default_input', first_value)
        if payload.input_text:
            user_inputs['default_input'] = payload.input_text
            user_inputs.setdefault('input_text', payload.input_text)
            user_inputs.setdefault('text', payload.input_text)

    try:
        result_text, tokens, logs = run_workflow(nodes, edges, db=db, session_id='custom_app_run', project_id=project.id, user_inputs=user_inputs)
        
        record_usage(
            db,
            billable_user_id=project.user_id,
            actor_user_id=user.id if user else None,
            project_id=project.id,
            token_usage=tokens,
            payload="Custom App Execution",
            result=result_text,
            event_type=EVENT_WORKFLOW_EXECUTION,
            outcome=outcome_from_result(result_text),
            trigger_type="custom_app",
        )
        db.commit()
        return {"status": "success", "result": result_text, "tokens": tokens, "logs": logs}
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
        'gpt-4o-mini': 16384,
        'gpt-5.4-mini': 16384,
        'gpt-5.6': 16384,
    }
    
    for node in payload.nodes:
        if node.get('type') in ['llmNode', 'promptNode']:
            text = node.get('data', {}).get('systemPrompt', '') + " " + node.get('data', {}).get('userPrompt', '')
            tokens = len(encoding.encode(text)) if text else 0
            
            max_out = 0
            if node.get('type') == 'llmNode':
                model = node.get('data', {}).get('model', 'gpt-4o-mini')
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
def execute_flow(payload: FlowPayload, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user_required)):
    """
    Receives graph data from frontend, runs LangGraph logic,
    saves execution to DB, and returns the result.
    """
    if user.token_balance <= 0:
        raise HTTPException(status_code=403, detail="토큰을 모두 소진하여 실행할 수 없습니다. 토큰을 충전해 주세요.")

    # payload.project_id 는 자유 입력이고, run_workflow 는 이 값으로 **프로젝트 소유자의 자격증명을
    # 복호화**한다(graph.py 의 credential_owner). 검사가 없어서 비로그인 요청이 남의 project_id 를
    # 실어 보내면 그 사람의 DB·카카오·메일 자격증명으로 실행됐다(2026-08-31).
    # 권한이 없으면 조용히 익명 실행으로 강등하지 않고 거절한다 — 실패를 크게 내는 편이 안전하다.
    if payload.project_id:
        target = db.query(models.Project).filter(models.Project.id == payload.project_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="Project not found")
        _require_project_action(db, user, target, project_access.RUN)

    # 요청 자체가 잘못된 경우는 try 밖에서 막는다 — 아래 except 가 잡으면 400 이 200 + 오류
    # 문자열로 뭉개져 클라이언트가 "실행이 실패했다" 와 "요청이 틀렸다" 를 구분할 수 없다.
    node_ids = {str(n.get("id")) for n in payload.nodes}
    entry_kwargs = {}
    if payload.entry_node_id:
        if str(payload.entry_node_id) not in node_ids:
            raise HTTPException(status_code=400, detail="entry_node_id가 그래프에 없습니다.")
        entry_kwargs = {"entry_node_id": payload.entry_node_id, "approval_payload": payload.entry_input or ""}
    if payload.stop_node_id and str(payload.stop_node_id) not in node_ids:
        raise HTTPException(status_code=400, detail="stop_node_id가 그래프에 없습니다.")
    if payload.scope_node_ids:
        unknown = [nid for nid in payload.scope_node_ids if str(nid) not in node_ids]
        if unknown:
            raise HTTPException(status_code=400, detail=f"scope_node_ids에 그래프에 없는 노드가 있습니다: {unknown[0]}")

    # 1. Run LangGraph
    try:
        result_text, tokens, logs = run_workflow(
            payload.nodes, payload.edges, db=db, session_id='editor', project_id=payload.project_id,
            stop_node_id=payload.stop_node_id, scope_node_ids=payload.scope_node_ids,
            pinned_outputs=payload.pinned_outputs,
            **({"approval_decisions": payload.approval_decisions} if payload.approval_decisions else {}),
            **entry_kwargs,
        )
        
        # Check if run_workflow returned an error string
        if "► Flow 1 Error:" in result_text or "Error calling model" in result_text:
            if "RESOURCE_EXHAUSTED" in result_text or "429" in result_text or "Quota exceeded" in result_text:
                result_text = "❌ AI API 크레딧이 소진되었습니다. AI Studio 또는 OpenAI에서 크레딧을 충전해 주세요."
            elif "AuthenticationError" in result_text or "401" in result_text or "API_KEY_INVALID" in result_text:
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
        if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg or "Quota exceeded" in error_msg:
            result_text = "❌ AI API 크레딧이 소진되었습니다. AI Studio 또는 OpenAI에서 크레딧을 충전해 주세요."
        elif "AuthenticationError" in error_msg or "401" in error_msg or "API_KEY_INVALID" in error_msg:
            result_text = "❌ AI API 키가 유효하지 않습니다. .env 파일의 API 키를 확인해 주세요."
        elif "Network" in error_msg or "Connection" in error_msg:
            result_text = f"❌ 네트워크 오류가 발생했습니다: {error_msg}"
        else:
            result_text = f"❌ 워크플로우 실행 중 오류가 발생했습니다: {error_msg}"
    
    import json
    # 2. Save log to PostgreSQL (or SQLite fallback)
    try:
        # 성공/실패는 실행 로그의 구조화 오류(NodeError v1)로 판정한다 — 결과 문자열 검색은
        # legacy 문구가 남은 경로의 fallback 으로만 남아 있다(ADR-0016, node_errors.runtime).
        flow_status = node_error_runtime.flow_outcome(result_text, logs)
        
        db_log = record_usage(
            db,
            billable_user_id=user.id if user else None,
            actor_user_id=user.id if user else None,
            project_id=payload.project_id,
            token_usage=tokens if isinstance(tokens, dict) else None,
            payload=json.dumps(payload.dict()),
            result=result_text,
            event_type=EVENT_WORKFLOW_EXECUTION,
            outcome=flow_status,
            trigger_type="editor",
            error_message=result_text if flow_status == "error" else None,
        )
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
                error_message=step.get('error_message'),
                # telemetry 컬럼 — code/category/effectState/legacy 여부만(ADR-0016 ERROR-4.3)
                **node_error_runtime.step_columns(step),
            )
            db.add(node_log)
            
        db.commit()
        db.refresh(db_log)
    except Exception as e:
        print(f"Failed to save log to DB: {e}")
        db.rollback()

    # 3. Return response to frontend
    # 승인 대기로 멈춘 실행이면 프론트가 즉석 승인 UI(견본 미리보기 + 승인/거절)를 띄울 수
    # 있도록 요청 상세를 함께 돌려준다(ADR-0015).
    approval_request = None
    for step in logs:
        if step.get("approval_request_id"):
            import approval_service
            row = db.query(models.ApprovalRequest).filter(
                models.ApprovalRequest.request_id == step["approval_request_id"],
            ).first()
            if row:
                approval_request = approval_service.request_to_dict(row, include_full_payload=True)
            break
    # 구조화 오류 필드(ADR-0016): error_schema, node_error_v1(클라이언트 표시 플래그), outcome, errors[].
    # 기존 result 문자열은 이행기 표시용으로 함께 제공한다.
    return {"status": "success", "result": result_text, "token_usage": tokens, "logs": logs,
            "approval_request": approval_request,
            **node_error_runtime.response_fields(result_text, logs)}


# ── 사용자 승인 요청 (ADR-0015) ─────────────────────────────────────────
class ApprovalDecisionPayload(BaseModel):
    decision: str  # approve | reject
    comment: Optional[str] = ""


@app.get("/api/approvals")
def list_approvals(status: Optional[str] = None, db: Session = Depends(get_db), user: models.User = Depends(get_current_user_required)):
    import approval_service
    query = db.query(models.ApprovalRequest).filter(models.ApprovalRequest.user_id == user.id)
    if status:
        query = query.filter(models.ApprovalRequest.status == status)
    rows = query.order_by(models.ApprovalRequest.created_at.desc()).limit(100).all()
    pending_count = db.query(models.ApprovalRequest).filter(
        models.ApprovalRequest.user_id == user.id,
        models.ApprovalRequest.status == "pending",
    ).count()
    return {
        "requests": [approval_service.request_to_dict(row) for row in rows],
        "pending_count": pending_count,
    }


@app.get("/api/approvals/count")
def count_pending_approvals(db: Session = Depends(get_db), user: models.User = Depends(get_current_user_required)):
    count = db.query(models.ApprovalRequest).filter(
        models.ApprovalRequest.user_id == user.id,
        models.ApprovalRequest.status == "pending",
    ).count()
    return {"count": count}


@app.get("/api/approvals/{request_id}")
def get_approval(request_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user_required)):
    import approval_service
    row = db.query(models.ApprovalRequest).filter(
        models.ApprovalRequest.request_id == request_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="승인 요청을 찾을 수 없습니다.")
    if row.user_id != user.id:
        raise HTTPException(status_code=403, detail="이 승인 요청을 볼 권한이 없습니다.")
    return approval_service.request_to_dict(row, include_full_payload=True)


@app.post("/api/approvals/{request_id}/decide")
def decide_approval(request_id: str, payload: ApprovalDecisionPayload, db: Session = Depends(get_db), user: models.User = Depends(get_current_user_required)):
    """승인/거절을 기록하고 중단 지점부터 실행을 재개한다. 결정은 한 번만 유효하다."""
    import json as _json

    import approval_service
    try:
        request, result_text, tokens, logs = approval_service.decide_and_resume(
            db, request_id=request_id, actor_user_id=user.id,
            decision=payload.decision, comment=payload.comment or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    try:
        record_usage(
            db,
            billable_user_id=request.user_id,
            actor_user_id=user.id,
            project_id=request.project_id,
            token_usage=tokens if isinstance(tokens, dict) else None,
            payload=_json.dumps({"approval_request_id": request.request_id, "decision": payload.decision}),
            result=result_text,
            event_type=EVENT_WORKFLOW_EXECUTION,
            trigger_type="approval_resume",
        )
        db.commit()
    except Exception as exc:
        print(f"Failed to record approval resume usage: {exc}")
        db.rollback()

    # 재개 후 다음 승인 노드에서 다시 멈췄으면(연쇄 승인) 그 요청 상세도 함께 돌려준다.
    next_approval = None
    for step in logs:
        if step.get("approval_request_id"):
            row = db.query(models.ApprovalRequest).filter(
                models.ApprovalRequest.request_id == step["approval_request_id"],
            ).first()
            if row:
                next_approval = approval_service.request_to_dict(row, include_full_payload=True)
            break

    return {
        "status": "success",
        "request": approval_service.request_to_dict(request),
        "result": result_text,
        "token_usage": tokens,
        "logs": logs,
        "approval_request": next_approval,
    }


class EvaluatePayload(BaseModel):
    project_id: int
    title: str = ""
    description: str = ""
    graph_data: Dict[str, Any]

@app.post("/api/evaluate")
async def evaluate_project(payload: EvaluatePayload, user: models.User = Depends(get_current_staff_user), db: Session = Depends(get_db)):
    if user and user.token_balance <= 0:
        raise HTTPException(status_code=403, detail="토큰을 모두 소진하여 AI를 사용할 수 없습니다.")
    import evaluator
    try:
        report = await evaluator.run_evaluation_pipeline(
            project_id=payload.project_id,
            title=payload.title,
            description=payload.description,
            nodes=payload.graph_data.get('nodes', []),
            edges=payload.graph_data.get('edges', []),
            db=db,
            user_id=user.id if user else None,
        )

        return {"status": "success", "report": report}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class EvaluateAutofixPayload(EvaluatePayload):
    threshold: int = 70
    max_attempts: int = 3

@app.post("/api/evaluate/autofix")
async def evaluate_project_with_autofix(payload: EvaluateAutofixPayload, user: models.User = Depends(get_current_staff_user), db: Session = Depends(get_db)):
    """평가 -> 기준 미달 시 개선 제안을 메타 에이전트에 넣어 자동 수정 -> 재평가를 반복한다."""
    if user and user.token_balance <= 0:
        raise HTTPException(status_code=403, detail="토큰을 모두 소진하여 AI를 사용할 수 없습니다.")
    import evaluator
    try:
        report = await evaluator.run_evaluation_with_autofix(
            project_id=payload.project_id,
            title=payload.title,
            description=payload.description,
            nodes=payload.graph_data.get('nodes', []),
            edges=payload.graph_data.get('edges', []),
            db=db,
            user_id=user.id if user else None,
            threshold=payload.threshold,
            max_attempts=payload.max_attempts,
        )
        if report is None or "error" in report:
            return {"status": "error", "message": (report or {}).get("error", "평가 실패")}

        autofix_tokens = report.get("autofix_token_usage", {}).get("total_tokens", 0)
        if user and autofix_tokens > 0:
            record_usage(
                db,
                billable_user_id=user.id,
                actor_user_id=user.id,
                project_id=payload.project_id,
                token_usage=report.get("autofix_token_usage"),
                payload="Evaluation Autofix",
                result=f"Attempts: {len(report.get('attempts', []))}",
                event_type=EVENT_WORKFLOW_GENERATION,
                trigger_type="evaluation_autofix",
            )
            db.commit()

        return {"status": "success", "report": report}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/evaluate/cases")
def get_eval_cases():
    import evaluation
    return evaluation.get_evaluation_catalog()

@app.get("/api/evaluate/run")
async def run_eval(ids: str = None, profile: str = None, refresh: bool = False, user: models.User = Depends(get_current_staff_user)):
    import evaluation
    selected = ids.split(",") if ids else None
    return StreamingResponse(
        evaluation.run_evaluation_suite(
            selected,
            profile=profile,
            use_cache=not refresh,
        ),
        media_type="text/event-stream",
    )

# ── 사이트(제품) 사용자 평가 ─────────────────────────────────────────────
# 워크플로우 하나를 채점하는 /api/evaluate와는 별개로, 서비스 자체에 대한 사용자 만족도
# 설문(1~5점, 문항별)을 받는다.
#
# **문항 정본은 여기 하나뿐이다.** 예전에는 프론트(SiteFeedbackWidget)가 같은 목록을 따로
# 들고 있어서 한쪽만 고치면 조용히 갈라졌다 — 이제 /api/site-feedback/questions 로 내려준다.
#
# 문구는 개발 용어를 걷어내고 **처음 온 사람이 바로 답할 수 있는 말**로 쓴다. 한 화면에
# 네 문항씩 보여주므로 구획(section)마다 정확히 네 개를 둔다.
SITE_FEEDBACK_SECTIONS = [
    {
        "id": "make",
        "title": "자동화 만들기",
        "hint": "하고 싶은 일을 적어서 자동화를 만들어 본 경험에 대한 질문이에요.",
        "questions": [
            {"key": "gen_intent_match", "title": "말한 대로 만들어졌나요?",
             "help": "원하는 일을 적었을 때 그에 맞는 자동화가 나왔는지"},
            {"key": "gen_logic_match", "title": "순서가 자연스러웠나요?",
             "help": "만들어진 단계가 실제로 일하는 순서와 맞았는지"},
            {"key": "gen_edit_convenience", "title": "고치기 쉬웠나요?",
             "help": "만들어진 내용을 원하는 대로 바꾸기 편했는지"},
            {"key": "gen_detail_completeness", "title": "빠뜨린 게 없었나요?",
             "help": "조건을 여러 개 말했을 때 하나도 빠지지 않고 들어갔는지"},
        ],
    },
    {
        "id": "screen",
        "title": "화면과 사용 편의",
        "hint": "화면을 보고 쓰는 동안 어땠는지에 대한 질문이에요.",
        "questions": [
            {"key": "ux_intuitiveness", "title": "처음에도 쓸 만했나요?",
             "help": "설명을 따로 안 봐도 어디를 눌러야 할지 알 수 있었는지"},
            {"key": "ux_visual_clarity", "title": "한눈에 들어왔나요?",
             "help": "만든 자동화가 어떻게 흘러가는지 화면에서 잘 보였는지"},
            {"key": "ux_menu_layout", "title": "찾던 기능이 있을 만한 자리에 있었나요?",
             "help": "메뉴와 버튼 위치 때문에 헤매지 않았는지"},
            {"key": "ux_customization", "title": "내게 맞게 바꿀 수 있었나요?",
             "help": "어두운 화면처럼 보기 편한 방식으로 맞출 수 있었는지"},
        ],
    },
    {
        "id": "run",
        "title": "실행과 연결",
        "hint": "만든 자동화를 실제로 돌려 본 경험에 대한 질문이에요.",
        "questions": [
            {"key": "perf_speed", "title": "기다리는 시간이 짧았나요?",
             "help": "실행할 때 답답하지 않았는지"},
            {"key": "perf_stability", "title": "도중에 멈추지 않았나요?",
             "help": "쓰는 중에 갑자기 오류가 나거나 멈추지 않았는지"},
            {"key": "perf_error_clarity", "title": "문제가 생겼을 때 이해됐나요?",
             "help": "오류 안내를 보고 무엇을 고쳐야 할지 알 수 있었는지"},
            {"key": "integration_smoothness", "title": "쓰던 서비스와 잘 이어졌나요?",
             "help": "메일·메신저·문서 같은 외부 서비스 연결이 매끄러웠는지"},
        ],
    },
]

# 요약·검증에 쓰는 평평한 목록. 관리 화면에서 문항을 알아볼 수 있게 구획 이름을 붙여 둔다.
SITE_FEEDBACK_QUESTIONS = {
    question["key"]: f'[{section["title"]}] {question["title"]}'
    for section in SITE_FEEDBACK_SECTIONS
    for question in section["questions"]
}

class SiteFeedbackPayload(BaseModel):
    scores: Dict[str, int]
    comment: Optional[str] = None

@app.get("/api/site-feedback/questions")
def get_site_feedback_questions():
    """문항 정본. 인증 없이도 볼 수 있다 — 안에 든 게 설문 문구뿐이다."""
    return {"status": "success", "sections": SITE_FEEDBACK_SECTIONS}

@app.get("/api/site-feedback/me")
def get_my_site_feedback(user: Optional[models.User] = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """이미 냈는지 여부. 로그인하지 않았으면 판단할 근거가 없으므로 False 다."""
    if not user:
        return {"submitted": False}
    submitted = db.query(models.SiteFeedbackSubmitter).filter(
        models.SiteFeedbackSubmitter.user_id == user.id).first() is not None
    return {"submitted": submitted}

@app.post("/api/site-feedback")
def submit_site_feedback(payload: SiteFeedbackPayload,
                         user: models.User = Depends(get_current_user_required),
                         db: Session = Depends(get_db)):
    """평가는 **계정당 한 번**이다. 내용은 그대로 익명으로 저장한다.

    예전에는 인증 자체가 없어 누구인지 알 수 없었고, 그래서 같은 사람이 몇 번이든 낼 수
    있었다. 지금은 로그인을 요구해 "냈다"는 사실만 별도 표에 적고, 평가 내용에는 여전히
    user_id 를 남기지 않는다(models.SiteFeedbackSubmitter 주석 참고).
    """
    unknown_keys = set(payload.scores.keys()) - set(SITE_FEEDBACK_QUESTIONS.keys())
    if unknown_keys:
        raise HTTPException(status_code=400, detail=f"알 수 없는 문항: {sorted(unknown_keys)}")
    for key, val in payload.scores.items():
        if not isinstance(val, int) or not (1 <= val <= 5):
            raise HTTPException(status_code=400, detail=f"{key}의 점수는 1~5 사이 정수여야 합니다")
    # 문항을 전부 "잘 모르겠어요"로 넘겨 빈 응답이 쌓이는 것은 막는다.
    if not payload.scores:
        raise HTTPException(status_code=400, detail="점수를 매긴 문항이 하나도 없습니다.")

    if db.query(models.SiteFeedbackSubmitter).filter(
            models.SiteFeedbackSubmitter.user_id == user.id).first():
        raise HTTPException(status_code=409, detail="이미 평가를 제출하셨습니다.")

    db.add(models.SiteFeedback(user_id=None, scores=payload.scores, comment=payload.comment))
    db.add(models.SiteFeedbackSubmitter(user_id=user.id,
                                        submitted_on=datetime.date.today()))
    try:
        db.commit()
    except IntegrityError:
        # 위의 조회와 커밋 사이에 다른 탭이 먼저 넣은 경우. 막는 것은 기본키이지 위 조회가 아니다.
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 평가를 제출하셨습니다.")
    return {"status": "success"}

@app.get("/api/site-feedback/summary")
def get_site_feedback_summary(db: Session = Depends(get_db)):
    """문항별 평균 점수 + 응답 수. 관리 목적 — 인증 없이도 조회 가능(민감 정보 없음)."""
    rows = db.query(models.SiteFeedback).all()
    totals: Dict[str, list] = {k: [] for k in SITE_FEEDBACK_QUESTIONS}
    for r in rows:
        for k, v in (r.scores or {}).items():
            if k in totals:
                totals[k].append(v)
    summary = {
        k: {
            "question": SITE_FEEDBACK_QUESTIONS[k],
            "average": round(sum(vs) / len(vs), 2) if vs else None,
            "count": len(vs),
        }
        for k, vs in totals.items()
    }
    return {"status": "success", "response_count": len(rows), "questions": summary}


@app.get("/api/projects/{project_id}/runs")
def get_project_runs(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user_required)):
    # Verify project access
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # 실행 결과는 공개 범위로 열지 않는다. 예전에는 세 라우트가 각자 visibility 를 손으로 보면서
    # public 을 무검사 통과시켜, 로그인만 하면 **남의 공개 프로젝트의 실행 결과 전문**(run.result 와
    # 전 노드 result_data)을 읽을 수 있었다. 공개는 '그래프를 보여준다'는 뜻이지 '그 사람의 데이터를
    # 보여준다'는 뜻이 아니다.
    #
    # RUN 등급으로 판정한다 — project_access.can 의 3단계(공개 범위)는 VIEW 만 주므로 public·friends
    # 로는 절대 통과하지 못하고, 소유자와 workspace 의 runner 이상만 통과한다.
    _require_project_action(db, user, project, project_access.RUN)
        
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

@app.get("/api/projects/{project_id}/evaluations")
def get_project_evaluations(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user_required)):
    # Verify project access
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # 실행 결과는 공개 범위로 열지 않는다. 예전에는 세 라우트가 각자 visibility 를 손으로 보면서
    # public 을 무검사 통과시켜, 로그인만 하면 **남의 공개 프로젝트의 실행 결과 전문**(run.result 와
    # 전 노드 result_data)을 읽을 수 있었다. 공개는 '그래프를 보여준다'는 뜻이지 '그 사람의 데이터를
    # 보여준다'는 뜻이 아니다.
    #
    # RUN 등급으로 판정한다 — project_access.can 의 3단계(공개 범위)는 VIEW 만 주므로 public·friends
    # 로는 절대 통과하지 못하고, 소유자와 workspace 의 runner 이상만 통과한다.
    _require_project_action(db, user, project, project_access.RUN)
        
    evals = db.query(models.EvaluationLog).filter(models.EvaluationLog.project_id == project_id).order_by(models.EvaluationLog.created_at.desc()).limit(100).all()
    
    return [
        {
            "id": e.id,
            "score": e.score,
            "test_case_count": e.test_case_count,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "report": e.report
        } for e in evals
    ]


@app.get("/api/projects/{project_id}/generation-traces")
def get_project_generation_traces(
    project_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user_required),
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view generation traces")

    safe_limit = max(1, min(limit, 100))
    traces = db.query(models.GenerationTrace).filter(
        models.GenerationTrace.project_id == project_id,
    ).order_by(models.GenerationTrace.created_at.desc()).limit(safe_limit).all()
    return [trace_to_dict(trace) for trace in traces]

@app.get("/api/runs/{run_id}")
def get_run_details(run_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user_required)):
    run = db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    project = db.query(models.Project).filter(models.Project.id == run.project_id).first()
    # 실행 결과는 공개 범위로 열지 않는다. 예전에는 세 라우트가 각자 visibility 를 손으로 보면서
    # public 을 무검사 통과시켜, 로그인만 하면 **남의 공개 프로젝트의 실행 결과 전문**(run.result 와
    # 전 노드 result_data)을 읽을 수 있었다. 공개는 '그래프를 보여준다'는 뜻이지 '그 사람의 데이터를
    # 보여준다'는 뜻이 아니다.
    #
    # RUN 등급으로 판정한다 — project_access.can 의 3단계(공개 범위)는 VIEW 만 주므로 public·friends
    # 로는 절대 통과하지 못하고, 소유자와 workspace 의 runner 이상만 통과한다.
    if project:
        _require_project_action(db, user, project, project_access.RUN)
    else:
        # 프로젝트가 없는 고아 로그(삭제된 프로젝트, project_id NULL). 예전에는 위 `if project:` 를
        # 그냥 통과해 로그인한 아무 계정에게나 run.result 전문과 전 노드 result_data 가 열렸다.
        # fail-closed 로 뒤집는다 — 로그를 소유한 본인만 열람할 수 있다.
        owner_ids = {run.billable_user_id, run.user_id, run.actor_user_id}
        if user.id not in owner_ids:
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

import asyncio
from starlette.concurrency import run_in_threadpool

def is_app_creation_intent(message: str, target_type: Optional[str] = "auto") -> bool:
    if target_type == "app":
        return True
    if target_type == "workflow":
        return False
    
    msg = message.lower().strip()
    
    app_keywords = [
        "앱 만들어", "앱 생성", "앱 구축", "앱 개발", "앱 제작", "앱을 만들어",
        "어플 만들어", "어플 생성", "어플 개발", "어플 제작", "어플을 만들어",
        "웹앱", "웹 앱", "웹어플", "웹 어플", "대시보드 앱", "폼 앱", "입력 폼",
        "설문조사 앱", "할 일 앱", "todo 앱", "출퇴근 앱", "근태 앱",
        "등록 폼", "신청 폼", "접수 폼", "작성 폼", "입력 화면",
        "ui 만들어", "ui 앱", "화면 만들어", "인터페이스 만들어",
        "custom app", "web application", "create an app", "build an app"
    ]
    if any(k in msg for k in app_keywords):
        return True
        
    import re
    if re.search(r'([가-힣a-zA-Z0-9]+(앱|어플|웹앱|web\s*app))\s*(만들어|생성|제작|구축|개발|디자인)', msg):
        return True
        
    return False

@app.post("/api/chat")
async def chat_with_agent(payload: ChatPayload, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """
    자연어로 flow(graph_data) 또는 커스텀 앱(UI + Blueprint Logic + Backend Workflow)을 생성/수정하는 챗봇.
    사용자의 요청이 '앱'을 구축하려는 의도인 경우 AI 앱 빌더 에이전트(app_agent)를 통해
    UI 컴포넌트와 인터랙션 로직, 백엔드 워크플로우를 한 번에 생성합니다.
    """
    if user and user.token_balance <= 0:
        raise HTTPException(status_code=403, detail="토큰을 모두 소진하여 AI를 사용할 수 없습니다.")

    generation_trace_id = str(uuid.uuid4())
    trace_started = time.perf_counter()
    numeric_project_id = int(payload.project_id) if str(payload.project_id).isdigit() else None
    trace_saved = False

    def save_trace(trace_payload: dict) -> None:
        nonlocal trace_saved
        try:
            persist_generation_trace(
                db,
                trace_payload,
                user_id=user.id if user else None,
                project_id=numeric_project_id,
            )
            trace_saved = True
        except Exception as trace_error:
            db.rollback()
            print(f"Failed to save generation trace {generation_trace_id}: {trace_error}")

    target_type = getattr(payload, 'target_type', 'auto') or 'auto'
    
    # ── 지목한 대상 해석 (백로그 28 POINT-0) ──
    #
    # **앱 생성 분기보다 먼저** 한다. 사용자가 캔버스에서 무언가를 지목했다면 그것은 "이걸
    # 고쳐줘" 라는 뜻이지 "앱을 만들어줘" 가 아니다. 뒤에 두면 지목이 조용히 무시된다.
    import pointing as _pointing

    _point_ctx = None
    _point_allowed = None
    _point_instruction = None
    try:
        _point_ctx = _pointing.parse_context(payload.pointing_context)
        if _point_ctx is not None:
            # 이 엔드포인트는 워크플로우 그래프를 다룬다. 앱 컴포넌트 지목은 POINT-2 에서
            # `/api/builder/generate_app` 에 붙는다 — 여기서 받으면 "대상 없음" 으로만 보인다.
            _app_kinds = {t["kind"] for t in _point_ctx["targets"]
                          if t["kind"] in (_pointing.KIND_APP_COMPONENT,
                                           _pointing.KIND_APP_LOGIC_NODE)}
            if _app_kinds:
                raise _pointing.PointingError(
                    _pointing.POINTING_INVALID_CONTEXT,
                    "앱 컴포넌트 지목은 아직 지원하지 않습니다.")
            _point_project = (db.query(models.Project)
                              .filter(models.Project.id == numeric_project_id).first()
                              if numeric_project_id else None)
            if _point_project is None:
                raise _pointing.PointingError(
                    _pointing.POINTING_TARGET_NOT_FOUND, "이 워크플로우를 찾을 수 없습니다.")
            _pointing.check_permission(db, user, _point_project, _point_ctx)
            _pointing.resolve(_point_ctx["targets"], workflow_graph=payload.graph_data,
                              revision=getattr(_point_project, "current_revision", None))
            _point_allowed = _pointing.editable_ids(_point_ctx, workflow_graph=payload.graph_data)
            _point_resolved = _pointing.resolve(
                _point_ctx["targets"], workflow_graph=payload.graph_data,
                revision=getattr(_point_project, "current_revision", None))
            _point_instruction = _pointing.instruction_block(
                _point_ctx, _point_allowed, _point_resolved)
    except _pointing.PointingError as _pe:
        print(f"[pointing] {_pe.code}: {_pointing.telemetry(_point_ctx, outcome=_pe.code.lower())}")
        raise HTTPException(status_code=409 if _pe.code == _pointing.POINTING_TARGET_STALE else 400,
                            detail=_pe.to_dict())

    # ── 1. App Builder Generation (앱 제작 의도) ──
    # 지목이 있으면 이 분기를 타지 않는다 — 지목은 곧 "대상 한정 수정" 요청이다.
    if _point_ctx is None and is_app_creation_intent(payload.message, target_type):
        try:
            app_result = await app_agent.generate_app(
                prompt=payload.message,
                current_state={},
                provider="openai",
                complexity_level=payload.complexity_level
            )
            
            workflow_mappings = app_result.workflow_mappings.copy() if app_result.workflow_mappings else {}
            flow_data = {"nodes": [], "edges": []}
            backend_project_id = None
            
            if app_result.requires_backend_workflow and app_result.backend_workflow_prompt:
                try:
                    flow_data = await asyncio.to_thread(meta_agent.generate_flow, app_result.backend_workflow_prompt)
                    if user:
                        project = models.Project(
                            user_id=user.id,
                            title=f"Backend for {app_result.new_title}",
                            description=f"Auto-generated backend workflow for {app_result.new_title}",
                            graph_data=flow_data,
                            visibility="private"
                        )
                        db.add(project)
                        db.commit()
                        db.refresh(project)
                        backend_project_id = str(project.id)
                        
                        for k, v in list(workflow_mappings.items()):
                            if v == "NEW_WORKFLOW_ID":
                                workflow_mappings[k] = backend_project_id
                                
                        for node in app_result.logic_nodes:
                            if node.type == "workflowNode" and node.data.projectId == "NEW_WORKFLOW_ID":
                                node.data.projectId = backend_project_id
                except Exception as e:
                    print(f"Error generating backend workflow for app: {e}")
                    app_result.reply += "\n\n(참고: 백엔드 워크플로우 자동 생성 중 경고가 발생했습니다.)"

            app_id = str(uuid.uuid4())
            combined_data = {
                "ui": {
                    "components": [c.model_dump() for c in app_result.ui_components],
                    "rootStyle": app_result.root_style,
                    "globalCss": app_result.global_css
                },
                "logic": {
                    "nodes": [n.model_dump() for n in app_result.logic_nodes],
                    "edges": [e.model_dump() for e in app_result.logic_edges]
                }
            }
            
            new_app = models.CustomApp(
                id=app_id,
                title=app_result.new_title,
                ui_graph_data=combined_data,
                workflow_mappings=workflow_mappings,
                owner_id=user.id if user else None
            )
            db.add(new_app)
            db.commit()
            
            total_tokens = 3500
            if user and total_tokens > 0:
                try:
                    record_usage(
                        db,
                        billable_user_id=user.id,
                        actor_user_id=user.id,
                        project_id=int(backend_project_id) if backend_project_id and backend_project_id.isdigit() else None,
                        payload=f"App Agent: {payload.message[:200]}",
                        result=app_result.reply[:500] if app_result.reply else "",
                        total_tokens=total_tokens,
                        event_type=EVENT_APP_GENERATION,
                        trigger_type="app_agent",
                    )
                    db.commit()
                except Exception as e:
                    db.rollback()
                    print(f"Failed to save app agent token log: {e}")

            if user:
                def save_app_session():
                    session = db.query(models.ChatSession).filter(
                        models.ChatSession.user_id == user.id,
                        models.ChatSession.project_id == str(payload.project_id)
                    ).first()
                    if not session:
                        session = models.ChatSession(
                            user_id=user.id,
                            project_id=str(payload.project_id),
                            title=app_result.new_title or (payload.message[:20] + "..."),
                            messages=[]
                        )
                        db.add(session)
                        db.commit()
                        db.refresh(session)
                    msgs = list(session.messages) if session.messages else []
                    msgs.append({"role": "user", "content": payload.message})
                    msgs.append({
                        "role": "ai",
                        "content": app_result.reply,
                        "type": "app",
                        "app_id": app_id,
                        "app_title": app_result.new_title,
                        "workflow_id": backend_project_id,
                        "graph_data": flow_data
                    })
                    session.messages = msgs
                    db.commit()
                await run_in_threadpool(save_app_session)

            return {
                "status": "success",
                "type": "app",
                "reply": app_result.reply,
                "app_id": app_id,
                "app_title": app_result.new_title,
                "app_data": combined_data["ui"],
                "logic_graph": combined_data["logic"],
                "workflow_mappings": workflow_mappings,
                "workflow_id": backend_project_id,
                "graph_data": flow_data,
                "token_usage": {"total_tokens": total_tokens},
                "clarification": None
            }
        except asyncio.CancelledError:
            print(f"App generation cancelled by client for project {payload.project_id}")
            return {"status": "cancelled", "message": "Client disconnected or cancelled"}
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"앱 생성 중 오류: {str(e)}")

    # ── 2. Workflow Generation (일반 워크플로우 생성) ──

    try:
        reply, graph_data, token_usage, clarification = await run_agent_turn(
            payload.graph_data,
            payload.message,
            thread_id=f"project-{payload.project_id}",
            complexity_level=payload.complexity_level,
            db=db,
            trace_id=generation_trace_id,
            training_consent=payload.training_consent,
            pointing_instruction=_point_instruction,
        )
        trace_payload = token_usage.pop("_generation_trace", None)
        generation_outcome = trace_payload.get("outcome") if trace_payload else None

        # 모델이 "지목한 것만 고쳤다" 고 말해도 믿지 않는다 — 전후를 직접 비교한다.
        # 범위 밖이 하나라도 바뀌었으면 **요청 전체를 거부**한다(절반만 반영된 그래프가 더 나쁘다).
        if _point_ctx is not None and _point_allowed is not None and graph_data:
            try:
                _pointing.validate_scope(_point_ctx, before=payload.graph_data,
                                         after=graph_data, allowed=_point_allowed)
                print(f"[pointing] {_pointing.telemetry(_point_ctx, outcome='applied')}")
            except _pointing.PointingError as _pe:
                print(f"[pointing] {_pointing.telemetry(_point_ctx, outcome='scope_violation', violations=len(_pe.targets))}")
                raise HTTPException(status_code=400, detail=_pe.to_dict())
        
        # 에이전트 토큰 차감 + DB 기록
        total_tokens = token_usage.get("total_tokens", 0)
        if user and total_tokens > 0:
            try:
                record_usage(
                    db,
                    billable_user_id=user.id,
                    actor_user_id=user.id,
                    project_id=numeric_project_id,
                    payload=f"Agent Chat: {payload.message[:200]}",
                    result=reply[:500] if reply else "",
                    token_usage=token_usage,
                    event_type=EVENT_WORKFLOW_GENERATION,
                    trigger_type="agent_chat",
                )
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"Failed to save agent token log: {e}")

        if trace_payload:
            save_trace(trace_payload)
        
        # ChatSession 저장 로직
        if user:
            def save_session():
                session = db.query(models.ChatSession).filter(
                    models.ChatSession.user_id == user.id,
                    models.ChatSession.project_id == str(payload.project_id)
                ).first()
                
                if not session:
                    try:
                        from llm.providers import create_chat_model
                        from langchain_core.messages import SystemMessage, HumanMessage
                        llm = create_chat_model(profile="title", temperature=0)
                        res = llm.invoke([
                            SystemMessage(content="주어진 사용자의 요청을 바탕으로 워크플로우 대화 기록의 제목을 15자 내외로 매우 짧게 요약해줘. 따옴표 없이 결과만 출력해. (예: 해커뉴스 요약 봇, 날씨 알리미 등)"),
                            HumanMessage(content=payload.message)
                        ])
                        title = res.content.strip().replace('"', '').replace("'", "")
                    except Exception as e:
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
                msgs.append({"role": "ai", "content": reply, "type": "workflow", "graph_data": graph_data})
                session.messages = msgs
                db.commit()
                
            await run_in_threadpool(save_session)

        return {
            "status": "success",
            "type": "workflow",
            "reply": reply,
            "graph_data": graph_data,
            "token_usage": token_usage,
            "clarification": clarification,
            "trace_id": generation_trace_id,
            "generation_outcome": generation_outcome,
        }
    except asyncio.CancelledError:
        if not trace_saved:
            save_trace(build_generation_trace(
                trace_id=generation_trace_id,
                thread_id=f"project-{payload.project_id}",
                message=payload.message,
                complexity_level=payload.complexity_level,
                graph_data=payload.graph_data,
                outcome="cancelled",
                status="cancelled",
                latency_ms=round((time.perf_counter() - trace_started) * 1000),
                repair_prompt_version=FLOW_REPAIR_PROMPT_VERSION,
            ))
        print(f"Chat generation cancelled by client for project {payload.project_id}")
        return {
            "status": "cancelled",
            "message": "Client disconnected or cancelled",
            "trace_id": generation_trace_id,
        }
    except Exception as e:
        if not trace_saved:
            save_trace(build_generation_trace(
                trace_id=generation_trace_id,
                thread_id=f"project-{payload.project_id}",
                message=payload.message,
                complexity_level=payload.complexity_level,
                graph_data=payload.graph_data,
                outcome="error",
                status="failed",
                latency_ms=round((time.perf_counter() - trace_started) * 1000),
                error_message=str(e),
                repair_prompt_version=FLOW_REPAIR_PROMPT_VERSION,
            ))
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"챗봇 처리 중 오류: {str(e)} (trace_id={generation_trace_id})",
        )

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

@app.delete("/api/chat/session/{session_id}")
def delete_chat_session(session_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    db.delete(session)
    db.commit()
    
    return {"status": "success"}

@app.post("/api/deploy/{project_id}")
async def deploy_project(project_id: int, payload: DeployPayload, db: Session = Depends(get_db),
                         user: models.User = Depends(get_current_user_required)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # 이 라우트는 deploy_mode 를 바꾸고, mode 가 fastapi/mcp 면 **생성된 파이썬 소스를 응답에 담는다**.
    # 그 소스에는 노드 data 가 컴파일 타임 리터럴로 굽혀 있어 봇 토큰·수신자·프롬프트가 평문으로 들어간다.
    # 인증 의존성이 없어서 누구나 정수 id 만으로 남의 배포 설정을 바꾸고 그 소스를 받아갈 수 있었다.
    _require_project_action(db, user, project, project_access.DEPLOY)
    
    # 디스코드 봇은 이제 이 "배포" 엔드포인트가 아니라 discordTriggerNode + 에디터의 "라이브 시작"
    # 토글로 켜고 끈다(webhookNode/scheduleNode와 동일한 방식) — 그래서 여기서 deploy_mode만
    # 바꿀 뿐, discord_bot을 건드리지 않는다(안 그러면 이 값을 apprunner/chatbot 등으로 바꿀 때마다
    # 실제로 떠 있는 디스코드 봇을 실수로 꺼버리게 된다).
    project.deploy_mode = payload.mode
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

    # /api/projects/{id}/run 과 같은 규칙 — 공개 앱은 익명 허용, 그 밖은 RUN 권한.
    if not _can_run_project(db, user, project):
        if not project_access.can(db, user, project, project_access.VIEW):
            raise HTTPException(status_code=404, detail="Project not found")
        raise HTTPException(status_code=403, detail="Not authorized to run this project")

    # 공개 앱은 익명이 실행할 수 있으므로(user=None), 요청자 잔액이 아니라 **소유자 잔액**을 본다.
    # 이 가드가 없으면 익명이 공개 앱을 무제한 실행해 소유자 크레딧을 태울 수 있다(2026-08-31 리뷰).
    _owner = db.query(models.User).filter(models.User.id == project.user_id).first()
    if _owner and _owner.token_balance <= 0:
        raise HTTPException(status_code=403, detail="앱 소유자의 토큰이 모두 소진되었습니다.")

    inputs_dict = payload.inputs
    if inputs_dict and isinstance(inputs_dict, dict):
        if "input_text" not in inputs_dict:
            values = list(inputs_dict.values())
            if values:
                inputs_dict["input_text"] = values[0]
                inputs_dict["text"] = values[0]

    result_text, tokens, logs = run_workflow(project.graph_data.get('nodes', []), project.graph_data.get('edges', []), db=db, session_id='api_call_' + str(project.id), project_id=project.id, **inputs_dict)
    
    import json
    try:
        record_usage(
            db,
            billable_user_id=user.id if user else None,
            actor_user_id=user.id if user else None,
            project_id=project.id,
            token_usage=tokens if isinstance(tokens, dict) else None,
            payload=json.dumps({"project_id": project_id, "inputs": payload.inputs}),
            result=result_text,
            event_type=EVENT_WORKFLOW_EXECUTION,
            outcome=outcome_from_result(result_text),
            trigger_type="api",
        )
        db.commit()
    except Exception as e:
        print(f"Failed to save deploy log: {e}")
        db.rollback()
        
    return {"status": "success", "result": result_text, "token_usage": tokens}

@app.api_route("/webhook/{endpoint_id:path}", methods=["GET", "POST"])
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
                if node_url.startswith('http://') or node_url.startswith('https://'):
                    from urllib.parse import urlparse
                    node_url = urlparse(node_url).path
                
                if not node_url:
                    node_endpoint = str(p.id)
                else:
                    node_endpoint = node_url.replace('/webhook/', '', 1) if node_url.startswith('/webhook/') else node_url.strip('/')
                
                req_endpoint = endpoint_id.replace('http://localhost:8000/webhook/', '', 1) if endpoint_id.startswith('http://localhost:8000/webhook/') else endpoint_id
                req_endpoint = req_endpoint.strip('/')
                
                print(f"Checking project {p.id}: node_endpoint='{node_endpoint}' against '{req_endpoint}'")
                if node_endpoint == req_endpoint:
                    project = p
                    webhook_node_id = n.get('id')
                    print(f"Matched project {p.id}!")
                    break
        if project:
            break
            
    # 2. 정수 project-id 폴백 (backward compatibility)
    #    ⚠️ 위 endpoint 매칭 브랜치는 is_live 를 확인하지만(3064) 이 폴백은 확인하지 않아서,
    #    비공개·라이브 꺼진 프로젝트를 정수 id 만으로 익명 실행할 수 있었다(2026-08-31 적대적 리뷰).
    #    id 는 추측 가능하므로 endpoint 토큰 매칭과 같은 라이브 게이트를 여기에도 건다.
    if not project:
        try:
            project_id = int(endpoint_id)
            candidate = db.query(models.Project).filter(models.Project.id == project_id).first()
            if candidate:
                graph_data = candidate.graph_data or {}
                if isinstance(graph_data, dict) and graph_data.get('is_live', False):
                    nodes = graph_data.get('nodes', [])
                    for n in nodes:
                        if isinstance(n, dict) and n.get('type') == 'webhookNode':
                            project = candidate
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
        # 성공/실패는 실행 로그의 구조화 오류(NodeError v1)로 판정한다 — 결과 문자열 검색은
        # legacy 문구가 남은 경로의 fallback 으로만 남아 있다(ADR-0016, node_errors.runtime).
        flow_status = node_error_runtime.flow_outcome(result_text, logs)
        
        record_usage(
            db,
            billable_user_id=project.user_id,
            actor_user_id=None,
            project_id=project.id,
            token_usage=tokens if isinstance(tokens, dict) else None,
            payload=json.dumps(payload, ensure_ascii=False),
            result="Success (Webhook)" if flow_status == "success" else result_text,
            event_type=EVENT_WORKFLOW_EXECUTION,
            outcome=flow_status,
            trigger_type="webhook",
            error_message=result_text if flow_status == "error" else None,
        )
        db.commit()
        return {"status": "success", "result": result_text}
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})


@app.post("/telegram-webhook/{project_id}")
async def telegram_webhook(project_id: int, request: Request):
    # 텔레그램은 이 엔드포인트가 빠르게 200을 반환하길 기대한다(느리면 재전송을 시도한다) —
    # 실제 워크플로우 실행(동기/블로킹)은 백그라운드 스레드로 넘기고 곧바로 응답한다
    # (discord_bot.py의 on_message가 asyncio.to_thread로 _run을 넘기는 것과 동일한 이유).
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}
    import asyncio
    asyncio.create_task(asyncio.to_thread(telegram_bot.process_update, project_id, update))
    return {"ok": True}


@app.get("/api/bots")
def get_active_bots(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    # deploy_mode가 아니라 discordTriggerNode/telegramTriggerNode가 실제로 그래프 안에 있는지로
    # 판단한다(scheduleNode를 scheduler가 deploy_mode와 무관하게 스캔하는 것과 동일한 방식).
    projects = db.query(models.Project).filter(models.Project.user_id == user.id).all()

    result = []
    for p in projects:
        graph_data = p.graph_data or {}
        discord_node_id, _ = discord_bot.find_discord_trigger_node(graph_data)
        telegram_node_id, _ = telegram_bot.find_telegram_trigger_node(graph_data)

        if discord_node_id:
            client = discord_bot._active_bots.get(p.id)
            status = "offline"
            bot_name = None
            if client:
                status = "online" if client.is_ready() else "connecting"
                bot_name = str(client.user) if client.user else None
            result.append({
                "project_id": p.id,
                "project_title": p.title,
                "trigger_node_id": discord_node_id,
                "platform": "discord",
                "status": status,
                "bot_name": bot_name,
                "updated_at": p.updated_at
            })
        elif telegram_node_id:
            # 텔레그램은 게이트웨이 연결이 없는 웹훅 방식이라 discord처럼 "연결 중" 상태가 없다 —
            # is_live 여부가 곧 상태다.
            is_live = graph_data.get("is_live", False)
            bot_name = None
            if is_live:
                tg_token = telegram_bot.resolve_telegram_token(graph_data, p.user_id, db)
                bot_name = telegram_bot.get_telegram_bot_name(tg_token) or None
            result.append({
                "project_id": p.id,
                "project_title": p.title,
                "trigger_node_id": telegram_node_id,
                "platform": "telegram",
                "status": "online" if is_live else "offline",
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
    tg_node_id, _ = telegram_bot.find_telegram_trigger_node(graph_data)
    if tg_node_id:
        tg_token = telegram_bot.resolve_telegram_token(graph_data, project.user_id, db)
        if tg_token:
            telegram_bot.delete_telegram_webhook(tg_token)

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

    graph_data = dict(project.graph_data) if project.graph_data else {}
    discord_node_id, _ = discord_bot.find_discord_trigger_node(graph_data)
    telegram_node_id, _ = telegram_bot.find_telegram_trigger_node(graph_data)
    if not discord_node_id and not telegram_node_id:
        raise HTTPException(status_code=400, detail="이 프로젝트에는 디스코드 봇(시작) 또는 텔레그램 봇(시작) 노드가 없습니다")

    if discord_node_id:
        token = discord_bot.resolve_discord_token(graph_data, project.user_id, db)
        if not token:
            raise HTTPException(status_code=400, detail="No Discord token saved for this project")
    else:
        token = telegram_bot.resolve_telegram_token(graph_data, project.user_id, db)
        if not token:
            raise HTTPException(status_code=400, detail="No Telegram token saved for this project")

    # Check tokens before starting
    if user and user.token_balance <= 0:
        raise HTTPException(status_code=403, detail="토큰을 모두 소진하여 봇을 시작할 수 없습니다.")

    # Toggle live state
    graph_data["is_live"] = True
    project.graph_data = graph_data
    flag_modified(project, "graph_data")
    db.commit()

    if discord_node_id:
        discord_bot.start_discord_bot(project_id, token)
    else:
        telegram_bot.set_telegram_webhook(token, project_id)

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
    graph_data = project.graph_data or {}
    tg_node_id, _ = telegram_bot.find_telegram_trigger_node(graph_data)
    if tg_node_id:
        tg_token = telegram_bot.resolve_telegram_token(graph_data, project.user_id, db)
        if tg_token:
            telegram_bot.delete_telegram_webhook(tg_token)

    # "봇 삭제"는 이제 이 프로젝트의 discordTriggerNode/telegramTriggerNode 자체를 그래프에서
    # 제거하는 것을 뜻한다(토큰은 노드 데이터 또는 API 센터에 있으므로, 예전처럼 graph_data의
    # 별도 필드를 지울 게 없다).
    if project.graph_data:
        new_data = dict(project.graph_data)
        trigger_ids = {n.get('id') for n in new_data.get('nodes', []) if n.get('type') in ('discordTriggerNode', 'telegramTriggerNode')}
        if trigger_ids:
            new_data['nodes'] = [n for n in new_data.get('nodes', []) if n.get('id') not in trigger_ids]
            new_data['edges'] = [e for e in new_data.get('edges', []) if e.get('source') not in trigger_ids and e.get('target') not in trigger_ids]
        new_data['is_live'] = False
        project.graph_data = new_data
        flag_modified(project, "graph_data")

    project.deploy_mode = "chatbot"  # 레거시 필드지만 다른 화면이 참고할 수 있어 정리해둔다
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

    token = discord_bot.resolve_discord_token(project.graph_data or {}, project.user_id, db)
    return {"status": "success", "token": token}

@app.put("/api/bots/{project_id}/update-token")
async def update_bot_token(project_id: int, payload: TokenActionPayload, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
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
        nodes = new_data.get('nodes', [])
        trigger_node = next((n for n in nodes if n.get('type') == 'discordTriggerNode'), None)
        if not trigger_node:
            raise HTTPException(status_code=400, detail="이 프로젝트에는 디스코드 봇(시작) 노드가 없습니다")
        trigger_node.setdefault('data', {})['botToken'] = payload.new_discord_token
        trigger_node['data']['botToken_source'] = 'manual'
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

                last_run = db.query(models.FlowExecutionLog).filter(
                    models.FlowExecutionLog.project_id == p.id
                ).order_by(models.FlowExecutionLog.execution_time.desc()).first()
                        
                schedules.append({
                    "project_id": p.id,
                    "node_id": schedule_node.get("id"),
                    "title": p.title,
                    "cron": cron_expr,
                    "status": status,
                    "next_run": next_run,
                    "updated_at": p.updated_at,
                    "last_run": last_run.execution_time if last_run else None,
                    "last_outcome": (last_run.outcome or last_run.status) if last_run else None,
                })
    return schedules

@app.post("/api/schedules/{project_id}/pause")
async def pause_schedule(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
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
        
    # Also stop discord/telegram bot if exists
    node_id, _ = discord_bot.find_discord_trigger_node(graph_data)
    if node_id:
        discord_bot.stop_discord_bot(project_id)
    tg_node_id, _ = telegram_bot.find_telegram_trigger_node(graph_data)
    if tg_node_id:
        tg_token = telegram_bot.resolve_telegram_token(graph_data, project.user_id, db)
        if tg_token:
            telegram_bot.delete_telegram_webhook(tg_token)

    return {"status": "success", "message": "Schedule paused and project live status disabled"}

@app.post("/api/schedules/{project_id}/resume")
async def resume_schedule(project_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
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
        
    # Also start discord/telegram bot if exists
    node_id, _ = discord_bot.find_discord_trigger_node(graph_data)
    if node_id:
        token = discord_bot.resolve_discord_token(graph_data, project.user_id, db)
        if token:
            discord_bot.start_discord_bot(project_id, token)
    tg_node_id, _ = telegram_bot.find_telegram_trigger_node(graph_data)
    if tg_node_id:
        tg_token = telegram_bot.resolve_telegram_token(graph_data, project.user_id, db)
        if tg_token:
            telegram_bot.set_telegram_webhook(tg_token, project_id)

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

    def empty_usage_bucket():
        return {"execution": 0, "agent": 0, "app_builder": 0, "evaluation": 0}

    def usage_type(log):
        if log.status in {"agent", "app_builder", "evaluation"}:
            return log.status
        return "execution"

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
            usage[t.strftime("%Y-%m-%d %H:00")] = empty_usage_bucket()
        for log in recent_logs:
            if log.execution_time:
                t_str = log.execution_time.strftime("%Y-%m-%d %H:00")
                if t_str in usage:
                    slot = usage[t_str]
                    tok = log.total_tokens or 0
                    slot[usage_type(log)] += tok
        chart_data = [{"date": k[-5:], "tokens": sum(v.values()), **v, "fullDate": k} for k, v in sorted(usage.items())]

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
            usage[d] = empty_usage_bucket()
        for log in recent_logs:
            if log.execution_time:
                d_str = log.execution_time.date().isoformat()
                if d_str in usage:
                    slot = usage[d_str]
                    tok = log.total_tokens or 0
                    slot[usage_type(log)] += tok
        chart_data = [{"date": k[-5:], "tokens": sum(v.values()), **v, "fullDate": k} for k, v in sorted(usage.items())]

    elif time_range == "yearly":
        usage = {}
        m = now.month
        y = now.year
        for i in range(12):
            usage[f"{y}-{m:02d}"] = empty_usage_bucket()
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
                    slot = usage[m_str]
                    tok = log.total_tokens or 0
                    slot[usage_type(log)] += tok
        chart_data = [{"date": k, "tokens": sum(v.values()), **v, "fullDate": k} for k, v in sorted(usage.items())]

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
            usage[d] = empty_usage_bucket()
        for log in recent_logs:
            if log.execution_time:
                d_str = log.execution_time.date().isoformat()
                if d_str in usage:
                    slot = usage[d_str]
                    tok = log.total_tokens or 0
                    slot[usage_type(log)] += tok
        chart_data = [{"date": k[-5:], "tokens": sum(v.values()), **v, "fullDate": k} for k, v in sorted(usage.items())]

    # 용도별 누적 사용량
    all_logs = db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.user_id == user.id).all()
    usage_by_type = empty_usage_bucket()
    for log in all_logs:
        tok = log.total_tokens or 0
        usage_by_type[usage_type(log)] += tok

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
        models.FlowExecutionLog.project_id.is_(None),
        models.FlowExecutionLog.status.notin_(["agent", "app_builder", "evaluation"])
    ).scalar()
    
    if none_usage:
        project_usage.append({"project_id": None, "title": "미지정 프로젝트", "tokens": none_usage})

    project_usage.sort(key=lambda x: x['tokens'], reverse=True)

    return {
        "total_used": total_used,
        "remaining": remaining,
        "total_allocated": total_allocated,
        "chart_data": chart_data,
        "project_usage": project_usage,
        "usage_by_type": usage_by_type,
    }


@app.get("/api/statistics/v2")
def get_statistics_v2(
    time_range: str = "weekly",
    timezone: str = "Asia/Seoul",
    user: models.User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if time_range not in VALID_TIME_RANGES:
        raise HTTPException(status_code=422, detail=f"Unsupported time_range: {time_range}")
    try:
        return build_statistics(db, user, time_range=time_range, timezone_name=timezone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── Workspace / RBAC (ADR-0024, 우선 백로그 11) ────────────────────────────
#
# 권한 판정은 `project_access.can()` 한 곳이다. 아직 옮기지 않은 엔드포인트는 `user_id == user.id`
# 를 보는데, 그건 workspace 멤버십보다 **더 엄격하다** — 이전이 덜 끝난 상태의 실패 방식은
# "팀원이 아직 못 한다"이지 "남이 볼 수 있다"가 아니다.

class WorkspaceCreatePayload(BaseModel):
    slug: str
    name: str


class InvitePayload(BaseModel):
    handle: str
    role: str = "viewer"


class RolePayload(BaseModel):
    userId: int
    role: str


class MoveProjectPayload(BaseModel):
    workspaceId: Optional[int] = None


def _workspace_or_404(db, workspace_id: int, user):
    import project_access

    workspace = db.query(models.Workspace).filter(models.Workspace.id == workspace_id).first()
    # 멤버가 아니면 존재 자체를 알리지 않는다.
    if workspace is None or not project_access.role_of(db, workspace.id, user.id):
        raise HTTPException(status_code=404, detail="워크스페이스를 찾을 수 없습니다.")
    return workspace


@app.get("/api/workspaces")
def list_my_workspaces(user: models.User = Depends(get_current_user_required),
                       db: Session = Depends(get_db)):
    import workspaces as ws

    return {"status": "success", "workspaces": ws.my_workspaces(db, user),
            "invites": ws.pending_invites(db, user)}


@app.post("/api/workspaces")
def create_workspace(payload: WorkspaceCreatePayload,
                     user: models.User = Depends(get_current_user_required),
                     db: Session = Depends(get_db)):
    import workspaces as ws

    try:
        workspace = ws.create_workspace(db, user, slug=payload.slug, name=payload.name)
    except ws.WorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "workspaceId": workspace.id, "slug": workspace.slug}


@app.get("/api/workspaces/{workspace_id}")
def get_workspace(workspace_id: int, user: models.User = Depends(get_current_user_required),
                  db: Session = Depends(get_db)):
    import project_access
    import workspaces as ws

    workspace = _workspace_or_404(db, workspace_id, user)
    role = project_access.role_of(db, workspace.id, user.id)
    projects = db.query(models.Project).filter(models.Project.workspace_id == workspace.id).all()
    return {"status": "success", "workspace": {
        "id": workspace.id, "slug": workspace.slug, "name": workspace.name, "myRole": role,
        "canManageMembers": project_access.can_manage_members(role),
        "members": ws.members(db, workspace.id),
        "projects": [{"id": p.id, "title": p.title, "visibility": p.visibility} for p in projects],
    }}


@app.post("/api/workspaces/{workspace_id}/invites")
def invite_member(workspace_id: int, payload: InvitePayload,
                  user: models.User = Depends(get_current_user_required),
                  db: Session = Depends(get_db)):
    """**핸들로 초대한다** — 이메일로 초대하면 이메일만 알아도 계정 존재 여부가 확인된다."""
    import workspaces as ws

    workspace = _workspace_or_404(db, workspace_id, user)
    try:
        row = ws.invite(db, user, workspace, handle=payload.handle, role=payload.role)
    except ws.WorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "inviteId": row.id}


@app.post("/api/workspaces/invites/{invite_id}")
def respond_invite(invite_id: int, payload: dict = Body(...),
                   user: models.User = Depends(get_current_user_required),
                   db: Session = Depends(get_db)):
    import workspaces as ws

    try:
        row = ws.respond_to_invite(db, user, invite_id, accept=bool(payload.get("accept")))
    except ws.WorkspaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "success", "inviteStatus": row.status}


@app.post("/api/workspaces/{workspace_id}/members/role")
def change_member_role(workspace_id: int, payload: RolePayload,
                       user: models.User = Depends(get_current_user_required),
                       db: Session = Depends(get_db)):
    import workspaces as ws

    workspace = _workspace_or_404(db, workspace_id, user)
    try:
        ws.set_role(db, user, workspace, payload.userId, payload.role)
    except ws.WorkspaceError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"status": "success"}


@app.delete("/api/workspaces/{workspace_id}/members/{user_id}")
def remove_member(workspace_id: int, user_id: int,
                  user: models.User = Depends(get_current_user_required),
                  db: Session = Depends(get_db)):
    """**마지막 소유자는 나갈 수 없다** — 주인 없는 workspace 는 아무도 관리할 수 없다."""
    import workspaces as ws

    workspace = _workspace_or_404(db, workspace_id, user)
    try:
        ws.remove_member(db, user, workspace, user_id)
    except ws.WorkspaceError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"status": "success"}


@app.get("/api/workspaces/{workspace_id}/audit")
def workspace_audit(workspace_id: int, limit: int = 50,
                    user: models.User = Depends(get_current_user_required),
                    db: Session = Depends(get_db)):
    import project_access
    import workspaces as ws

    workspace = _workspace_or_404(db, workspace_id, user)
    if not project_access.can_manage_members(project_access.role_of(db, workspace.id, user.id)):
        raise HTTPException(status_code=403, detail="감사 이력은 관리자만 볼 수 있습니다.")
    return {"status": "success", "events": ws.recent_events(db, workspace.id, limit=limit)}


@app.post("/api/projects/{project_id}/workspace")
def move_project_to_workspace(project_id: int, payload: MoveProjectPayload,
                              user: models.User = Depends(get_current_user_required),
                              db: Session = Depends(get_db)):
    import workspaces as ws

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    try:
        ws.move_project(db, user, project, workspace_id=payload.workspaceId)
    except ws.WorkspaceError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"status": "success", "workspaceId": project.workspace_id}


# ── 커뮤니티 템플릿 (ADR-0023, 우선 백로그 12) ─────────────────────────────
#
# §4.12 의 글 공유 위에 **버전·호환성·설치 계보**를 얹는 승격 계층이다. 스냅샷과 정화는 그대로
# 물려받고 다시 만들지 않는다.

class TemplatePublishPayload(BaseModel):
    projectId: int
    slug: str
    title: str
    description: Optional[str] = ""
    category: str = "etc"
    tags: Optional[List[str]] = None
    version: str = "1.0.0"
    changelog: Optional[str] = ""


class TemplateVersionPayload(BaseModel):
    projectId: int
    version: str
    changelog: Optional[str] = ""


@app.post("/api/community/templates/gate")
def check_template_gate(payload: dict = Body(...),
                        user: models.User = Depends(get_current_user_required),
                        db: Session = Depends(get_db)):
    """게시 조건을 미리 본다. **왜 안 되는지가 즉시 보여야 한다.**"""
    import community_templates

    project = db.query(models.Project).filter(
        models.Project.id == payload.get("projectId"), models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return {"status": "success", **community_templates.evaluate_gate(db, project, user)}


@app.get("/api/community/templates")
def list_community_templates(category: Optional[str] = None, tag: Optional[str] = None,
                             q: Optional[str] = None, sort: str = "quality", limit: int = 30,
                             db: Session = Depends(get_db)):
    import community_templates

    rows = community_templates.list_templates(db, category=category, tag=tag,
                                              query_text=q, sort=sort, limit=limit)
    return {"status": "success",
            "templates": [community_templates.public_template(db, t) for t in rows]}


@app.post("/api/community/templates")
def publish_template(payload: TemplatePublishPayload,
                     user: models.User = Depends(get_current_user_required),
                     db: Session = Depends(get_db)):
    import community_templates

    _require_active_profile(db, user)
    project = db.query(models.Project).filter(models.Project.id == payload.projectId).first()
    try:
        template, version = community_templates.publish(
            db, user, project=project, slug=payload.slug, title=payload.title,
            description=payload.description or "", category=payload.category,
            tags=payload.tags, version=payload.version, changelog=payload.changelog or "")
    except community_templates.TemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "templateId": template.id, "slug": template.slug,
            "templateStatus": template.status, "versionId": version.id}


class TemplateEditPayload(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    introBody: Optional[str] = None
    introImageIds: Optional[List[str]] = None
    thumbnailArtifactId: Optional[str] = None


class TemplateRevisePayload(BaseModel):
    # 둘 중 하나로 그래프를 준다. 운영자는 보통 템플릿을 자기 계정으로 가져와 에디터에서
    # 고친 뒤 그 프로젝트를 가리킨다 — JSON 을 손으로 붙여넣게 만들 이유가 없다.
    projectId: Optional[int] = None
    graph: Optional[Dict[str, Any]] = None
    version: str
    changelog: str = ""
    reviewer: str = ""


class TemplateCommentPayload(BaseModel):
    body: str


def _template_for_view(db, slug: str, *, viewer):
    """소개 페이지가 볼 수 있는 템플릿. 검수 대기·정지 상태는 고칠 수 있는 사람에게만 보인다."""
    import community_templates

    template = db.query(models.Template).filter(models.Template.slug == slug).first()
    if not template:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    if template.status not in ("published", "deprecated"):
        if not community_templates.can_edit(db, viewer, template):
            raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    return template


@app.get("/api/community/templates/{slug}")
def get_community_template(slug: str,
                           user: Optional[models.User] = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """소개 페이지가 쓰는 한 방 조회 — 템플릿·버전·소개·댓글·내가 누른 좋아요까지 함께 준다."""
    import community_identity
    import community_posts
    import community_templates

    template = _template_for_view(db, slug, viewer=user)
    versions = db.query(models.TemplateVersion).filter(
        models.TemplateVersion.template_id == template.id
    ).order_by(models.TemplateVersion.id.desc()).all()

    payload = community_templates.public_template(db, template)
    payload["introBody"] = template.intro_body or ""
    payload["introImages"] = [f"/api/community/templates/{template.slug}/images/{a}"
                              for a in (template.intro_image_ids or [])]
    payload["introImageIds"] = [str(a) for a in (template.intro_image_ids or [])]
    payload["thumbnailArtifactId"] = template.thumbnail_artifact_id
    payload["canEdit"] = community_templates.can_edit(db, user, template)
    latest = db.query(models.TemplateVersion).filter_by(id=template.latest_version_id).first()
    share = (db.query(models.WorkflowShare).filter_by(id=latest.workflow_share_id).first()
             if latest else None)
    payload["graphOutline"] = community_templates.graph_outline(share)

    liked = False
    if user:
        liked = db.query(models.Reaction).filter(
            models.Reaction.target_type == "template", models.Reaction.target_id == template.id,
            models.Reaction.user_id == user.id, models.Reaction.kind == "like").first() is not None
    payload["likedByMe"] = liked
    # 자기 것에는 좋아요를 못 누른다 — 버튼을 눌러 보고 실패하는 대신 미리 알려준다.
    payload["canLike"] = bool(user) and template.owner_id != (user.id if user else None)

    comments = community_posts.list_comments(db, target_type="template",
                                             target_ids=[template.id],
                                             viewer_id=user.id if user else None)
    staff = _viewer_is_staff(db, user)
    payload["comments"] = [{
        "id": c.id, "body": c.body,
        "author": community_identity.public_profile(
            community_identity.get_profile(db, c.author_id)) if c.author_id else None,
        "createdAt": c.created_at.isoformat() if c.created_at else None,
        "canDelete": bool(user and (c.author_id == user.id or staff)),
    } for c in comments]

    return {"status": "success",
            "template": payload,
            "versions": [{"id": v.id, "version": v.version, "changelog": v.changelog,
                          "status": v.status,
                          "publishedAt": v.published_at.isoformat() if v.published_at else None,
                          "compatibility": community_templates.check_compatibility(db, v)}
                         for v in versions]}


@app.patch("/api/community/templates/{slug}")
def edit_community_template(slug: str, payload: TemplateEditPayload,
                            user: models.User = Depends(get_current_user_required),
                            db: Session = Depends(get_db)):
    """겉면(제목·소개·분류·섬네일)을 고친다. **버전 스냅샷은 건드리지 않는다.**"""
    import community_templates

    template = _template_for_view(db, slug, viewer=user)
    image_ids = None
    if payload.introImageIds is not None:
        image_ids = _validated_template_images(db, user, template, payload.introImageIds)
    try:
        community_templates.edit_template(
            db, user, template, title=payload.title, description=payload.description,
            category=payload.category, tags=payload.tags, intro_body=payload.introBody,
            intro_image_ids=image_ids, thumbnail_artifact_id=payload.thumbnailArtifactId)
    except community_templates.TemplateError as exc:
        raise HTTPException(status_code=403 if "권한" in str(exc) else 400, detail=str(exc))
    return {"status": "success", "template": community_templates.public_template(db, template)}


@app.post("/api/community/templates/{slug}/revise")
def revise_community_template(slug: str, payload: TemplateRevisePayload,
                              user: models.User = Depends(get_current_user_required),
                              db: Session = Depends(get_db)):
    """공식 템플릿의 **로직**을 고쳐 새 버전을 낸다. 기존 버전은 그대로 남는다."""
    import community_templates

    template = _template_for_view(db, slug, viewer=user)

    graph = payload.graph
    if payload.projectId is not None:
        project = db.query(models.Project).filter(models.Project.id == payload.projectId).first()
        # 남의 프로젝트를 가리켜 그 내용을 공식 템플릿으로 밀어넣지 못하게 한다.
        if not project or project.user_id != user.id:
            raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
        graph = project.graph_data or {}
    if graph is None:
        raise HTTPException(status_code=400, detail="새 버전으로 낼 워크플로우를 지정해주세요.")

    try:
        _, version = community_templates.revise_curated(
            db, user, template, graph=graph, version=payload.version,
            changelog=payload.changelog, reviewer=payload.reviewer)
    except community_templates.TemplateError as exc:
        raise HTTPException(status_code=403 if "권한" in str(exc) else 400, detail=str(exc))
    return {"status": "success", "versionId": version.id, "version": version.version}


def _validated_template_images(db, user, template, artifact_ids):
    """소개에 붙일 이미지를 검증한다.

    이미 소개에 들어 있는 id 는 통과시킨다 — 운영자가 남이 올린 템플릿의 오탈자를 고칠 때
    그림까지 다시 올리게 만들 수는 없다. 새로 넣는 id 만 **올린 본인 것인지** 확인한다.
    """
    import artifacts

    ids = [str(a).strip() for a in (artifact_ids or []) if str(a or "").strip()]
    if len(ids) > community_templates_max_images():
        raise HTTPException(status_code=400,
                            detail=f"이미지는 최대 {community_templates_max_images()}장까지 넣을 수 있습니다.")
    existing = {str(a) for a in (template.intro_image_ids or [])}
    for artifact_id in ids:
        if artifact_id in existing:
            continue
        try:
            resolved = artifacts.resolve(db, artifact_id, owner_user_id=user.id,
                                         require_project_match=False)
        except Exception:
            raise HTTPException(status_code=400, detail="붙일 수 없는 이미지가 있습니다.")
        if resolved.ref.kind != artifacts.KIND_IMAGE:
            raise HTTPException(status_code=400, detail="이미지 파일만 붙일 수 있습니다.")
    return ids


def community_templates_max_images() -> int:
    import community_templates

    return community_templates.MAX_INTRO_IMAGES


@app.get("/api/community/templates/{slug}/images/{artifact_id}")
def get_community_template_image(slug: str, artifact_id: str,
                                 user: Optional[models.User] = Depends(get_current_user),
                                 db: Session = Depends(get_db)):
    """소개 이미지. 공개 목록에 실리는 그림이라 로그인 없이도 볼 수 있다 —
    다만 **그 템플릿의 소개에 실제로 들어 있는 id** 만 내려준다."""
    import artifacts

    identifier = str(artifact_id or "").strip()
    template = _template_for_view(db, slug, viewer=user)
    if identifier not in [str(a) for a in (template.intro_image_ids or [])]:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
    try:
        resolved = artifacts.resolve(db, identifier, owner_user_id=0, allow_any_owner=True,
                                     require_project_match=False)
    except Exception:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
    return FileResponse(resolved.path, media_type=resolved.ref.mime_type,
                        headers={"Cache-Control": "public, max-age=3600"})


@app.post("/api/community/templates/{slug}/like")
def like_community_template(slug: str,
                            user: models.User = Depends(get_current_user_required),
                            db: Session = Depends(get_db)):
    import community_posts

    template = _template_for_view(db, slug, viewer=user)
    try:
        return {"status": "success",
                **community_posts.toggle_like(db, user, target_type="template",
                                              target_id=template.id)}
    except community_posts.PostError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/community/templates/{slug}/comments")
def comment_on_community_template(slug: str, payload: TemplateCommentPayload,
                                  user: models.User = Depends(get_current_user_required),
                                  db: Session = Depends(get_db)):
    import community_identity
    import community_posts
    import rate_limit

    _require_active_profile(db, user)
    template = _template_for_view(db, slug, viewer=user)
    try:
        rate_limit.enforce(db, f"user:{user.id}", "comment.create",
                           is_new_account=_is_new_account(user))
    except rate_limit.RateLimited as exc:
        raise _rate_limited(exc)
    try:
        row = community_posts.create_comment(db, user, target_type="template",
                                             target_id=template.id, body=payload.body)
    except community_posts.PostError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "comment": {
        "id": row.id, "body": row.body,
        "author": community_identity.public_profile(community_identity.get_profile(db, user.id)),
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "canDelete": True,
    }}


@app.post("/api/community/templates/{slug}/versions")
def publish_template_version(slug: str, payload: TemplateVersionPayload,
                             user: models.User = Depends(get_current_user_required),
                             db: Session = Depends(get_db)):
    """새 버전. 설치자에게 알림이 가지만 **사본을 자동으로 고치지는 않는다.**"""
    import community_templates

    _require_active_profile(db, user)
    template = db.query(models.Template).filter(models.Template.slug == slug).first()
    project = db.query(models.Project).filter(models.Project.id == payload.projectId).first()
    if not template:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    # ⚠️ publish_version 은 **템플릿** 소유권만 보고 **프로젝트** 소유권은 보지 않았다. 그래서
    # 자기 템플릿에 남의 projectId 로 새 버전을 올리면, 피해자의 비공개 그래프가 정화만 거쳐
    # 공개 템플릿으로 게시됐다(2026-08-31 적대적 리뷰). 프로젝트 소유·조회 권한을 여기서 강제한다.
    if project is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    _require_project_action(db, user, project, project_access.VIEW)
    if project.user_id != user.id and not project_access.can(db, user, project, project_access.EDIT):
        raise HTTPException(status_code=403, detail="본인 소유 워크플로우만 템플릿으로 게시할 수 있습니다.")
    try:
        version = community_templates.publish_version(
            db, user, template, project=project, version=payload.version,
            changelog=payload.changelog or "")
    except community_templates.TemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "versionId": version.id}


@app.post("/api/community/templates/{slug}/install")
def install_community_template(slug: str, version_id: Optional[int] = None,
                               user: models.User = Depends(get_current_user_required),
                               db: Session = Depends(get_db)):
    """사본을 만든다. **실행하지 않는다** — 자격증명은 사용자가 자기 계정에서 채운다."""
    import community_shares
    import community_templates

    template = db.query(models.Template).filter(models.Template.slug == slug).first()
    if not template:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    version = db.query(models.TemplateVersion).filter(
        models.TemplateVersion.id == (version_id or template.latest_version_id)).first()
    if not version or version.template_id != template.id:
        raise HTTPException(status_code=404, detail="버전을 찾을 수 없습니다.")

    try:
        project = community_templates.install(db, user, template, version)
    except community_templates.TemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    share = db.query(models.WorkflowShare).filter(
        models.WorkflowShare.id == version.workflow_share_id).first()
    return {"status": "success", "projectId": project.id,
            "preview": community_shares.import_preview(share)}


@app.post("/api/community/templates/{slug}/versions/{version_id}/yank")
def yank_template_version(slug: str, version_id: int,
                          user: models.User = Depends(get_current_user_required),
                          db: Session = Depends(get_db)):
    """새 설치만 막는다. 이미 설치한 사본은 **회수할 수 없다** — 남의 프로젝트다."""
    import community_templates

    version = db.query(models.TemplateVersion).filter(
        models.TemplateVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="버전을 찾을 수 없습니다.")
    try:
        community_templates.yank_version(db, user, version)
    except community_templates.TemplateError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"status": "success"}


@app.post("/api/community/moderation/templates/{template_id}")
def moderate_template(template_id: int, payload: dict = Body(...),
                      staff: models.User = Depends(get_current_staff_user),
                      db: Session = Depends(get_db)):
    """검수 큐의 템플릿을 승인·반려·정지한다. 정지는 **추가 설치만** 막는다."""
    import community_safety

    template = db.query(models.Template).filter(models.Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    action = str(payload.get("action") or "")
    if action not in ("approve", "suspend", "restore"):
        raise HTTPException(status_code=400, detail="허용되지 않는 조치입니다.")

    template.status = "published" if action in ("approve", "restore") else "suspended"
    if action == "approve" and not template.published_at:
        template.published_at = datetime.datetime.utcnow()
    community_safety.record_action(
        db, staff, target_type="template", target_id=str(template.id),
        action="restore" if action in ("approve", "restore") else "suspend",
        reason=str(payload.get("reason") or ""), commit=False)

    if action == "suspend":
        # 회수는 불가능하다. 할 수 있는 것은 설치자에게 알리는 것뿐이다.
        import notifications

        installer_ids = {row.installed_by for row in db.query(models.TemplateInstall)
                         .join(models.TemplateVersion,
                               models.TemplateInstall.template_version_id == models.TemplateVersion.id)
                         .filter(models.TemplateVersion.template_id == template.id).all()
                         if row.installed_by}
        for user_id in installer_ids:
            notifications.notify(db, user_id=user_id, kind="template_suspended",
                                 target_type="template", target_id=str(template.id), commit=False,
                                 body=f"설치한 템플릿 '{template.title}' 이 운영 조치로 중지됐습니다. "
                                      f"이미 가져간 사본은 그대로 남아 있으니 직접 확인해주세요.")
    db.commit()
    return {"status": "success", "templateStatus": template.status}


# ── 사용자 간 쪽지 (ADR-0022, 우선 백로그 24) ──────────────────────────────
#
# 수신 범위 판정은 `messaging.can_message()` 한 곳에 있고 **전송 API 와 SSE 구독이 같은 함수**를
# 쓴다. 전송만 막고 구독을 열어 두면 차단한 상대의 메시지가 스트림으로 흘러 들어온다.

class ConversationOpenPayload(BaseModel):
    handle: str


class SendMessagePayload(BaseModel):
    body: str = ""
    artifactIds: Optional[List[str]] = None


class ReadUpToPayload(BaseModel):
    upToId: Optional[int] = None


def _messaging_enabled():
    import message_stream

    if not message_stream.enabled():
        raise HTTPException(status_code=503, detail="쪽지 기능이 현재 꺼져 있습니다.")


def _conversation_or_404(db, conversation_id: int, user_id: int):
    import messaging

    conversation = db.query(models.Conversation).filter(
        models.Conversation.id == conversation_id).first()
    try:
        return messaging.require_participant(db, conversation, user_id)
    except messaging.MessagingError:
        # 참가자가 아니면 존재 자체를 알리지 않는다 — 대화 id 를 찍어보며 확인할 수 없어야 한다.
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")


@app.get("/api/messages/conversations")
def list_conversations(user: models.User = Depends(get_current_user_required),
                       db: Session = Depends(get_db)):
    import messaging

    _messaging_enabled()
    return {"status": "success", "conversations": messaging.list_conversations(db, user.id),
            "unread": messaging.unread_total(db, user.id)}


@app.post("/api/messages/conversations")
def open_conversation(payload: ConversationOpenPayload,
                      user: models.User = Depends(get_current_user_required),
                      db: Session = Depends(get_db)):
    """대화 열기. **친구가 아니면 여기서 막힌다** — 대화를 여는 것 자체가 수신 범위 검사를 지난다."""
    import community_identity
    import messaging

    _messaging_enabled()
    _require_active_profile(db, user)
    profile = community_identity.find_by_handle(db, payload.handle)
    if not profile:
        raise HTTPException(status_code=404, detail="해당 핸들의 사용자를 찾을 수 없습니다.")
    other = db.query(models.User).filter(models.User.id == profile.user_id).first()
    try:
        conversation = messaging.open_conversation(db, user, other)
    except messaging.MessagingForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except messaging.MessagingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "conversationId": conversation.id}


@app.get("/api/messages/conversations/{conversation_id}")
def get_conversation(conversation_id: int, before_id: Optional[int] = None, limit: int = 50,
                     user: models.User = Depends(get_current_user_required),
                     db: Session = Depends(get_db)):
    import community_identity
    import messaging

    _messaging_enabled()
    conversation = _conversation_or_404(db, conversation_id, user.id)
    rows = messaging.list_messages(db, conversation, user.id, before_id=before_id, limit=limit)
    other_id = messaging.other_participant(conversation, user.id)
    return {"status": "success",
            "other": community_identity.public_profile(community_identity.get_profile(db, other_id)),
            # 친구가 끊기거나 차단되면 읽기만 남는다 — 대화를 지우지는 않는다.
            "canSend": messaging.can_message(db, user.id, other_id),
            "messages": [messaging.public_message(m, user.id) for m in rows]}


@app.post("/api/messages/conversations/{conversation_id}/messages")
def send_message(conversation_id: int, payload: SendMessagePayload,
                 user: models.User = Depends(get_current_user_required),
                 db: Session = Depends(get_db)):
    import message_stream
    import messaging
    import rate_limit

    _messaging_enabled()
    _require_active_profile(db, user)
    conversation = _conversation_or_404(db, conversation_id, user.id)
    try:
        rate_limit.enforce(db, f"user:{user.id}", "message.send", is_new_account=_is_new_account(user))
    except rate_limit.RateLimited as exc:
        raise _rate_limited(exc)

    try:
        message = messaging.send_message(db, user, conversation, body=payload.body,
                                         artifact_ids=payload.artifactIds)
    except messaging.MessagingForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except messaging.MessagingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 같은 프로세스의 대기자를 깨운다. 전달을 **보장**하는 것은 DB 다(message_stream 참고).
    message_stream.publish([messaging.other_participant(conversation, user.id)])
    return {"status": "success", "messageId": message.id}


@app.post("/api/messages/conversations/{conversation_id}/read")
def read_conversation(conversation_id: int, payload: ReadUpToPayload,
                      user: models.User = Depends(get_current_user_required),
                      db: Session = Depends(get_db)):
    import messaging

    _messaging_enabled()
    conversation = _conversation_or_404(db, conversation_id, user.id)
    return {"status": "success",
            "lastReadMessageId": messaging.mark_read(db, conversation, user.id,
                                                     up_to_id=payload.upToId)}


@app.delete("/api/messages/conversations/{conversation_id}")
def hide_conversation(conversation_id: int, user: models.User = Depends(get_current_user_required),
                      db: Session = Depends(get_db)):
    """**내 목록에서만** 숨긴다. 상대의 대화와 메시지는 그대로다."""
    import messaging

    _messaging_enabled()
    conversation = _conversation_or_404(db, conversation_id, user.id)
    messaging.hide_conversation(db, conversation, user.id)
    return {"status": "success"}


@app.delete("/api/messages/{message_id}")
def delete_message_for_me(message_id: int, user: models.User = Depends(get_current_user_required),
                          db: Session = Depends(get_db)):
    """내 화면에서만 지운다 — 양쪽에서 지우면 신고가 들어왔을 때 확인할 방법이 없다."""
    import messaging

    _messaging_enabled()
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if message is None:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")
    _conversation_or_404(db, message.conversation_id, user.id)
    messaging.delete_for_me(db, message, user.id)
    return {"status": "success"}


@app.get("/api/messages/stream")
async def stream_messages(request: Request, last_event_id: int = 0,
                          user: models.User = Depends(get_current_user_required)):
    """SSE. 재연결은 정상 동작이다 — `Last-Event-ID` 로 놓친 구간을 메운다.

    nginx 가 `proxy_buffering` 을 켠 채로 두면 이벤트가 버퍼에 갇힌다. `X-Accel-Buffering: no` 로
    직접 알리고, 배포 문서(.env.example)에도 남겼다.
    """
    import message_stream
    from database import SessionLocal

    _messaging_enabled()
    if message_stream.stream_count(user.id) >= message_stream.MAX_STREAMS_PER_USER:
        raise HTTPException(status_code=429, detail="열려 있는 연결이 너무 많습니다. 다른 탭을 닫아주세요.")

    header_id = request.headers.get("last-event-id")
    try:
        resume_from = int(header_id) if header_id else int(last_event_id or 0)
    except (TypeError, ValueError):
        resume_from = 0

    return StreamingResponse(
        message_stream.event_stream(SessionLocal, user.id, resume_from),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


# ── 커뮤니티 Q&A (ADR-0021, 우선 백로그 23) ────────────────────────────────
#
# 가시성 판정은 `community_posts.visible_post_query()` 한 곳에 있다. 목록·검색·상세가 각자
# 판단하면 한 경로만 빠뜨려도 친구 공개 글이 전체에 노출되거나 차단한 사람의 글이 보인다.

class PostPayload(BaseModel):
    kind: str = "question"
    visibility: str = "public"
    title: str
    body: str = ""
    tags: Optional[List[str]] = None
    projectId: Optional[int] = None          # 붙일 워크플로우(선택)
    nodeError: Optional[dict] = None         # 실행 오류 발췌(선택)
    nodeType: Optional[str] = None
    imageArtifactIds: Optional[List[str]] = None   # 붙일 이미지(선택)


class PostEditPayload(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[List[str]] = None
    visibility: Optional[str] = None


class AnswerPayload(BaseModel):
    body: str
    projectId: Optional[int] = None


class CommentPayload(BaseModel):
    targetType: str
    targetId: int
    body: str


class LikePayload(BaseModel):
    targetType: str
    targetId: int


def _author_of(db, user_id):
    import community_identity

    return community_identity.public_profile(community_identity.get_profile(db, user_id)) if user_id else None


def _viewer_is_staff(db, user) -> bool:
    """운영 권한 판정의 단일 창구. admin 과 moderator 를 매번 따로 조합하면 화면마다 어긋난다."""
    import community_safety

    return community_safety.has_staff_access(user)


def _post_summary(db, post, *, share=None, viewer_id=None, is_staff=False):
    return {
        "id": post.id, "kind": post.kind, "visibility": post.visibility,
        "title": post.title, "tags": list(post.tags or []),
        "answerCount": post.answer_count or 0, "likeCount": post.like_count or 0,
        "resolved": post.accepted_answer_id is not None,
        "author": _author_of(db, post.author_id),
        "createdAt": post.created_at.isoformat() if post.created_at else None,
        "hasWorkflow": share is not None,
        "images": [f"/api/community/posts/{post.id}/images/{a}"
                   for a in (post.image_artifact_ids or [])],
        # 삭제 권한은 서버가 판단해 내려준다 — 화면이 각자 규칙을 다시 쓰면 어긋난다.
        "canDelete": bool(viewer_id and (post.author_id == viewer_id or is_staff)),
    }


@app.get("/api/community/posts")
def list_community_posts(sort: str = "unanswered", kind: Optional[str] = None,
                         tag: Optional[str] = None, error_code: Optional[str] = None,
                         q: Optional[str] = None, before_id: Optional[int] = None,
                         limit: int = 20, user: models.User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """기본 정렬은 **미해결 질문**이다 — Q&A 에서 가장 중요한 화면은 인기 글이 아니라 답이 없는 질문이다."""
    import community_posts

    viewer_id = user.id if user else None
    viewer_is_staff = _viewer_is_staff(db, user)
    posts = community_posts.list_posts(
        db, viewer_id=viewer_id, sort=sort, kind=kind, tag=tag,
        error_code=error_code, query_text=q, before_id=before_id, limit=limit)
    shares = {s.owner_id for s in db.query(models.WorkflowShare).filter(
        models.WorkflowShare.owner_type == "post",
        models.WorkflowShare.owner_id.in_([p.id for p in posts] or [-1])).all()}
    return {"status": "success", "posts": [
        _post_summary(db, p, share=(True if p.id in shares else None),
                      viewer_id=viewer_id, is_staff=viewer_is_staff) for p in posts]}


MAX_POST_IMAGES = 6


def _validated_post_images(db, user, artifact_ids):
    """붙일 이미지를 글 작성 **전에** 검증한다.

    남의 파일 id 를 그대로 실어 보내는 것을 막아야 하므로 소유자 확인이 있는 `resolve()` 를 쓴다.
    그림이 아닌 파일(예: pdf·xlsx)은 여기서 거른다 — 확장자만 보고 통과시키면 업로드 관문을
    우회해 아무 파일이나 글에 붙일 수 있다.
    """
    import artifacts

    ids = [str(a).strip() for a in (artifact_ids or []) if str(a or "").strip()]
    if not ids:
        return []
    if len(ids) > MAX_POST_IMAGES:
        raise HTTPException(status_code=400, detail=f"이미지는 최대 {MAX_POST_IMAGES}장까지 붙일 수 있습니다.")

    validated = []
    for artifact_id in ids:
        try:
            resolved = artifacts.resolve(db, artifact_id, owner_user_id=user.id,
                                         require_project_match=False)
        except Exception:
            raise HTTPException(status_code=400, detail="붙일 수 없는 이미지가 있습니다.")
        if resolved.ref.kind != artifacts.KIND_IMAGE:
            raise HTTPException(status_code=400, detail="이미지 파일만 붙일 수 있습니다.")
        validated.append(resolved.ref.artifact_id)
    return validated


@app.post("/api/community/posts")
def create_community_post(payload: PostPayload,
                          user: models.User = Depends(get_current_user_required),
                          db: Session = Depends(get_db)):
    import community_posts
    import community_shares
    import rate_limit

    _require_active_profile(db, user)
    try:
        rate_limit.enforce(db, f"user:{user.id}", "post.create", is_new_account=_is_new_account(user))
    except rate_limit.RateLimited as exc:
        raise _rate_limited(exc)

    image_ids = _validated_post_images(db, user, payload.imageArtifactIds)
    try:
        post = community_posts.create_post(
            db, user, kind=payload.kind, title=payload.title, body=payload.body,
            tags=payload.tags, visibility=payload.visibility, image_artifact_ids=image_ids)
    except community_posts.PostError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # 글에 붙은 뒤에야 고정한다 — 글이 안 만들어졌으면 평소 보존 기간대로 정리되어야 한다.
    community_posts.pin_images(db, image_ids)
    db.commit()

    # 워크플로우 첨부 — 정화에 실패하면 글까지 되돌린다(반쯤 만들어진 글을 남기지 않는다).
    if payload.projectId:
        project = db.query(models.Project).filter(models.Project.id == payload.projectId).first()
        try:
            community_shares.create_share(db, user, owner_type="post", owner_id=post.id, project=project)
        except community_shares.ShareError as exc:
            db.delete(post)
            db.commit()
            raise HTTPException(status_code=400, detail=str(exc))

    if payload.nodeError:
        try:
            community_shares.attach_excerpt(db, post, node_error=payload.nodeError,
                                            node_type=payload.nodeType or "")
        except community_shares.ShareError:
            pass   # 발췌 실패가 글 작성을 막지는 않는다
    return {"status": "success", "postId": post.id}


@app.get("/api/community/posts/{post_id}")
def get_community_post(post_id: int, user: models.User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    import community_posts
    import community_shares

    viewer_id = user.id if user else None
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    # 볼 수 없는 글은 **존재하지 않는 것처럼** 404 다 — 친구 공개 글의 존재를 확인할 수 없게.
    if not community_posts.can_view(db, post, viewer_id):
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다.")

    post.view_count = (post.view_count or 0) + 1
    db.commit()

    answers = community_posts.list_answers(db, post, viewer_id)
    share = db.query(models.WorkflowShare).filter(
        models.WorkflowShare.owner_type == "post", models.WorkflowShare.owner_id == post.id).first()
    answer_shares = {s.owner_id: s for s in db.query(models.WorkflowShare).filter(
        models.WorkflowShare.owner_type == "answer",
        models.WorkflowShare.owner_id.in_([a.id for a in answers] or [-1])).all()}
    excerpts = db.query(models.ExecutionExcerpt).filter(
        models.ExecutionExcerpt.post_id == post.id).all()
    post_comments = community_posts.list_comments(db, target_type="post", target_ids=[post.id],
                                                  viewer_id=viewer_id)
    answer_comments = community_posts.list_comments(db, target_type="answer",
                                                    target_ids=[a.id for a in answers],
                                                    viewer_id=viewer_id)

    def comment_payload(rows):
        return [{"id": c.id, "body": c.body, "author": _author_of(db, c.author_id),
                 "createdAt": c.created_at.isoformat() if c.created_at else None} for c in rows]

    return {"status": "success", "post": {
        **_post_summary(db, post, share=share, viewer_id=viewer_id,
                        is_staff=_viewer_is_staff(db, user)),
        "body": post.body, "viewCount": post.view_count,
        "acceptedAnswerId": post.accepted_answer_id,
        "isAuthor": bool(viewer_id and post.author_id == viewer_id),
        "workflow": community_shares.public_share(share),
        "excerpts": [community_shares.public_excerpt(e) for e in excerpts],
        "comments": comment_payload(post_comments),
        "answers": [{
            "id": a.id, "body": a.body, "likeCount": a.like_count or 0,
            "isAccepted": bool(a.is_accepted), "author": _author_of(db, a.author_id),
            "createdAt": a.created_at.isoformat() if a.created_at else None,
            "workflow": community_shares.public_share(answer_shares.get(a.id)),
            "comments": comment_payload([c for c in answer_comments if c.target_id == a.id]),
        } for a in answers],
    }}


@app.get("/api/community/posts/{post_id}/images/{artifact_id}")
def get_community_post_image(post_id: int, artifact_id: str,
                             user: models.User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    """글 이미지를 내려준다. 볼 자격은 **그 이미지를 실은 글의 공개 범위**가 정한다.

    `/uploads` 정적 경로로 바로 주지 않는 이유는 친구 공개 글 때문이다 — 정적 경로는 주소만 알면
    누구나 받을 수 있어서, 친구에게만 보인다고 적어놓고 그림은 전부 공개되는 상태가 된다.
    글 id 를 주소에 넣는 이유는 이 한 건만 보면 되기 때문이다 — artifact id 만 받으면 그 id 를 실은
    글을 찾으려고 전체 글을 훑어야 한다.
    """
    import artifacts
    import community_posts

    identifier = str(artifact_id or "").strip()
    viewer_id = user.id if user else None
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    # 글을 볼 수 없으면 이미지도 없다 — 있는지조차 알리지 않는다(404).
    if not community_posts.can_view(db, post, viewer_id):
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
    if identifier not in [str(a) for a in (post.image_artifact_ids or [])]:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")

    try:
        # 소유권 검사를 건너뛴다 — 글쓴이가 아닌 사람도 봐야 하고, 볼 자격은 위에서 이미 정해졌다.
        resolved = artifacts.resolve(db, identifier, owner_user_id=0, allow_any_owner=True,
                                     require_project_match=False)
    except Exception:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
    return FileResponse(resolved.path, media_type=resolved.ref.mime_type,
                        headers={"Cache-Control": "private, max-age=3600"})


@app.patch("/api/community/posts/{post_id}")
def edit_community_post(post_id: int, payload: PostEditPayload,
                        user: models.User = Depends(get_current_user_required),
                        db: Session = Depends(get_db)):
    import community_posts

    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not community_posts.can_view(db, post, user.id):
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다.")
    try:
        community_posts.edit_post(db, user, post,
                                  **{k: v for k, v in payload.dict().items() if v is not None})
    except community_posts.PostError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"status": "success"}


@app.delete("/api/community/posts/{post_id}")
def delete_community_post(post_id: int, user: models.User = Depends(get_current_user_required),
                          db: Session = Depends(get_db)):
    import community_posts
    import community_safety

    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if post is None or post.deleted_at is not None:
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다.")
    staff = community_safety.has_staff_access(user)
    try:
        community_posts.delete_post(db, user, post, is_staff=staff)
    except community_posts.PostError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if staff and post.author_id != user.id:
        community_safety.record_action(db, user, target_type="post", target_id=str(post.id),
                                       action="remove", reason="운영 조치")
    return {"status": "success"}


@app.post("/api/community/posts/{post_id}/answers")
def create_community_answer(post_id: int, payload: AnswerPayload,
                            user: models.User = Depends(get_current_user_required),
                            db: Session = Depends(get_db)):
    import community_posts
    import community_shares
    import notifications
    import rate_limit

    _require_active_profile(db, user)
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not community_posts.can_view(db, post, user.id):
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다.")
    try:
        rate_limit.enforce(db, f"user:{user.id}", "answer.create", is_new_account=_is_new_account(user))
    except rate_limit.RateLimited as exc:
        raise _rate_limited(exc)

    try:
        answer = community_posts.create_answer(db, user, post, body=payload.body)
    except community_posts.PostError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if payload.projectId:
        project = db.query(models.Project).filter(models.Project.id == payload.projectId).first()
        try:
            community_shares.create_share(db, user, owner_type="answer", owner_id=answer.id,
                                          project=project)
        except community_shares.ShareError as exc:
            db.delete(answer)
            post.answer_count = max(0, (post.answer_count or 1) - 1)
            db.commit()
            raise HTTPException(status_code=400, detail=str(exc))

    if post.author_id and post.author_id != user.id:
        notifications.notify(db, user_id=post.author_id, kind="answer", actor_id=user.id,
                             target_type="post", target_id=str(post.id),
                             body=f"질문에 답변이 달렸습니다: {post.title[:40]}")
    return {"status": "success", "answerId": answer.id}


@app.post("/api/community/posts/{post_id}/accept/{answer_id}")
def accept_community_answer(post_id: int, answer_id: int,
                            user: models.User = Depends(get_current_user_required),
                            db: Session = Depends(get_db)):
    """채택은 **질문자만** 한다 — 무엇이 자기 문제를 풀었는지는 질문자만 안다."""
    import community_posts
    import notifications

    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    answer = db.query(models.Answer).filter(models.Answer.id == answer_id).first()
    if not community_posts.can_view(db, post, user.id) or answer is None:
        raise HTTPException(status_code=404, detail="찾을 수 없습니다.")
    try:
        community_posts.accept_answer(db, user, post, answer)
    except community_posts.PostError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    # 채택 알림은 답변자에게 가장 중요한 신호다.
    if answer.author_id and answer.author_id != user.id:
        notifications.notify(db, user_id=answer.author_id, kind="accepted", actor_id=user.id,
                             target_type="post", target_id=str(post.id),
                             body=f"답변이 채택되었습니다: {post.title[:40]}")
    return {"status": "success"}


@app.delete("/api/community/posts/{post_id}/accept")
def unaccept_community_answer(post_id: int, user: models.User = Depends(get_current_user_required),
                              db: Session = Depends(get_db)):
    import community_posts

    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not community_posts.can_view(db, post, user.id):
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다.")
    try:
        community_posts.unaccept_answer(db, user, post)
    except community_posts.PostError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"status": "success"}


@app.delete("/api/community/comments/{comment_id}")
def delete_community_comment(comment_id: int,
                             user: models.User = Depends(get_current_user_required),
                             db: Session = Depends(get_db)):
    """본인 댓글은 본인이, 그 외에는 운영자가 지운다. 글·답변과 같은 soft delete 다."""
    import community_posts

    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment or comment.deleted_at is not None:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다.")
    try:
        community_posts.delete_comment(db, user, comment, is_staff=_viewer_is_staff(db, user))
    except community_posts.PostError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"status": "success"}


@app.post("/api/community/comments")
def create_community_comment(payload: CommentPayload,
                             user: models.User = Depends(get_current_user_required),
                             db: Session = Depends(get_db)):
    import community_posts
    import rate_limit

    _require_active_profile(db, user)
    try:
        rate_limit.enforce(db, f"user:{user.id}", "comment.create", is_new_account=_is_new_account(user))
    except rate_limit.RateLimited as exc:
        raise _rate_limited(exc)

    # 댓글도 글의 가시성을 따른다 — 볼 수 없는 글에는 댓글을 달 수 없다.
    post_id = payload.targetId if payload.targetType == "post" else None
    if payload.targetType == "answer":
        answer = db.query(models.Answer).filter(models.Answer.id == payload.targetId).first()
        post_id = answer.post_id if answer else None
    post = db.query(models.Post).filter(models.Post.id == post_id).first() if post_id else None
    if not community_posts.can_view(db, post, user.id):
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")

    try:
        row = community_posts.create_comment(db, user, target_type=payload.targetType,
                                             target_id=payload.targetId, body=payload.body)
    except community_posts.PostError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "commentId": row.id}


@app.post("/api/community/likes")
def toggle_community_like(payload: LikePayload,
                          user: models.User = Depends(get_current_user_required),
                          db: Session = Depends(get_db)):
    import community_posts

    _require_active_profile(db, user)
    try:
        result = community_posts.toggle_like(db, user, target_type=payload.targetType,
                                             target_id=payload.targetId)
    except community_posts.PostError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", **result}


# ── 워크플로우 공유 ─────────────────────────────────────────────────────
def _post_for_share_or_404(db, share):
    """글에 붙은 워크플로우 공유의 소속 Post 를 찾는다. owner_type 은 post|answer|template 인데,
    template 공유(운영 DB 972건)는 글에 속하지 않으므로 이 경로로 열지 않는다(2026-08-31 리뷰)."""
    if share.owner_type == "post":
        post_id = share.owner_id
    elif share.owner_type == "answer":
        answer = db.query(models.Answer).filter(models.Answer.id == share.owner_id).first()
        if answer is None:
            raise HTTPException(status_code=404, detail="공유된 워크플로우를 찾을 수 없습니다.")
        post_id = answer.post_id
    else:
        raise HTTPException(status_code=404, detail="공유된 워크플로우를 찾을 수 없습니다.")
    return db.query(models.Post).filter(models.Post.id == post_id).first()


@app.post("/api/community/shares/preview")
def preview_share(payload: dict = Body(...),
                  user: models.User = Depends(get_current_user_required),
                  db: Session = Depends(get_db)):
    """게시 **전에** 무엇이 지워지는지 보여준다. 사용자가 모른 채 누르게 하지 않는다."""
    import community_sanitize

    project = db.query(models.Project).filter(
        models.Project.id == payload.get("projectId"),
        models.Project.user_id == user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return {"status": "success", **community_sanitize.preview(project.graph_data or {})}


@app.get("/api/community/shares/{share_id}")
def get_share(share_id: int, user: models.User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    import community_posts
    import community_shares

    share = db.query(models.WorkflowShare).filter(models.WorkflowShare.id == share_id).first()
    if not share:
        raise HTTPException(status_code=404, detail="공유된 워크플로우를 찾을 수 없습니다.")
    # ⚠️ owner_type 은 post | answer | template 세 값이다. 예전에는 post 가 아니면 전부 answer 로
    #    간주해, template share(운영 DB 972건 전부)가 엉뚱한 Answer 행으로 판정을 타고 그중 16건은
    #    무관한 공개 글의 visibility 로 통과해 in_review 스냅샷을 노출했다(2026-08-31 적대적 리뷰).
    #    template 공유는 이 라우트가 아니라 커뮤니티 템플릿 갤러리로 봐야 하므로 여기선 거부한다.
    post = _post_for_share_or_404(db, share)
    if not community_posts.can_view(db, post, user.id if user else None):
        raise HTTPException(status_code=404, detail="공유된 워크플로우를 찾을 수 없습니다.")
    return {"status": "success",
            "share": community_shares.public_share(share, include_graph=True),
            "preview": community_shares.import_preview(share)}


@app.post("/api/community/shares/{share_id}/import")
def import_shared_workflow(share_id: int, user: models.User = Depends(get_current_user_required),
                           db: Session = Depends(get_db)):
    """사본을 만든다. **실행하지 않는다** — 자격증명은 사용자가 자기 계정에서 채운다."""
    import community_posts
    import community_shares
    import notifications

    share = db.query(models.WorkflowShare).filter(models.WorkflowShare.id == share_id).first()
    if not share:
        raise HTTPException(status_code=404, detail="공유된 워크플로우를 찾을 수 없습니다.")
    post = _post_for_share_or_404(db, share)
    if not community_posts.can_view(db, post, user.id):
        raise HTTPException(status_code=404, detail="공유된 워크플로우를 찾을 수 없습니다.")

    try:
        project = community_shares.import_share(db, user, share)
    except community_shares.ShareError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if post and post.author_id and post.author_id != user.id:
        notifications.notify(db, user_id=post.author_id, kind="imported", actor_id=user.id,
                             target_type="post", target_id=str(post.id), quiet=True,
                             body=f"공유한 워크플로우를 누군가 가져갔습니다: {post.title[:40]}")
    return {"status": "success", "projectId": project.id,
            "preview": community_shares.import_preview(share)}


# ── 커뮤니티 안전·정체성 공통 기반 (ADR-0020, 우선 백로그 22) ─────────────
#
# 이 묶음은 §4.12(글·답변)와 §4.13(쪽지)이 **함께 쓰는 바닥**이다. 기능마다 신고·차단을 따로 두면
# 관리자가 두 화면을 보며 같은 사용자를 판단하게 되고, "커뮤니티에서 차단했는데 쪽지는 오는"
# 상태가 반드시 생긴다.

class ProfilePayload(BaseModel):
    handle: str
    displayName: Optional[str] = ""
    bio: Optional[str] = ""


class BlockPayload(BaseModel):
    handle: str


class ReportPayload(BaseModel):
    targetType: str
    targetId: str
    reason: str
    detail: Optional[str] = ""


class ReportStatusPayload(BaseModel):
    status: str


class SuspendPayload(BaseModel):
    handle: str
    days: int = 7
    reason: Optional[str] = ""


class ReadPayload(BaseModel):
    ids: Optional[List[int]] = None


def _rate_limited(exc) -> HTTPException:
    return HTTPException(status_code=429, detail="요청이 너무 잦습니다. 잠시 뒤 다시 시도해주세요.",
                         headers={"Retry-After": str(exc.retry_after)})


def _require_active_profile(db, user):
    """커뮤니티 쓰기의 공통 전제 — 긴급 스위치가 켜져 있고, 프로필이 있고, 정지되지 않았을 것.

    글·답변·댓글·좋아요·쪽지가 모두 이 함수를 지나므로 여기 한 곳이면 쓰기 전체가 멈춘다.
    읽기 경로는 이 함수를 부르지 않는다 — 그래서 읽기는 항상 유지된다.
    """
    import community_identity
    import community_safety

    if not community_safety.community_writes_enabled(db):
        raise HTTPException(status_code=503,
                            detail="커뮤니티 쓰기가 일시 중지됐습니다. 읽기는 계속 가능합니다.")
    profile = community_identity.get_profile(db, user.id)
    if profile is None:
        raise HTTPException(status_code=409, detail="커뮤니티 프로필이 필요합니다. 핸들을 먼저 만들어주세요.")
    if community_identity.is_suspended(profile):
        raise HTTPException(status_code=403, detail="커뮤니티 활동이 제한된 상태입니다. 읽기는 계속 가능합니다.")
    return profile


@app.get("/api/community/me")
def community_me(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """커뮤니티 진입점. 프로필이 없으면 **만들라는 신호와 후보 핸들**을 준다(ADR-0020 SAFE-1).

    핸들을 미리 백필하지 않는 이유가 여기 있다 — 커뮤니티에 처음 들어오는 이 순간에는 사용자가
    왜 공개 이름이 필요한지 안다.
    """
    import community_identity
    import community_safety
    import notifications

    profile = community_identity.get_profile(db, user.id)
    if profile is None:
        return {"status": "success", "needsProfile": True,
                "suggestedHandle": community_identity.suggest(db, user),
                # 운영 권한은 커뮤니티 프로필 생성 여부와 무관하다. 프로필이 없는 moderator도
                # 운영 콘솔을 찾아갈 수 있어야 하므로 두 분기에서 같은 권한 정보를 돌려준다.
                "role": getattr(user, "role", "user"),
                "isStaff": community_safety.has_staff_access(user),
                "unreadNotifications": notifications.unread_count(db, user.id)}
    return {
        "status": "success", "needsProfile": False,
        "profile": community_identity.public_profile(profile),
        "role": getattr(user, "role", "user"),
        "isStaff": community_safety.has_staff_access(user),
        "unreadNotifications": notifications.unread_count(db, user.id),
    }


@app.post("/api/community/profile")
def create_community_profile(payload: ProfilePayload,
                             user: models.User = Depends(get_current_user_required),
                             db: Session = Depends(get_db)):
    import community_identity

    try:
        profile = community_identity.create_profile(
            db, user, handle=payload.handle,
            display_name=payload.displayName or "", bio=payload.bio or "")
    except community_identity.HandleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "profile": community_identity.public_profile(profile)}


@app.get("/api/community/profiles/{handle}")
def get_community_profile(handle: str, user: models.User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    """공개 프로필. 차단한 상대는 **존재하지 않는 것처럼** 404 다 — 차단 사실을 API 로 확인할 수 없게."""
    import community_identity
    import community_safety

    profile = community_identity.find_by_handle(db, handle)
    if not profile:
        raise HTTPException(status_code=404, detail="프로필을 찾을 수 없습니다.")
    if user and profile.user_id in community_safety.hidden_user_ids(db, user.id):
        raise HTTPException(status_code=404, detail="프로필을 찾을 수 없습니다.")
    return {"status": "success", "profile": community_identity.public_profile(profile)}


@app.get("/api/community/blocks")
def list_blocks(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    import community_identity

    rows = db.query(models.Block).filter(models.Block.blocker_id == user.id).all()
    return {"status": "success", "blocked": [
        community_identity.public_profile(community_identity.get_profile(db, row.blocked_id))
        for row in rows
    ]}


@app.post("/api/community/blocks")
def create_block(payload: BlockPayload, user: models.User = Depends(get_current_user_required),
                 db: Session = Depends(get_db)):
    """차단 + 친구 해제 + 상대에게 조용한 통지(제품 결정 2026-08-29)."""
    import community_identity
    import community_safety
    import rate_limit

    try:
        rate_limit.enforce(db, f"user:{user.id}", "block.create")
    except rate_limit.RateLimited as exc:
        raise _rate_limited(exc)

    profile = community_identity.find_by_handle(db, payload.handle)
    if not profile:
        raise HTTPException(status_code=404, detail="해당 핸들의 사용자를 찾을 수 없습니다.")
    target = db.query(models.User).filter(models.User.id == profile.user_id).first()
    try:
        community_safety.block(db, user, target)
    except community_safety.SafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success"}


@app.delete("/api/community/blocks/{handle}")
def delete_block(handle: str, user: models.User = Depends(get_current_user_required),
                 db: Session = Depends(get_db)):
    """차단 해제. **친구 관계는 복구하지 않는다** — 다시 맺을지는 사용자가 정한다."""
    import community_identity
    import community_safety

    profile = community_identity.find_by_handle(db, handle)
    if not profile:
        raise HTTPException(status_code=404, detail="해당 핸들의 사용자를 찾을 수 없습니다.")
    target = db.query(models.User).filter(models.User.id == profile.user_id).first()
    return {"status": "success", "removed": community_safety.unblock(db, user, target)}


@app.post("/api/community/reports")
def create_report(payload: ReportPayload, user: models.User = Depends(get_current_user_required),
                  db: Session = Depends(get_db)):
    import community_safety
    import rate_limit

    try:
        rate_limit.enforce(db, f"user:{user.id}", "report.create", is_new_account=_is_new_account(user))
    except rate_limit.RateLimited as exc:
        raise _rate_limited(exc)
    try:
        row = community_safety.report(db, user, target_type=payload.targetType,
                                      target_id=payload.targetId, reason=payload.reason,
                                      detail=payload.detail or "")
    except community_safety.SafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "reportId": row.id}


@app.get("/api/community/notifications")
def get_notifications(before_id: Optional[int] = None, limit: int = 30,
                      user: models.User = Depends(get_current_user_required),
                      db: Session = Depends(get_db)):
    import notifications

    return {
        "status": "success",
        "unread": notifications.unread_count(db, user.id),
        "notifications": notifications.list_for(db, user.id, before_id=before_id, limit=limit),
    }


@app.post("/api/community/notifications/read")
def read_notifications(payload: ReadPayload, user: models.User = Depends(get_current_user_required),
                       db: Session = Depends(get_db)):
    import notifications

    updated = notifications.mark_read(db, user.id, notification_ids=payload.ids)
    return {"status": "success", "updated": updated, "unread": notifications.unread_count(db, user.id)}


# ── 운영(moderator 이상) ────────────────────────────────────────────────
@app.get("/api/community/moderation/reports")
def list_reports(status_filter: str = "open", limit: int = 50,
                 staff: models.User = Depends(get_current_staff_user),
                 db: Session = Depends(get_db)):
    query = db.query(models.Report)
    if status_filter != "all":
        query = query.filter(models.Report.status == status_filter)
    rows = query.order_by(models.Report.id.desc()).limit(max(1, min(limit, 200))).all()
    import community_safety

    # 신고된 것이 **무엇인지** 함께 준다 — 대상 미리보기 없이는 판단할 근거가 없다.
    return {"status": "success", "reports": [{
        "id": r.id, "targetType": r.target_type, "targetId": r.target_id,
        "reason": r.reason, "detail": r.detail, "status": r.status,
        "reporter": _author_of(db, r.reporter_id),
        "target": community_safety.target_preview(db, r.target_type, r.target_id),
        "createdAt": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


@app.post("/api/community/moderation/reports/{report_id}")
def update_report(report_id: int, payload: ReportStatusPayload,
                  staff: models.User = Depends(get_current_staff_user),
                  db: Session = Depends(get_db)):
    import community_safety

    try:
        row = community_safety.resolve_report(db, staff, report_id, status=payload.status)
    except community_safety.SafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "reportStatus": row.status}


class ContentActionPayload(BaseModel):
    targetType: str
    targetId: str
    action: str            # hide | remove | restore
    reason: Optional[str] = ""


class WritesSwitchPayload(BaseModel):
    enabled: bool
    reason: Optional[str] = ""


@app.post("/api/community/moderation/content")
def moderate_content(payload: ContentActionPayload,
                     staff: models.User = Depends(get_current_staff_user),
                     db: Session = Depends(get_db)):
    """글·답변·댓글·쪽지 조치. **되돌리기도 하나의 조치로 이력에 남는다.**"""
    import community_safety

    try:
        community_safety.moderate_content(db, staff, target_type=payload.targetType,
                                          target_id=payload.targetId, action=payload.action,
                                          reason=payload.reason or "")
    except community_safety.SafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success"}


@app.get("/api/community/moderation/actions")
def list_moderation_actions(limit: int = 50,
                            staff: models.User = Depends(get_current_staff_user),
                            db: Session = Depends(get_db)):
    import community_safety

    return {"status": "success", "actions": community_safety.recent_actions(db, limit=limit)}


@app.get("/api/community/moderation/status")
def moderation_status(staff: models.User = Depends(get_current_staff_user),
                      db: Session = Depends(get_db)):
    import community_safety

    return {
        "status": "success",
        "writesEnabled": community_safety.community_writes_enabled(db),
        "openReports": db.query(models.Report).filter(models.Report.status == "open").count(),
        "reviewing": db.query(models.Report).filter(models.Report.status == "reviewing").count(),
    }


@app.post("/api/community/moderation/writes")
def switch_community_writes(payload: WritesSwitchPayload,
                            staff: models.User = Depends(get_current_staff_user),
                            db: Session = Depends(get_db)):
    """긴급 스위치 — 커뮤니티 **쓰기만** 멈춘다. 읽기는 어느 경우에도 유지된다.

    상태를 환경변수가 아니라 조치 이력으로 표현한다. 긴급 스위치가 재배포를 요구하면 정작
    긴급할 때 쓸 수 없고, 이력에 두면 누가 언제 껐는지가 함께 남는다.
    """
    import community_safety

    enabled = community_safety.set_community_writes(db, staff, enabled=payload.enabled,
                                                    reason=payload.reason or "")
    return {"status": "success", "writesEnabled": enabled}


@app.post("/api/community/moderation/suspend")
def suspend_member(payload: SuspendPayload, staff: models.User = Depends(get_current_staff_user),
                   db: Session = Depends(get_db)):
    """쓰기만 막고 읽기는 남긴다. 되돌리기는 `/restore` 이고 **둘 다 이력에 남는다**."""
    import community_identity
    import community_safety

    profile = community_identity.find_by_handle(db, payload.handle)
    if not profile:
        raise HTTPException(status_code=404, detail="해당 핸들의 사용자를 찾을 수 없습니다.")
    target = db.query(models.User).filter(models.User.id == profile.user_id).first()
    try:
        updated = community_safety.suspend_user(db, staff, target, days=payload.days,
                                                reason=payload.reason or "")
    except community_safety.SafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "suspendedUntil": updated.suspended_until.isoformat()}


@app.post("/api/community/moderation/restore")
def restore_member(payload: SuspendPayload, staff: models.User = Depends(get_current_staff_user),
                   db: Session = Depends(get_db)):
    import community_identity
    import community_safety

    profile = community_identity.find_by_handle(db, payload.handle)
    if not profile:
        raise HTTPException(status_code=404, detail="해당 핸들의 사용자를 찾을 수 없습니다.")
    target = db.query(models.User).filter(models.User.id == profile.user_id).first()
    try:
        community_safety.restore_user(db, staff, target, reason=payload.reason or "")
    except community_safety.SafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success"}


class FriendAddPayload(BaseModel):
    # 이메일 경로는 폐기됐다(ADR-0020). 필드는 한 릴리스 동안 남겨 두되 무시한다 —
    # 예전 프론트가 남아 있어도 422 로 죽지 않고 "핸들을 입력하세요" 안내를 받게 하려는 것이다.
    handle: Optional[str] = None
    greeting: Optional[str] = None
    email: Optional[str] = None


def _is_new_account(user: models.User) -> bool:
    """가입 직후에는 rate limit 이 더 엄격하다(ADR-0020). 우회 계정 도배를 좁힌다."""
    import rate_limit

    profile = db_profile_created_at(user)
    if profile is None:
        return True
    return (datetime.datetime.utcnow() - profile) < datetime.timedelta(hours=rate_limit.NEW_ACCOUNT_HOURS)


def db_profile_created_at(user: models.User):
    """커뮤니티 프로필 생성 시각. 가입 시각 컬럼이 없어 이 값을 계정 나이의 근사로 쓴다."""
    profile = getattr(user, "community_profile", None)
    if isinstance(profile, list):
        profile = profile[0] if profile else None
    return getattr(profile, "created_at", None) if profile else None

@app.get("/api/friends")
def get_friends(user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """친구 목록. **이메일은 싣지 않는다**(ADR-0020) — 공개 표면의 식별자는 핸들 하나다."""
    import community_identity

    friends = db.query(models.Friendship).filter(models.Friendship.user_id == user.id).all()
    return [{
        "id": f.friend.id,
        "name": f.friend.name,
        "picture": f.friend.picture,
        "profile": community_identity.public_profile(community_identity.get_profile(db, f.friend.id)),
    } for f in friends]

@app.delete("/api/friends/{friend_id}")
def remove_friend(friend_id: int, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    db.query(models.Friendship).filter(models.Friendship.user_id == user.id, models.Friendship.friend_id == friend_id).delete()
    db.query(models.Friendship).filter(models.Friendship.user_id == friend_id, models.Friendship.friend_id == user.id).delete()
    db.commit()
    return {"status": "success"}

# --- Friend Request Endpoints ---

@app.post("/api/friends/request")
def send_friend_request(payload: FriendAddPayload, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """친구 신청. **핸들로만 찾는다**(ADR-0020).

    예전에는 이메일로 찾았다. 그러면 이메일만 알면 계정 존재 여부가 확인되고(계정 열거), 공개 표면이
    생기는 순간 그 경로가 스팸의 입구가 된다. 이제 사용자가 스스로 공개한 이름으로만 찾힌다 —
    커뮤니티에 들어온 적 없는 사용자는 검색되지 않는다.
    """
    import community_identity
    import community_safety
    import rate_limit

    handle = (payload.handle or "").strip()
    if not handle:
        raise HTTPException(status_code=400, detail="상대의 핸들을 입력해주세요. 이메일로는 더 이상 찾을 수 없습니다.")

    try:
        rate_limit.enforce(db, f"user:{user.id}", "friend.request",
                           is_new_account=_is_new_account(user))
    except rate_limit.RateLimited as exc:
        raise HTTPException(status_code=429, detail="친구 신청을 너무 자주 보냈습니다. 잠시 뒤 다시 시도해주세요.",
                            headers={"Retry-After": str(exc.retry_after)})

    profile = community_identity.find_by_handle(db, handle)
    if not profile:
        raise HTTPException(status_code=404, detail="해당 핸들의 사용자를 찾을 수 없습니다.")
    if profile.user_id == user.id:
        raise HTTPException(status_code=400, detail="자기 자신에게는 친구 신청을 보낼 수 없습니다.")

    target = db.query(models.User).filter(models.User.id == profile.user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="해당 핸들의 사용자를 찾을 수 없습니다.")
    # 차단한 상대에게는 요청이 가지 않는다. 존재 여부를 알려주지 않도록 404 와 같은 문구를 쓴다.
    if community_safety.is_blocked_between(db, user.id, target.id):
        raise HTTPException(status_code=404, detail="해당 핸들의 사용자를 찾을 수 없습니다.")

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

    req = models.FriendRequest(from_user_id=user.id, to_user_id=target.id, status="pending",
                               greeting=(payload.greeting or "")[:200] or None)
    db.add(req)
    # 사이트 내 알림으로 알린다(제품 결정 2026-08-29) — 이메일은 보내지 않는다.
    import notifications

    sender = community_identity.get_profile(db, user.id)
    notifications.notify(
        db, user_id=target.id, kind="friend_request", actor_id=user.id,
        target_type="profile", target_id=str(user.id), commit=False,
        body=f"{sender.handle if sender else '한 사용자'}님이 친구 신청을 보냈습니다.",
    )
    db.commit()
    return {"status": "success", "message": f"{profile.handle}님께 친구 신청을 보냈습니다."}

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
    #
    # ⚠️ os.path.join(FRONTEND_DIST, full_path) 는 full_path 에 '../' 가 있으면 dist 밖으로 나간다.
    # nginx 는 경로를 정규화해 막지만 0.0.0.0:8000 이 직접 열려 있어(그리고 curl --path-as-is 는
    # 정규화하지 않아) `/../../backend/.env` 로 DATABASE_URL·JWT_SECRET·OPENAI_API_KEY 가 인증 없이
    # 유출됐다(2026-08-31 적대적 리뷰에서 실증). dist 루트 안으로 가둔 뒤에만 파일을 낸다.
    _FRONTEND_ROOT = os.path.realpath(FRONTEND_DIST)

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        index = os.path.join(_FRONTEND_ROOT, "index.html")
        # 없는 API 경로는 SPA 라우팅이 아니다. 여기서 index.html 을 200 으로 돌려주면 배포
        # 반영 실패가 '200 text/html'로 위장돼, 개발자가 백엔드가 아니라 프론트부터 뒤지게
        # 된다(이 저장소의 실제 재발 이력). 오타 난 라우트도 조용히 화면을 받는다.
        if full_path.startswith("api/"):
            return _api_miss_response("/" + full_path)
        candidate = os.path.realpath(os.path.join(_FRONTEND_ROOT, full_path))
        # 심볼릭 링크까지 푼 실제 경로가 dist 루트 안이어야 한다. 밖이면 SPA 라우팅으로 간주해 index.
        if candidate != _FRONTEND_ROOT and not candidate.startswith(_FRONTEND_ROOT + os.sep):
            return FileResponse(index)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(index)

@app.delete("/api/chat/sessions/{session_id}")
def delete_chat_session(session_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    db.delete(session)
    db.commit()
    return {"status": "success"}

# --- App Builder Endpoints ---

class BuilderGenerateRequest(BaseModel):
    prompt: str
    provider: Optional[str] = "openai"

@app.post("/api/builder/generate")
async def builder_generate_ui(req: BuilderGenerateRequest, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Get user API key
    api_key_record = db.query(models.UserApiKey).filter(
        models.UserApiKey.user_id == user.id,
        models.UserApiKey.provider == req.provider
    ).first()
    
    api_key = decrypt_secret(api_key_record.api_key) if api_key_record else None
    
    # If no key, fallback to system key (for MVP/demo purposes)
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY") if req.provider == "openai" else os.environ.get("GEMINI_API_KEY")
        
    try:
        html_code = await ui_generator.generate_custom_ui(req.prompt, api_key, req.provider)
        return {"html": html_code}
    except Exception as e:
        print(f"UI Generation Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class BuilderSaveRequest(BaseModel):
    app_id: Optional[str] = None
    app_name: str
    ui_graph_data: dict
    logic_graph: dict
    workflow_mappings: dict

def normalize_builder_workflow_mappings(mappings: dict) -> dict:
    normalized = {}
    for component_id, raw_mapping in (mappings or {}).items():
        if isinstance(raw_mapping, dict):
            project_id = raw_mapping.get("projectId", raw_mapping.get("id"))
            extra = raw_mapping.copy()
        else:
            project_id = raw_mapping
            extra = {}
        if project_id is None or project_id == "":
            continue
        extra["projectId"] = str(project_id)
        normalized[str(component_id)] = extra
    return normalized

@app.post("/api/builder/save")
def builder_save_app(req: BuilderSaveRequest, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    combined_data = {
        "ui": req.ui_graph_data,
        "logic": req.logic_graph
    }
    
    if req.app_id:
        existing_app = db.query(models.CustomApp).filter(models.CustomApp.id == req.app_id, models.CustomApp.owner_id == user.id).first()
        if existing_app:
            existing_app.title = req.app_name
            existing_app.ui_graph_data = combined_data
            existing_app.workflow_mappings = normalize_builder_workflow_mappings(req.workflow_mappings)
            db.commit()
            return {"status": "success", "id": existing_app.id}
            
    app_id = str(uuid.uuid4())
    new_app = models.CustomApp(
        id=app_id,
        title=req.app_name,
        ui_graph_data=combined_data,
        workflow_mappings=normalize_builder_workflow_mappings(req.workflow_mappings),
        owner_id=user.id
    )
    db.add(new_app)
    db.commit()
    
    return {"status": "success", "id": app_id}

from app_agent import generate_app
import meta_agent

class BuilderGenerateAppRequest(BaseModel):
    app_id: Optional[str] = None
    prompt: str
    current_state: dict
    generate_mode: str = "code"
    workflow_mode: str = "auto"
    existing_workflow_id: Optional[int] = None

@app.post("/api/builder/generate_app")
async def builder_generate_app_endpoint(req: BuilderGenerateAppRequest, user: models.User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    workflow_mode = req.workflow_mode if req.workflow_mode in {"auto", "existing", "none"} else "auto"
    existing_workflow = None
    generation_prompt = req.prompt
    if workflow_mode == "existing":
        if not req.existing_workflow_id:
            raise HTTPException(status_code=400, detail="기존 Workflow를 선택해주세요.")
        existing_workflow = db.query(models.Project).filter(
            models.Project.id == req.existing_workflow_id,
            models.Project.user_id == user.id,
        ).first()
        if not existing_workflow:
            raise HTTPException(status_code=404, detail="선택한 Workflow를 찾을 수 없습니다.")
        generation_prompt += (
            "\n\n[Workflow 정책] 새 Workflow를 만들지 말고 반드시 기존 Workflow를 사용하세요. "
            f"Workflow ID는 {existing_workflow.id}, 제목은 '{existing_workflow.title}'입니다. "
            "백엔드 동작이 필요한 버튼은 이 Workflow ID에 연결하세요."
        )
    elif workflow_mode == "none":
        generation_prompt += (
            "\n\n[Workflow 정책] 백엔드 Workflow를 만들거나 연결하지 마세요. "
            "화면과 클라이언트 JavaScript만 생성하세요."
        )

    # 1. Call app_agent
    from app_agent import generate_app_safely
    try:
        result = await generate_app_safely(generation_prompt, req.current_state, provider="openai", generate_mode=req.generate_mode)
    except Exception as exc:
        print(f"App Builder generation failed: {exc}")
        raise HTTPException(status_code=500, detail=f"앱 생성 실패: {exc}") from exc
    
    workflow_mappings = result.workflow_mappings.copy()
    workflow_token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    
    actual_project_id = str(existing_workflow.id) if existing_workflow else None

    # 2. If it requires backend workflow, use meta_agent to generate a project
    if workflow_mode == "auto" and result.requires_backend_workflow and result.backend_workflow_prompt:
        try:
            import asyncio
            def generate_backend_flow_with_usage():
                from langchain_community.callbacks import get_openai_callback
                with get_openai_callback() as callback:
                    generated_flow = meta_agent.generate_flow(result.backend_workflow_prompt)
                return generated_flow, {
                    "input_tokens": int(callback.prompt_tokens or 0),
                    "output_tokens": int(callback.completion_tokens or 0),
                    "total_tokens": int(callback.total_tokens or 0),
                }

            flow_data, workflow_token_usage = await asyncio.to_thread(generate_backend_flow_with_usage)
            if hasattr(flow_data, "model_dump"):
                flow_data_dict = flow_data.model_dump()
            else:
                flow_data_dict = flow_data
                
            project = models.Project(
                user_id=user.id,
                title=f"Backend for {result.new_title}",
                description=f"Auto-generated backend workflow for {result.new_title}",
                graph_data=flow_data_dict,
                visibility="private"
            )
            db.add(project)
            db.commit()
            db.refresh(project)
            
            # 3. Replace 'NEW_WORKFLOW_ID' with actual project.id in mappings and logic nodes
            import re
            actual_project_id = str(project.id)
        except Exception as e:
            print(f"Error generating backend workflow: {e}")
            result.reply += "\n\n(참고: 백엔드 워크플로우 생성 중 오류가 발생했습니다. 일부 기능이 동작하지 않을 수 있습니다.)"

    if workflow_mode == "none":
        workflow_mappings = {}
        workflow_node_ids = {node.id for node in result.logic_nodes if node.type == "workflowNode"}
        result.logic_nodes = [node for node in result.logic_nodes if node.id not in workflow_node_ids]
        result.logic_edges = [
            edge for edge in result.logic_edges
            if edge.source not in workflow_node_ids and edge.target not in workflow_node_ids
        ]
    elif actual_project_id:
        import re
        if result.requires_backend_workflow and not workflow_mappings:
            def first_button_id(components):
                for component in components:
                    if component.type == "button":
                        return component.id
                    nested_id = first_button_id(component.children or [])
                    if nested_id:
                        return nested_id
                return None

            fallback_button_id = first_button_id(result.ui_components)
            if fallback_button_id:
                workflow_mappings[fallback_button_id] = actual_project_id
        for component_id, mapping in list(workflow_mappings.items()):
            if isinstance(mapping, dict):
                mapping = {**mapping, "projectId": actual_project_id}
            else:
                mapping = actual_project_id
            workflow_mappings[component_id] = mapping
        for node in result.logic_nodes:
            if node.type == "workflowNode":
                node.data.projectId = actual_project_id
        if result.global_js:
            result.global_js = re.sub(r"['\"][A-Z_]*WORKFLOW_ID['\"]", f"'{actual_project_id}'", result.global_js)
            result.global_js = re.sub(
                r"(runWorkflow\(\s*['\"])[^'\"]+(['\"])",
                rf"\g<1>{actual_project_id}\g<2>",
                result.global_js,
            )

    token_usage = {
        key: int((result.token_usage or {}).get(key, 0) or 0) + int(workflow_token_usage.get(key, 0) or 0)
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }
    token_usage["app_generation"] = result.token_usage or {}
    token_usage["workflow_generation"] = workflow_token_usage
    total_tokens = int(token_usage.get("total_tokens", 0) or 0)
    if total_tokens > 0:
        record_usage(
            db,
            billable_user_id=user.id,
            actor_user_id=user.id,
            project_id=None,
            payload=f"App Builder Generate ({req.app_id or 'new'}): {req.prompt[:200]}",
            result=(result.reply or "")[:500],
            token_usage={
                **token_usage,
                "usage_type": "app_builder",
                "app_id": req.app_id,
                "workflow_mode": workflow_mode,
            },
            event_type=EVENT_APP_GENERATION,
            trigger_type="app_builder",
        )
        db.commit()

    normalized_workflow_mappings = normalize_builder_workflow_mappings(workflow_mappings)
    current_ui_graph = req.current_state.get("ui_graph_data") or {}
    current_canvas = current_ui_graph.get("canvas") or {}
    current_root_style = current_ui_graph.get("rootStyle") or {}
    canvas = {
        "width": current_canvas.get("width", 1024),
        "height": current_canvas.get("height", 768),
        "autoHeight": current_canvas.get("autoHeight", True),
    }
    root_style = {**current_root_style, **(result.root_style or {})}

    return {
        "reply": result.reply,
        "new_title": result.new_title,
        "ui_graph_data": {
            "components": [c.model_dump() for c in result.ui_components],
            "rootStyle": root_style,
            "globalCss": result.global_css,
            "globalJs": result.global_js,
            "canvas": canvas
        },
        "logic_graph": {
            "nodes": [n.model_dump() for n in result.logic_nodes],
            "edges": [e.model_dump() for e in result.logic_edges]
        },
        "workflow_mappings": normalized_workflow_mappings,
        "token_usage": token_usage,
    }


# ── 없는 /api 경로는 SPA 셸도 405 도 아니다 ────────────────────────────────
# **반드시 이 파일 맨 끝에 있어야 한다.** Starlette 는 등록 순서로 매칭하므로, 위에 있는 실제
# 라우트가 먼저 잡히고 아무것도 잡지 못한 /api 요청만 여기로 온다.
#
# 왜 필요한가: 프론트 dist 가 있을 때 `GET /{full_path:path}` catch-all 이 /api 경로까지 잡는다.
# GET 은 그 안에서 404 JSON 으로 돌려주지만, POST 는 "경로는 매칭됐는데 메서드가 없다" 가 되어
# **405** 가 나갔다. 배포에서 라우트가 빠졌을 때 405 는 "있는데 메서드가 틀렸나?" 로 읽혀
# 원인 추적을 엉뚱한 데로 보낸다(계획서가 실측으로 지적한 위장 중 하나).
#
# 다만 진짜 405 까지 404 로 뭉개면 API 계약이 나빠진다 — 라우트가 실재하는데 메서드만 다른
# 경우는 405 와 Allow 헤더가 정확한 답이다. 그래서 경로에 등록된 라우트가 있는지 먼저 본다.
def _api_miss_response(path: str) -> JSONResponse:
    """아무 라우트도 처리하지 못한 /api 요청의 응답. 두 진입점이 이걸 함께 쓴다 —
    아래 catch-all(주로 GET 외 메서드)과, 프론트 dist 가 있을 때 GET 을 먼저 잡는
    `serve_frontend` 의 api 분기. 한 곳만 고치면 메서드에 따라 404/405 가 갈린다."""
    allowed: set = set()
    for route in app.routes:
        regex = getattr(route, "path_regex", None)
        methods = getattr(route, "methods", None)
        route_path = getattr(route, "path", "") or ""
        if regex is None or not methods:
            continue
        # /api 로 시작하는 것만 센다. 프론트 SPA fallback(`/{full_path:path}`)도 이 경로에
        # 매칭되지만 그건 API 라우트가 아니다 — 그것까지 세면 없는 경로가 405 로 나간다.
        if not route_path.startswith("/api/") or route_path == "/api/{rest:path}":
            continue
        if regex.match(path):
            allowed |= set(methods)
    if allowed:
        return JSONResponse(
            status_code=405, content={"detail": "Method Not Allowed"},
            headers={"Allow": ", ".join(sorted(allowed))},
        )
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


@app.api_route("/api/{rest:path}",
               methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
               include_in_schema=False)
async def api_route_not_found(rest: str):
    return _api_miss_response("/api/" + rest)
