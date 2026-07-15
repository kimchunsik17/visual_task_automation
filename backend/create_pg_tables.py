import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from models import Base, FlowExecutionLog, NodeExecutionLog

load_dotenv()
db_url = os.getenv("DATABASE_URL")
print("Connecting to:", db_url)

engine = create_engine(db_url)
inspector = inspect(engine)

print("Tables:", inspector.get_table_names())

print("Creating missing tables...")
Base.metadata.create_all(bind=engine)

print("Tables after create_all:", inspect(engine).get_table_names())
