import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE projects ADD COLUMN share_token VARCHAR;"))
        conn.execute(text("CREATE UNIQUE INDEX ix_projects_share_token ON projects (share_token);"))
        conn.commit()
        print("Column share_token added successfully.")
    except Exception as e:
        print("Column might already exist or error:", e)
        conn.rollback()
