from sqlalchemy import Column, Integer, String, JSON, Date, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy import false as sql_false
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    google_id = Column(String, unique=True, index=True)
    email = Column(String, index=True)
    name = Column(String)
    picture = Column(String)
    token_balance = Column(Integer, default=200000)
    # 'user' | 'moderator' | 'admin' (ADR-0020). 예전에는 ADMIN_EMAILS 환경변수로만 판정해서
    # 조치 이력에 "누가"를 사용자 id 로 남길 수 없었고 권한 변경에 재배포가 필요했다.
    # 환경변수는 이제 **첫 관리자를 만드는 부트스트랩**으로만 남는다.
    role = Column(String, nullable=False, default="user", server_default="user")

    projects = relationship("Project", back_populates="owner")
    api_keys = relationship("UserApiKey", back_populates="user", cascade="all, delete-orphan")


class UserApiKey(Base):
    __tablename__ = "user_api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider = Column(String, index=True) # e.g. openai, gemini, kakao, kakao_token, discord, slack
    # AES-256-GCM encrypted at the service boundary. provider=kakao_token stores the access token.
    api_key = Column(String)
    # 명명된 자격증명(ADR-0017, 마이그레이션 0009). provider=database 는 사용자당 여러 행을 가질 수 있고
    # 노드는 `{{API_CENTER:database#<id>}}` reference 로 하나를 고른다. 다른 provider 는 여전히 한 행이다.
    label = Column(String, nullable=True)
    # kakao_token 전용(다른 provider는 안 씀) — OAuth refresh_token과, access_token 만료 시각.
    # 카카오 access_token은 6시간마다 만료되는데, refresh_token(약 2개월 유효)으로 재로그인 없이
    # 자동 갱신할 수 있다. run_workflow()가 {{API_CENTER:kakao_token}}을 치환하기 직전에 이 두
    # 필드를 보고 만료 임박이면 자동으로 갱신한다(graph.py 참고).
    refresh_token = Column(String, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="api_keys")


class OAuthState(Base):
    """인가 코드 흐름의 왕복 1회분 (마이그레이션 0016).

    사용자를 provider 동의 화면으로 보낸 뒤 돌아올 때, "그 응답이 정말 우리가 보낸 요청에
    대한 것인가"를 확인할 근거가 필요하다. state 를 클라이언트에 맡기면 CSRF 로 남의 계정에
    공격자의 토큰을 붙일 수 있어서 서버가 들고 있는다.

    한 번 쓰면 `consumed_at` 이 찍히고 다시 못 쓴다 — code 재생 공격을 막는다. 만료된 행과
    소비된 행은 `purge_expired()` 가 치운다(테이블이 무한히 자라지 않게).
    """

    __tablename__ = "oauth_states"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider = Column(String, index=True, nullable=False)
    # 추측 불가능한 난수. provider 로 나갔다가 그대로 돌아온다.
    state = Column(String, unique=True, index=True, nullable=False)
    # PKCE code_verifier. 이것도 비밀이라 다른 자격증명과 같이 암호화해 넣는다.
    code_verifier = Column(String, nullable=True)
    # 인가 요청에 실제로 쓴 redirect_uri. 토큰 교환 때 같은 값을 보내야 하고, 다르면 provider 가 거부한다.
    redirect_uri = Column(String, nullable=False)
    # 동의 후 사용자를 돌려보낼 우리 화면. 서버가 들고 있어야 열린 리다이렉터가 되지 않는다.
    return_to = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)


class ConnectorCursor(Base):
    """Trigger 노드가 "어디까지 처리했는지" (마이그레이션 0017).

    예전에는 `NodeMemory` 를 `session_id='__cursor__'` 로 빌려 썼다. 대화 기억용 표에 세션이
    아닌 상태를 끼워 넣은 것이라, workspace 격리도 provider 구분도 cursor 형식 버전도 lease 도
    둘 자리가 없었다. 값은 그대로 옮겼으므로 **기존 Trigger 가 과거 항목을 다시 통지하지 않는다.**

    `cursor_version` 은 형식이 바뀔 때 안전하게 버리기 위한 것이다. 읽는 쪽이 모르는 버전이면
    "첫 실행"이 아니라 **오류**로 다루는 편이 낫다 — 첫 실행으로 읽으면 조용히 과거를 다시 통지한다.
    """

    __tablename__ = "connector_cursors"

    id = Column(Integer, primary_key=True, index=True)
    # ADR-0024 의 workspace 소유와 맞춘다. 개인 프로젝트면 비어 있다.
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id = Column(Integer, index=True, nullable=False)
    node_id = Column(String, index=True, nullable=False)
    # 어떤 서비스의 cursor 인지. 옛 값에서 옮겨온 행은 비어 있다.
    provider = Column(String, nullable=True, index=True)
    cursor_version = Column(Integer, nullable=False, default=1)
    cursor_json = Column(String, nullable=False, default="{}")
    # 같은 노드를 두 워커가 동시에 폴링하면 둘 다 통지한다. 먼저 잡은 쪽만 진행한다.
    lease_owner = Column(String, nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (UniqueConstraint("project_id", "node_id", name="uq_connector_cursor"),)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(String, default="Untitled Project")
    description = Column(String, nullable=True)
    graph_data = Column(JSON, default=lambda: {"nodes": [], "edges": []})
    is_public = Column(Boolean, default=False)
    visibility = Column(String, default="private") # 'public', 'private', 'friends'
    # 비어 있으면 개인 소유다(ADR-0024). 전면 백필을 하지 않는 이유는 §4.17 에 있다 —
    # 얻는 것이 "코드 경로가 하나" 뿐인데 그건 project_access.can() 이 이미 준다.
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="SET NULL"),
                          nullable=True, index=True)
    share_token = Column(String, unique=True, index=True, nullable=True)
    deploy_mode = Column(String, default="chatbot")
    # 낙관적 동시성 토큰(ADR-0006). 저장이 성공할 때마다 1씩 오르고, 클라이언트가 들고 있던
    # base_revision 과 다르면 덮어쓰지 않고 409로 돌려보낸다. 0은 "아직 revision이 없음"이다.
    current_revision = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="projects")
    revisions = relationship(
        "ProjectRevision",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectRevision.revision.desc()",
    )


class ProjectRevision(Base):
    """프로젝트를 저장할 때마다 남기는 그래프 스냅샷 (ADR-0006).

    예전에는 `Project.graph_data` 를 바로 덮어썼기 때문에, 두 탭에서 같은 워크플로우를 열어
    각자 저장하면 나중에 저장한 쪽이 앞선 변경을 조용히 지웠고 되돌릴 방법도 없었다.
    팀 협업, 커뮤니티 템플릿 포크 계보, AI 생성 전후 diff가 모두 이 스냅샷을 전제로 한다.
    """

    __tablename__ = "project_revisions"
    __table_args__ = (
        UniqueConstraint("project_id", "revision", name="uq_project_revision"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    # 프로젝트 안에서 1부터 증가하는 번호. Project.current_revision 이 가장 최근 값이다.
    revision = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    description = Column(String, nullable=True)
    graph_data = Column(JSON, default=lambda: {"nodes": [], "edges": []})
    # 저장을 일으킨 사용자. 계정이 지워져도 이력 자체는 남겨야 하므로 FK를 걸지 않는다.
    author_user_id = Column(Integer, nullable=True, index=True)
    # 'user' | 'ai' | 'restore' | 'import' — 되돌리기와 AI 생성 전후 비교를 구분하기 위한 값.
    source = Column(String, nullable=False, default="user")
    # 목록 화면에서 스냅샷 전체를 읽지 않고도 규모를 보여주기 위한 요약
    # ({"nodes": n, "edges": m, "node_types": {...}}).
    summary = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    project = relationship("Project", back_populates="revisions")


class FlowExecutionLog(Base):
    __tablename__ = "flow_execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    # `user_id` is kept as the legacy billable-user field during migration.
    user_id = Column(Integer, nullable=True, index=True)
    actor_user_id = Column(Integer, nullable=True, index=True)
    billable_user_id = Column(Integer, nullable=True, index=True)
    project_id = Column(Integer, nullable=True, index=True)
    execution_time = Column(DateTime, default=datetime.datetime.utcnow)
    payload = Column(String)
    result = Column(String)
    total_tokens = Column(Integer, default=0)
    token_usage_details = Column(JSON, nullable=True)
    event_type = Column(String, nullable=True, index=True)
    outcome = Column(String, nullable=True, index=True)
    trigger_type = Column(String, nullable=True, index=True)
    request_id = Column(String, nullable=True, index=True)
    status = Column(String, default="success")
    error_message = Column(String, nullable=True)

    user = relationship("User", foreign_keys=[user_id], primaryjoin="User.id == foreign(FlowExecutionLog.user_id)", backref="execution_logs")
    node_logs = relationship("NodeExecutionLog", back_populates="flow_execution", cascade="all, delete-orphan")

class NodeExecutionLog(Base):
    __tablename__ = "node_execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    flow_execution_id = Column(Integer, ForeignKey("flow_execution_logs.id", ondelete="CASCADE"), index=True)
    node_id = Column(String)
    node_type = Column(String)
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    status = Column(String, default="running")
    result_data = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    # NodeError v1 telemetry(ADR-0016, 마이그레이션 0008) — code/category/effectState 와 legacy 여부만.
    # 사용자 입력·provider 원문·경로는 컬럼에 없다. request_id 는 내부 ErrorRecord 와 연결하는 열쇠다.
    error_code = Column(String, nullable=True, index=True)
    error_category = Column(String, nullable=True)
    effect_state = Column(String, nullable=True)
    error_legacy = Column(Boolean, nullable=False, default=False, server_default=sql_false())
    error_request_id = Column(String, nullable=True)

    flow_execution = relationship("FlowExecutionLog", back_populates="node_logs")

class BotLog(Base):
    __tablename__ = "bot_logs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    username = Column(String)
    message = Column(String)
    response = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class NodeMemory(Base):
    __tablename__ = 'node_memory'

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    project_id = Column(Integer, index=True)
    node_id = Column(String, index=True)
    history = Column(String, default='[]')
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Friendship(Base):
    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    friend_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id], backref="friendships")
    friend = relationship("User", foreign_keys=[friend_id])


class FriendRequest(Base):
    __tablename__ = "friend_requests"

    id = Column(Integer, primary_key=True, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    to_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status = Column(String, default="pending")  # 'pending', 'accepted', 'rejected'
    # 한 줄 인사말(ADR-0020). 쪽지가 친구 한정이라 이 요청이 대화의 유일한 입구다 —
    # 맥락 없는 요청은 그대로 수락률로 이어진다.
    greeting = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id = Column(String, index=True, nullable=True) # string since it might be 'draft-123' or '45'
    title = Column(String)
    messages = Column(JSON, default=list) # [{role: 'user', content: '...'}, {role: 'ai', content: '...'}]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    user = relationship("User", backref="chat_sessions")

class EvaluationLog(Base):
    __tablename__ = "evaluation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id = Column(Integer, nullable=True, index=True)
    score = Column(Integer, default=0)
    report = Column(JSON, default=dict)
    test_case_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id], backref="evaluation_logs")


class GenerationTrace(Base):
    __tablename__ = "generation_traces"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = Column(Integer, nullable=True, index=True)
    thread_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="completed", index=True)
    outcome = Column(String, nullable=True, index=True)
    request_kind = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    model_profile = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    task_spec_prompt_version = Column(String, nullable=True)
    repair_prompt_version = Column(String, nullable=True)
    request_hash = Column(String, nullable=False)
    request_length = Column(Integer, default=0)
    request_preview = Column(String, nullable=True)
    task_spec = Column(JSON, nullable=True)
    graph_summary = Column(JSON, default=dict)
    validation_issues = Column(JSON, default=list)
    repair_notes = Column(JSON, default=list)
    token_usage = Column(JSON, default=dict)
    # 노드 선별 계측(ADR-0013): LLM 선별 vs hybrid shadow 선별과 최종 사용 노드 비교.
    node_selection = Column(JSON, nullable=True)
    # GenerationPlan 계측(백로그 10번): adaptive 후보 수·평가 정책·후보별 점수와 선택.
    generation_plan = Column(JSON, nullable=True)
    latency_ms = Column(Integer, default=0)
    langfuse_trace_id = Column(String, nullable=True, index=True)
    error_message = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        index=True,
    )

    user = relationship("User", foreign_keys=[user_id], backref="generation_traces")


class ApprovalRequest(Base):
    """사용자 승인 노드의 durable 대기 상태 (ADR-0015).

    워크플로우가 승인 노드에 도달하면 실행을 중단하고 이 행을 남긴다. 승인/거절 결정이
    오면 저장된 그래프 스냅샷과 payload로 그 노드부터 실행을 재개한다 — 서버가 재시작돼도
    대기 상태는 DB에 있으므로 유지된다. payload는 승인자가 본 그대로 재개에 쓰인다
    (승인한 견본과 다른 내용이 이어지는 일이 없도록).
    """
    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, unique=True, nullable=False, index=True)
    # 승인 권한자 = 프로젝트 소유자. 결정한 사람은 decided_by에 따로 남긴다.
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, nullable=True, index=True)
    project_title = Column(String, nullable=True)
    node_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)  # pending/approved/rejected/cancelled
    origin = Column(String, nullable=True)  # editor/schedule/webhook/app 등 실행 출처
    message = Column(String, nullable=True)
    # 승인 노드에 도달한 시점의 직전 노드 출력(승인 대상 견본). 재개 시 이 값이 그대로 흐른다.
    payload = Column(String, nullable=True)
    # 재개에 필요한 실행 문맥: 그래프 스냅샷(자격증명은 reference 상태), 런타임 입력.
    graph_snapshot = Column(JSON, nullable=True)
    runtime_inputs = Column(JSON, nullable=True)
    session_id = Column(String, nullable=True)
    notify_channels = Column(JSON, nullable=True)   # ["email","kakao","discord"] — 사이트 알림은 항상
    notify_results = Column(JSON, nullable=True)    # 채널별 발송 성공/실패 기록
    comment = Column(String, nullable=True)
    decided_by = Column(Integer, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    resume_outcome = Column(String, nullable=True)  # 재개 실행 결과 요약(success/error/halted)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        index=True,
    )

    user = relationship("User", foreign_keys=[user_id], backref="approval_requests")


class TrainingExample(Base):
    __tablename__ = "training_examples"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = Column(Integer, nullable=True, index=True)
    request_hash = Column(String, nullable=False, index=True)
    request_text = Column(String, nullable=False)
    task_spec = Column(JSON, nullable=True)
    generated_graph = Column(JSON, nullable=False)
    final_graph = Column(JSON, nullable=True)
    validation_issues = Column(JSON, default=list)
    acceptance_status = Column(String, nullable=True, index=True)
    edit_metrics = Column(JSON, default=dict)
    provider = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    prompt_versions = Column(JSON, default=dict)
    consent_policy_version = Column(String, nullable=False, default="training-consent-v1")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    user = relationship("User", foreign_keys=[user_id], backref="training_examples")


class SiteFeedback(Base):
    __tablename__ = "site_feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # {"gen_intent_match": 4, "gen_logic_match": 5, ...} — 각 문항 id -> 1~5점
    scores = Column(JSON, default=dict)
    comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id], backref="site_feedback")


class SiteFeedbackSubmitter(Base):
    """평가를 **낸 사람의 목록**. 무엇을 냈는지는 여기 남지 않는다.

    평가 내용(`site_feedback`)은 익명으로 두기로 이미 정해져 있어 `user_id` 가 늘 비어 있다.
    그 결과 "계정당 한 번" 을 강제할 방법이 사라져 같은 사람이 몇 번이든 낼 수 있었다.
    그래서 **냈다는 사실만** 여기에 따로 적는다 — 두 표는 서로를 가리키지 않으므로
    누가 무슨 점수를 줬는지는 여전히 알 수 없다.

    남는 단서는 제출 시각뿐이라 **날짜만** 적는다. 응답이 적을 때는 날짜만으로도 좁혀질 수
    있다는 걸 알고 받아들인 것이다 — 중복 제출을 막는 쪽이 더 중요하다고 판단했다.
    """

    __tablename__ = "site_feedback_submitters"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    submitted_on = Column(Date, nullable=False)


class UploadedFile(Base):
    """업로드된 파일의 소유·용량·보존 기간 기록 (ADR-0010).

    예전에는 `/api/upload` 에 인증이 없어 누구나 서버 디스크에 파일을 쌓을 수 있었고, 올라간
    파일이 누구 것인지도 알 수 없었다. 그래서 용량 제한도, 오래된 파일 정리도 불가능했다.

    배포된 앱을 익명으로 쓰는 사람도 파일을 올릴 수 있어야 하므로(뷰어 라우트에 로그인 요구가
    없다), "올린 사람"과 "용량을 부담하는 사람"을 따로 둔다 — 익명 업로드는 앱 소유자의
    용량으로 계산한다.
    """

    __tablename__ = "uploaded_files"
    # 저장 이름은 소유자 안에서만 유일하다. 생성 파일은 이름을 사용자가 정할 수 있어서
    # (uploads/서식.hwpx) 전역 unique 면 서로 다른 사용자의 같은 이름이 충돌했다 — 물리
    # 파일도 소유자 디렉토리(uploads/u<id>/)로 나눠 이름 충돌 자체가 없다(마이그레이션 0023).
    __table_args__ = (UniqueConstraint("owner_user_id", "stored_name", name="uq_uploaded_files_owner_stored_name"),)

    id = Column(Integer, primary_key=True, index=True)
    # 디스크에 저장된 이름(uuid 또는 사용자가 정한 출력 이름). 경로가 아니라 이름만 저장한다 —
    # 실제 위치(소유자 디렉토리/레거시 루트)는 upload_security.stored_file_path 가 푼다.
    stored_name = Column(String, index=True, nullable=False)
    # 공개 식별자(ADR-0018). 그래프·실행 로그·전송 결과에는 이 값만 남고, stored_name 과 실제
    # 경로는 서버 resolver 안에서만 다룬다 — 저장 위치가 바뀌어도 참조가 깨지지 않는다.
    artifact_id = Column(String, unique=True, index=True, nullable=True)
    original_name = Column(String, nullable=True)
    # 용량을 부담하는 사용자. 계정이 지워져도 정리 작업이 파일을 찾을 수 있어야 하므로 FK를 걸지 않는다.
    owner_user_id = Column(Integer, index=True, nullable=False)
    # 실제로 올린 사람. 익명 뷰어면 비어 있다.
    uploaded_by_user_id = Column(Integer, index=True, nullable=True)
    project_id = Column(Integer, index=True, nullable=True)
    # 'node'(에디터 노드) | 'context'(챗봇 첨부) | 'app'(배포된 앱 입력)
    purpose = Column(String, nullable=False, default="node")
    size_bytes = Column(Integer, nullable=False, default=0)
    content_type = Column(String, nullable=True)
    # 등록 시점의 내용 hash. 전송 직전에 다시 계산해 비교한다 — 등록 뒤 파일이 바뀌었으면 보내지
    # 않는다. 이 기능 도입 전 행은 비어 있고, 그 경우 크기·MIME 검증만 한다.
    sha256 = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    # 지난 파일은 정리한다. 비어 있으면 보존 대상(예: 정책 변경 전 파일).
    expires_at = Column(DateTime, nullable=True, index=True)


class ImageArtifact(Base):
    """Immutable AI image version and the conversation state used to revise it."""

    __tablename__ = "image_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    artifact_id = Column(String, unique=True, nullable=False, index=True)
    owner_user_id = Column(Integer, nullable=False, index=True)
    project_id = Column(Integer, nullable=True, index=True)
    node_id = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    stored_name = Column(String, unique=True, nullable=False)
    parent_artifact_id = Column(String, nullable=True)
    # Responses API multi-turn editing resumes with this id. It is metadata, never a credential.
    response_id = Column(String, nullable=True, index=True)
    request_id = Column(String, nullable=True)
    revision_index = Column(Integer, nullable=False, default=0)
    action = Column(String, nullable=False, default="auto")
    provider = Column(String, nullable=False, default="openai")
    model = Column(String, nullable=True)
    prompt = Column(String, nullable=True)
    revised_prompt = Column(String, nullable=True)
    output_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class CommunityProfile(Base):
    """커뮤니티 공개 표면의 정체성 (ADR-0020).

    핸들은 **커뮤니티에 처음 들어올 때** 만든다. 전체 백필도, 기존 사용자 강제도 없다 —
    커뮤니티를 쓸 생각이 없는 사용자에게 공개 이름을 강제할 이유가 없다.

    그래서 이 행이 없는 사용자는 공개 표면에 **존재하지 않는다**. 검색되지도, 친구로 찾아지지도
    않는다. 결함이 아니라 기본값이 비공개라는 뜻이다.
    """

    __tablename__ = "community_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    # 공개 식별자. 소문자·숫자·하이픈만 — URL 과 멘션에 쓰이고 대소문자 혼동을 막는다.
    handle = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    avatar_artifact_id = Column(String, nullable=True)
    # 정지는 쓰기만 막고 읽기는 남긴다.
    suspended_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", backref="community_profile")


class Block(Base):
    """차단 (ADR-0020). 글·답변·댓글·쪽지가 **모두 이 한 곳**을 본다.

    기능마다 따로 두면 "커뮤니티에서 차단했는데 쪽지는 오는" 상태가 생긴다.
    차단하면 친구 관계도 해제되고, 차단당한 쪽에도 알림이 간다(이유는 싣지 않는다).
    """

    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),)

    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    blocked_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Report(Base):
    """신고 (ADR-0020). 대상 종류에 무관한 하나의 테이블이다 — 관리자가 한 화면에서 판단해야 한다."""

    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    # 'post' | 'answer' | 'comment' | 'message' | 'profile'
    target_type = Column(String, nullable=False, index=True)
    target_id = Column(String, nullable=False, index=True)
    reporter_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reason = Column(String, nullable=False)          # 고정 목록(spam|harassment|inappropriate|copyright|other)
    detail = Column(String, nullable=True)
    # 'open' | 'reviewing' | 'resolved' | 'rejected'
    status = Column(String, nullable=False, default="open", index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True, index=True)


class ModerationAction(Base):
    """관리자 조치 이력 (ADR-0020). **모든 조치는 되돌릴 수 있어야 한다**(restore)."""

    __tablename__ = "moderation_actions"

    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String, nullable=False, index=True)
    target_id = Column(String, nullable=False, index=True)
    admin_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String, nullable=False)          # hide | remove | suspend | restore
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class Notification(Base):
    """인앱 알림 (ADR-0020). 이메일·외부 채널은 만들지 않는다 — 인앱 기록만 남긴다.

    실시간 푸시는 쪽지(§4.13)가 SSE 를 들여올 때 같은 채널에 얹는다. 댓글·좋아요 알림은
    초 단위 실시간이 필요 없다.
    """

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String, nullable=False)            # friend_request | blocked | moderation | ...
    target_type = Column(String, nullable=True)
    target_id = Column(String, nullable=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body = Column(String, nullable=True)
    # 조용한 알림은 배지에 세지 않고 목록에만 남는다(차단 통지 등).
    quiet = Column(Boolean, nullable=False, default=False, server_default="false")
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class RateLimitCounter(Base):
    """고정 윈도우 카운터 (ADR-0020).

    인메모리가 아니라 PostgreSQL 인 이유: 지금은 `--workers 1` 이라 인메모리도 정확하지만,
    워커를 늘리는 순간 한도가 **조용히** N배 느슨해지고 아무도 눈치채지 못한다. 재시작이 잦으면
    프로세스 안의 카운터는 그때마다 초기화된다. 16명 규모에서 왕복 1~3ms 는 그 대가로 싸다.
    """

    __tablename__ = "rate_limit_counters"

    # "<subject>:<action>:<bucket>" — bucket 이 분 단위라 행이 저절로 갈린다.
    key = Column(String, primary_key=True)
    count = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=False, index=True)


class Post(Base):
    """커뮤니티 글 (ADR-0021). **질문이 1급 시민이다**(§9-9 결정).

    질문/답변/댓글을 세 층으로 나눈 이유: "글 + 댓글" 한 겹이면 *답*과 *되묻는 말*이 같은 줄에 섞여
    **채택할 대상을 고를 수 없다**. 답변은 정렬·채택·좋아요의 단위이고, 댓글은 "어떤 노드 쓰셨어요?"
    같은 짧은 확인이라 성격이 다르다.
    """

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    kind = Column(String, nullable=False, default="question", index=True)   # question | showcase | tip
    # 게시 시점에 고른다(§9-10). Project.visibility 와 **별개의 행위**다 — 프로젝트를 공개로 바꾼다고
    # 글이 올라가지 않고, 글을 내린다고 프로젝트 설정이 바뀌지 않는다.
    visibility = Column(String, nullable=False, default="public", index=True)  # public | friends
    title = Column(String, nullable=False)
    body = Column(String, nullable=False, default="")
    tags = Column(JSON, default=list)
    image_artifact_ids = Column(JSON, default=list)
    accepted_answer_id = Column(Integer, nullable=True, index=True)
    answer_count = Column(Integer, nullable=False, default=0)
    like_count = Column(Integer, nullable=False, default=0)
    view_count = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="published", index=True)  # published | hidden | removed
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    edited_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True, index=True)   # soft delete → 30일 → hard delete


class Answer(Base):
    """질문에 달리는 답. 여러 개이고 **하나만 채택**된다. 채택은 질문자만 한다."""

    __tablename__ = "answers"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    body = Column(String, nullable=False, default="")
    like_count = Column(Integer, nullable=False, default=0)
    is_accepted = Column(Boolean, nullable=False, default=False, server_default=sql_false())
    status = Column(String, nullable=False, default="published", index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    edited_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True, index=True)


class Comment(Base):
    """질문·답변에 붙는 짧은 말(1단계). 답변과 달리 채택 대상이 아니다."""

    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String, nullable=False, index=True)   # post | answer
    target_id = Column(Integer, nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    body = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, default="published", index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    edited_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True, index=True)


class Reaction(Base):
    """좋아요. 대상당 사용자 하나 — 자기 글에는 누를 수 없다(집계 부풀리기 방지)."""

    __tablename__ = "reactions"
    __table_args__ = (UniqueConstraint("target_type", "target_id", "user_id", "kind",
                                       name="uq_reaction_once"),)

    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String, nullable=False, index=True)   # post | answer | comment
    target_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String, nullable=False, default="like")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class WorkflowShare(Base):
    """게시 시점의 **불변** 워크플로우 스냅샷 (ADR-0021).

    프로젝트를 가리키는 포인터가 아니다. 포인터로 두면 작성자가 자기 프로젝트를 고칠 때 남이 이미
    읽은 글의 내용이 조용히 바뀌고, 가져간 사람과 원본이 언제 갈라졌는지 알 수 없다.

    `graph_snapshot` 은 `community_sanitize` 를 통과한 것만 들어온다 — 비밀은 이미 없다.
    질문에도 답변에도 붙는다(*안 되는 것*과 *이렇게 하면 되는 것*).
    """

    __tablename__ = "workflow_shares"

    id = Column(Integer, primary_key=True, index=True)
    owner_type = Column(String, nullable=False, index=True)    # post | answer
    owner_id = Column(Integer, nullable=False, index=True)
    source_project_id = Column(Integer, nullable=True)
    source_revision = Column(Integer, nullable=True)
    graph_snapshot = Column(JSON, nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)
    node_types = Column(JSON, default=list)
    required_credentials = Column(JSON, default=list)
    risk_flags = Column(JSON, default=list)
    import_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class ExecutionExcerpt(Base):
    """질문에 붙이는 실행 오류 발췌 (ADR-0021).

    실행 로그를 통째로 붙이면 접속 문자열·토큰·서버 경로가 그대로 샌다. 그래서 ADR-0016
    `NodeError v1` 의 **공개 payload 만** 옮긴다 — 이미 redaction 을 거친 값이라 새 정화 규칙이
    필요 없고, 그 대가로 질문이 `error_code` 로 묶이고 검색된다.
    """

    __tablename__ = "execution_excerpts"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    node_type = Column(String, nullable=True)
    error_code = Column(String, nullable=True, index=True)
    error_category = Column(String, nullable=True)
    effect_state = Column(String, nullable=True)
    user_message = Column(String, nullable=True)
    occurred_at = Column(DateTime, nullable=True)


class Conversation(Base):
    """1:1 대화 (ADR-0022). **친구 한정**이라 "수락 대기" 상태가 없다.

    §4.13 은 친구가 아닌 상대의 첫 메시지를 요청함으로 받는 안을 검토했지만, 친구 한정으로
    정하면서(2026-08-29) `MessageRequest` 엔티티와 수락 흐름이 통째로 빠졌다. 수락은 이미 있는
    친구 요청이 담당하고, 쪽지는 친구가 된 뒤에만 열린다.
    """

    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("user_a_id", "user_b_id", name="uq_conversation_pair"),)

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, nullable=False, default="direct")
    # 참가자 쌍의 유일성을 DB 가 보장하도록 **작은 id 를 a 에** 둔다. 정렬하지 않으면
    # (1,2)와 (2,1)이 서로 다른 행이 되어 같은 상대와 대화가 두 개 생긴다.
    user_a_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_b_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    last_message_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class ConversationMember(Base):
    """참가자별 상태. 읽음·숨김·음소거는 **개인의 것**이라 대화가 아니라 참가자에 붙는다."""

    __tablename__ = "conversation_members"
    __table_args__ = (UniqueConstraint("conversation_id", "user_id", name="uq_conversation_member"),)

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    last_read_message_id = Column(Integer, nullable=False, default=0)
    muted_until = Column(DateTime, nullable=True)
    # 내 목록에서만 숨긴다. 상대의 대화는 그대로다.
    hidden_at = Column(DateTime, nullable=True)


class Message(Base):
    """쪽지 한 통 (ADR-0022).

    **본문은 실행 로그·telemetry·오류 payload 에 절대 남기지 않는다**(ADR-0016 redaction 규칙).
    삭제는 기본이 "내 화면에서만" 이다 — 양쪽에서 사라지면 신고가 들어왔을 때 확인할 방법이 없다.
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    body = Column(String, nullable=False, default="")
    attachment_artifact_ids = Column(JSON, default=list)
    # sent | removed_by_admin. "내 화면에서만 삭제"는 아래 deleted_for_user_ids 로 표현한다.
    status = Column(String, nullable=False, default="sent")
    # 내 화면에서만 지운 사람들의 id. 상대에게는 그대로 남는다.
    deleted_for_user_ids = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    edited_at = Column(DateTime, nullable=True)


class Template(Base):
    """커뮤니티 템플릿 (ADR-0023). 이름·소개·상태만 갖고 **내용은 버전이 갖는다.**

    §4.12 의 글 공유(`WorkflowShare`)와 다른 점은 하나다 — 글은 가볍게 올리고 지울 수 있어야 하고,
    템플릿은 **한 번 게시하면 절대 바뀌지 않아야** 한다. 누군가 v1.0 을 설치했는데 v1.0 의 내용이
    나중에 바뀌면 "v1.0 을 설치했다"는 기록이 거짓말이 된다.
    """

    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    category = Column(String, nullable=False, default="etc", index=True)
    tags = Column(JSON, default=list)
    # draft | in_review | published | deprecated | suspended
    status = Column(String, nullable=False, default="draft", index=True)
    # 운영자가 직접 만들어 올린 공식 템플릿인가(ADR-0023 의 게이트 3번 면제).
    #
    # 일반 게시는 "본인 계정에서 한 번 성공 실행" 을 요구한다 — 심사 인력 없이 얻는 가장 값싼
    # 품질 신호다. 공식 템플릿은 그 신호를 **사람의 검수로 대체**하므로, 대체했다는 사실이
    # 기록에 남아야 한다. 숨은 예외로 두면 나중에 "이건 왜 실행 이력이 없지" 를 알 수 없다.
    is_curated = Column(Boolean, nullable=False, default=False, index=True)
    latest_version_id = Column(Integer, nullable=True)
    install_count = Column(Integer, nullable=False, default=0)
    published_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # ── 소개 페이지 ──
    # `description` 은 목록 한 줄짜리 요약이고, 이건 **읽고 판단하라고 쓰는 글**이다(마크다운).
    # 버전 스냅샷과 달리 고쳐도 된다 — 가져간 사람의 사본이 바뀌지 않기 때문이다.
    intro_body = Column(String, nullable=False, default="", server_default="")
    intro_image_ids = Column(JSON, default=list)
    # 소개에 넣은 그림 중 하나를 목록의 섬네일로 쓴다. 반드시 intro_image_ids 안의 값이어야 한다.
    thumbnail_artifact_id = Column(String, nullable=True)

    # ── 집계 ──
    # 목록에서 정렬·표시에 쓰므로 컬럼으로 둔다. 정본은 reactions/comments 행이고 여기는 사본이다.
    like_count = Column(Integer, nullable=False, default=0, server_default="0")
    comment_count = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime, default=datetime.datetime.utcnow,
                        onupdate=datetime.datetime.utcnow)


class TemplateVersion(Base):
    """한 번 게시되면 **절대 바뀌지 않는다.** 고치려면 새 버전을 낸다.

    스냅샷을 다시 만들지 않고 §4.12 의 `WorkflowShare` 를 가리킨다 — 정화 로직을 두 벌 만들면
    한쪽만 고쳐지는 날이 온다.
    """

    __tablename__ = "template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_template_version"),)

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("templates.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    version = Column(String, nullable=False)              # semver
    workflow_share_id = Column(Integer, nullable=False)
    changelog = Column(String, nullable=True)
    # 설치 시점에 지금 환경과 대조한다 — 노드 정의가 바뀌면 예전 템플릿이 조용히 깨진다.
    compatibility = Column(JSON, default=dict)
    # 게시 때 통과한 근거. "언제 무엇을 확인했는가"가 남아야 나중에 판단을 되짚을 수 있다.
    publish_gate = Column(JSON, default=dict)
    status = Column(String, nullable=False, default="published", index=True)   # published | yanked
    published_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class TemplateInstall(Base):
    """설치 계보. 업그레이드 알림과 **품질 신호**(첫 실행 성공률·7일 유지율)의 원천이다.

    설치 수와 별점을 1차 품질 신호로 쓰지 않는다(§4.2 판단 유지) — 조작하기 쉽고 초기 표본이 작다.
    """

    __tablename__ = "template_installs"

    id = Column(Integer, primary_key=True, index=True)
    template_version_id = Column(Integer, ForeignKey("template_versions.id", ondelete="CASCADE"),
                                 nullable=False, index=True)
    installed_project_id = Column(Integer, nullable=True, index=True)
    installed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    installed_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    # success | error | none — 가져간 뒤 실제로 돌았는지가 별점보다 정직한 신호다.
    first_run_outcome = Column(String, nullable=True, index=True)
    retained_at_7d = Column(Boolean, nullable=True)


class Workspace(Base):
    """조직 단위 (ADR-0024). 워크플로우를 **개인의 것에서 조직의 것으로** 옮기는 그릇이다.

    친구 관계를 팀 권한으로 재사용하지 않는다(§4.1 판단) — "볼 수 있다"와 "편집·실행·배포할 수
    있다"는 다른 이야기이고, 섞으면 둘 다 흐려진다.
    """

    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    plan = Column(String, nullable=False, default="free")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class WorkspaceMember(Base):
    """멤버십과 역할. 역할 표는 §4.17 이 정본이고 `project_access.ROLE_ACTIONS` 가 그것을 옮긴 것이다."""

    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),)

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False, default="viewer")
    status = Column(String, nullable=False, default="active", index=True)   # active | removed
    invited_by = Column(Integer, nullable=True)
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)


class WorkspaceInvite(Base):
    """초대. **핸들로 보낸다** — 이메일로 초대하면 이메일만 알아도 계정 존재 여부가 확인된다
    (ADR-0020 에서 친구 추가를 핸들로 옮긴 것과 같은 이유)."""

    __tablename__ = "workspace_invites"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    handle = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False, default="viewer")
    invited_by = Column(Integer, nullable=True)
    # pending | accepted | declined | revoked
    status = Column(String, nullable=False, default="pending", index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AuditEvent(Base):
    """감사 이벤트 (ADR-0024). **권한·소유·자격증명 변경만** 남긴다.

    실행 이력은 이미 `FlowExecutionLog` 에 있다. 여기에 실행까지 넣으면 정작 봐야 할 권한 변경이
    파묻힌다.
    """

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"),
                          nullable=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=True)
    resource_id = Column(String, nullable=True)
    event_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class CustomApp(Base):
    __tablename__ = "custom_apps"

    id = Column(String, primary_key=True, index=True) # UUID or generated ID
    title = Column(String, default="Untitled Custom App")
    ui_graph_data = Column(JSON, default=lambda: {"nodes": [], "edges": []})
    workflow_mappings = Column(JSON, default=dict) # Mappings of UI element IDs to Project IDs or Node IDs
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    owner = relationship("User", foreign_keys=[owner_id], backref="custom_apps")


class DocumentFormat(Base):
    """사용자 문서 포맷 라이브러리 (포맷 스튜디오 계획 §4.1).

    프리셋(저장소 정본 document_formats/*.json)과 달리 사용자가 만든 포맷이다.
    id 는 uuid 문자열 — formatNode.data.formatId 가 프리셋 id 와 같은 자리에서 참조하므로
    숫자 PK 대신 충돌 없는 문자열을 쓴다. spec 은 저장 시점에 validate_format_spec 을
    통과한 FormatSpec JSON 이다.
    """

    __tablename__ = "document_formats"

    id = Column(String, primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String, nullable=False)
    layout = Column(String, nullable=False, default="document")
    spec = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    owner = relationship("User", foreign_keys=[owner_user_id], backref="document_formats")

