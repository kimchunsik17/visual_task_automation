import os
import sys

# Add backend directory to sys.path to import database
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

from database import SessionLocal
import models
import main

def test_stats():
    db = SessionLocal()
    try:
        user2 = db.query(models.User).filter(models.User.id == 2).first()
        user3 = db.query(models.User).filter(models.User.id == 3).first()
        
        if user2:
            stats2 = main.get_statistics("weekly", user=user2, db=db)
            print(f"Stats for ID 2: remaining={stats2['remaining']}")
            
        if user3:
            stats3 = main.get_statistics("weekly", user=user3, db=db)
            print(f"Stats for ID 3: remaining={stats3['remaining']}")
    finally:
        db.close()

if __name__ == "__main__":
    test_stats()
