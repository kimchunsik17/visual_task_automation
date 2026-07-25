import os
import sys
from dotenv import load_dotenv
load_dotenv()

from database import SessionLocal, engine
from sqlalchemy import text
import models

db = SessionLocal()

try:
    db.execute(text("ALTER TABLE users ADD COLUMN token_balance INTEGER DEFAULT 50000;"))
    db.commit()
    print("Added token_balance to users")
except Exception as e:
    print(f"Error adding token_balance: {e}")
    db.rollback()

# Test all tables and all columns by querying 1 row
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
