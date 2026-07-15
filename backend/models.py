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
    token_balance = Column(Integer, default=50000)

    projects = relationship("Project", back_populates="owner")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
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
    project_id = Column(Integer, ForeignKey("projects.id"), index=True)
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
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    friend_id = Column(Integer, ForeignKey("users.id"), index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id], backref="friendships")
    friend = relationship("User", foreign_keys=[friend_id])


class FriendRequest(Base):
    __tablename__ = "friend_requests"

    id = Column(Integer, primary_key=True, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    status = Column(String, default="pending")  # 'pending', 'accepted', 'rejected'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    project_id = Column(String, index=True, nullable=True) # string since it might be 'draft-123' or '45'
    title = Column(String)
    messages = Column(JSON, default=list) # [{role: 'user', content: '...'}, {role: 'ai', content: '...'}]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    user = relationship("User", backref="chat_sessions")

