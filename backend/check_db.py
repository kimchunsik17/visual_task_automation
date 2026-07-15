from sqlalchemy import create_engine, text
engine = create_engine('postgresql://postgres:1234@localhost:5432/visual_task_automation_db')
conn = engine.connect()
print([col[0] for col in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'flow_execution_logs'")).fetchall()])
