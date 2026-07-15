from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import FlowExecutionLog
import sys

engine = create_engine('sqlite:///./visual_task.db')
Session = sessionmaker(bind=engine)
session = Session()

try:
    logs = session.query(FlowExecutionLog).all()
    print("Total logs:", len(logs))
    for log in logs[-3:]:
        print(f"ID: {log.id}, Project: {log.project_id}, Status: {log.status}, Date: {log.execution_time}")
except Exception as e:
    print("Error:", e)
