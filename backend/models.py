from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Boolean
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

    projects = relationship("Project", back_populates="owner")
    api_keys = relationship("UserApiKey", back_populates="user", cascade="all, delete-orphan")


class UserApiKey(Base):
    __tablename__ = "user_api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider = Column(String, index=True) # e.g. openai, gemini, kakao, kakao_token, discord, slack
    api_key = Column(String) # Encrypted or raw for MVP. provider=kakao_token일 때는 access_token을 담는다.
    # kakao_token 전용(다른 provider는 안 씀) — OAuth refresh_token과, access_token 만료 시각.
    # 카카오 access_token은 6시간마다 만료되는데, refresh_token(약 2개월 유효)으로 재로그인 없이
    # 자동 갱신할 수 있다. run_workflow()가 {{API_CENTER:kakao_token}}을 치환하기 직전에 이 두
    # 필드를 보고 만료 임박이면 자동으로 갱신한다(graph.py 참고).
    refresh_token = Column(String, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="api_keys")

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(String, default="Untitled Project")
    description = Column(String, nullable=True)
    graph_data = Column(JSON, default=lambda: {"nodes": [], "edges": []})
    is_public = Column(Boolean, default=False)
    visibility = Column(String, default="private") # 'public', 'private', 'friends'
    share_token = Column(String, unique=True, index=True, nullable=True)
    deploy_mode = Column(String, default="chatbot")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="projects")


class FlowExecutionLog(Base):
    __tablename__ = "flow_execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    project_id = Column(Integer, nullable=True, index=True)
    execution_time = Column(DateTime, default=datetime.datetime.utcnow)
    payload = Column(String)
    result = Column(String)
    total_tokens = Column(Integer, default=0)
    token_usage_details = Column(JSON, nullable=True)
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
    latency_ms = Column(Integer, default=0)
    langfuse_trace_id = Column(String, nullable=True, index=True)
    error_message = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        index=True,
    )

    user = relationship("User", foreign_keys=[user_id], backref="generation_traces")


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
