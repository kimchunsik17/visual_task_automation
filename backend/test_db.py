import os
import sys
from dotenv import load_dotenv
load_dotenv()

from database import SessionLocal, engine
import models

db = SessionLocal()

tables = [
    models.User, models.Project, models.FlowExecutionLog, models.NodeExecutionLog,
    models.BotLog, models.NodeMemory, models.Friendship, models.FriendRequest, models.ChatSession
]

for model in tables:
    try:
        db.query(model).first()
        print(f"Table {model.__tablename__} OK")
    except Exception as e:
        print(f"Table {model.__tablename__} Error: {type(e).__name__} - {str(e).splitlines()[0]}")
        db.rollback()

db.close()
