from fastapi import FastAPI, Depends, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Dict, Any
import os
import shutil

from database import engine, Base, get_db
import models
from graph import run_workflow, compile_workflow

# Create DB tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Business Automation API")

# Ensure uploads directory exists
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

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

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Receives a file from the frontend and saves it to the uploads/ directory.
    Returns the file path.
    """
    file_path = os.path.join("uploads", file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"status": "success", "file_path": file_path, "filename": file.filename}

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
