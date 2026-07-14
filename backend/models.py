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

    projects = relationship("Project", back_populates="owner")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, default="Untitled Project")
    description = Column(String, nullable=True)
    graph_data = Column(JSON, default=lambda: {"nodes": [], "edges": []})
    is_public = Column(Boolean, default=False)
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
