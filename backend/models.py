from sqlalchemy import Column, Integer, String, JSON, DateTime
from database import Base
import datetime

class FlowExecutionLog(Base):
    __tablename__ = "flow_execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    execution_time = Column(DateTime, default=datetime.datetime.utcnow)
    payload = Column(JSON)
    result = Column(String)
