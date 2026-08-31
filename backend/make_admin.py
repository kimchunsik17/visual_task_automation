from database import SessionLocal
from models import User

db = SessionLocal()
users = db.query(User).all()
for u in users:
    print(f"User: {u.email}, is_admin: {u.is_admin}")
    u.is_admin = True
db.commit()
print("All users updated to admin.")
db.close()
