import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from models import Base, FlowExecutionLog, NodeExecutionLog

load_dotenv()
db_url = os.getenv("DATABASE_URL")
print("Connecting to:", db_url)

engine = create_engine(db_url)

with engine.connect() as conn:
    print("Dropping tables...")
    conn.execute(text("DROP TABLE IF EXISTS node_execution_logs CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS flow_execution_logs CASCADE;"))
    conn.commit()

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Done.")
