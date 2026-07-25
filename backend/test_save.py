import json
from database import SessionLocal
import models
from main import create_project, update_project, ProjectCreate

db = SessionLocal()
user = db.query(models.User).first()

payload = ProjectCreate(
    title="Test Project",
    description="Test description",
    graph_data={"nodes": [], "edges": []},
    visibility="private"
)

try:
    print("Testing create_project...")
    res = create_project(payload=payload, user=user, db=db)
    print("create_project success:", res)
except Exception as e:
    print("create_project error:", str(e))

try:
    print("\nTesting update_project...")
    res = update_project(project_id=8, payload=payload, user=user, db=db)
    print("update_project success:", res)
except Exception as e:
    print("update_project error:", str(e))
