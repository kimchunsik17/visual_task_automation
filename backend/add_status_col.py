from sqlalchemy import create_engine, text
engine = create_engine('postgresql://postgres:1234@localhost:5432/visual_task_automation_db')
with engine.begin() as conn:
    conn.execute(text("ALTER TABLE flow_execution_logs ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'success'"))
    conn.execute(text("ALTER TABLE flow_execution_logs ADD COLUMN IF NOT EXISTS node_id VARCHAR DEFAULT NULL"))
