import os
import sys

# Add backend directory to sys.path to import database
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

from sqlalchemy import text
from database import engine

def run_migration():
    try:
        with engine.connect() as conn:
            # PostgreSQL and SQLite syntax for adding a column with default value
            conn.execute(text("ALTER TABLE users ADD COLUMN token_balance INTEGER DEFAULT 50000;"))
            conn.commit()
            print("Successfully added token_balance column to users table.")
    except Exception as e:
        print(f"Migration failed or already applied: {e}")

if __name__ == "__main__":
    run_migration()
