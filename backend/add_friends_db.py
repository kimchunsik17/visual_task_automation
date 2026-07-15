import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from models import Base

load_dotenv()
db_url = os.getenv("DATABASE_URL")
print("Connecting to:", db_url)

engine = create_engine(db_url)

# Create missing tables (friendships)
print("Creating missing tables...")
Base.metadata.create_all(bind=engine)

# Alter projects table
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE projects ADD COLUMN visibility VARCHAR DEFAULT 'private'"))
        conn.commit()
        print("Added visibility column to projects table")
    except Exception as e:
        print("Column visibility might already exist:", e)
        
    try:
        conn.execute(text("UPDATE projects SET visibility = 'public' WHERE is_public = true"))
        conn.execute(text("UPDATE projects SET visibility = 'private' WHERE is_public = false"))
        conn.commit()
        print("Migrated existing is_public data to visibility")
    except Exception as e:
        print("Error migrating data:", e)

print("Migration complete.")
