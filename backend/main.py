from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Dict, Any

from database import engine, Base, get_db
import models
from graph import run_workflow, compile_workflow

# Create DB tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Business Automation API")

# Setup CORS to allow requests from the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], # Vite default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class FlowPayload(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

@app.post("/api/execute")
def execute_flow(payload: FlowPayload, db: Session = Depends(get_db)):
    """
    Receives graph data from frontend, runs LangGraph logic,
    saves execution to DB, and returns the result.
    """
    # 1. Run LangGraph with Gemini
    result_text = run_workflow(payload.nodes, payload.edges)
    
    import json
    # 2. Save log to PostgreSQL (or SQLite fallback)
    try:
        db_log = models.FlowExecutionLog(
            payload=json.dumps(payload.dict()),
            result=result_text
        )
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
    except Exception as e:
        print(f"Failed to save log to DB: {e}")
        db.rollback()

    # 3. Return response to frontend
    return {"status": "success", "result": result_text}

@app.post("/api/compile")
def compile_flow(payload: FlowPayload):
    """
    Parses graph data from frontend and returns raw Python code representation.
    """
    compiled_code = compile_workflow(payload.nodes, payload.edges)
    return {"status": "success", "code": compiled_code}

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import mimetypes

# Fix mimetypes for Windows where .js might be text/plain
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

# Serve frontend static files
# Calculate the absolute path to the frontend/dist directory
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")

if os.path.exists(FRONTEND_DIST):
    # Mount the static files (assets, JS, CSS)
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    # Catch-all route for SPA routing (returns index.html)
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
