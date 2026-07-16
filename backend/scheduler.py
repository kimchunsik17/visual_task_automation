import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from graph import run_workflow
import traceback
import json

scheduler = AsyncIOScheduler()

def execute_scheduled_project(project_id: int):
    """
    Background job to execute a project workflow.
    """
    print(f"[Scheduler] Executing scheduled project {project_id}")
    db = SessionLocal()
    try:
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if not project:
            print(f"[Scheduler] Project {project_id} not found.")
            return

        # 토큰 체크 및 스케줄 중지
        user = db.query(models.User).filter(models.User.id == project.user_id).first()
        if user and user.token_balance <= 0:
            print(f"[Scheduler] Project {project_id} skipped: insufficient tokens.")
            job_id = f"project_{project_id}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            project.deploy_mode = 'chatbot'
            db.commit()
            return

        nodes = project.graph_data.get('nodes', [])
        edges = project.graph_data.get('edges', [])
        
        # We pass a distinct session_id to maintain memory separately if needed,
        # or use a generic 'scheduled_task' session.
        result_text, tokens, logs = run_workflow(
            nodes, 
            edges, 
            db=db, 
            session_id=f"scheduled_{project_id}", 
            project_id=project_id
        )
        
        # Save execution log
        owner_id = project.user_id
        total_tokens = tokens.get('total_tokens', 0) if isinstance(tokens, dict) else 0
        
        if total_tokens > 0:
            user = db.query(models.User).filter(models.User.id == owner_id).first()
            if user:
                user.token_balance -= total_tokens

        exec_log = models.FlowExecutionLog(
            user_id=owner_id,
            project_id=project_id,
            payload=json.dumps({"trigger": "scheduler", "cron": True}, ensure_ascii=False),
            result=result_text,
            total_tokens=total_tokens,
            token_usage_details=tokens
        )
        db.add(exec_log)
        db.commit()
        
        print(f"[Scheduler] Project {project_id} execution completed. Result: {result_text[:50]}...")
    except Exception as e:
        print(f"[Scheduler] Error executing project {project_id}: {str(e)}")
        traceback.print_exc()
    finally:
        db.close()


def sync_project_schedule(project_id: int, project: models.Project):
    """
    Sync a project's schedule. If it has a scheduleNode, add/update the job.
    Otherwise, remove the job if it exists.
    """
    job_id = f"project_{project_id}"
    
    # Check for scheduleNode in the graph
    nodes = project.graph_data.get('nodes', [])
    schedule_node = next((n for n in nodes if n.get('type') == 'scheduleNode'), None)
    
    if schedule_node and project.graph_data.get("is_live", False):
        cron_expr = schedule_node.get('data', {}).get('cronExpression', '0 7 * * *')
        try:
            trigger = CronTrigger.from_crontab(cron_expr)
            
            # If job exists, update it, else add it
            if scheduler.get_job(job_id):
                scheduler.reschedule_job(job_id, trigger=trigger)
                print(f"[Scheduler] Updated schedule for project {project_id} to '{cron_expr}'")
            else:
                scheduler.add_job(
                    execute_scheduled_project,
                    trigger=trigger,
                    args=[project_id],
                    id=job_id,
                    replace_existing=True
                )
                print(f"[Scheduler] Added new schedule for project {project_id} with '{cron_expr}'")
        except ValueError as e:
            print(f"[Scheduler] Invalid cron expression for project {project_id}: {cron_expr}")
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
    else:
        # No scheduleNode or is_live == False, remove job if exists
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            print(f"[Scheduler] Removed schedule for project {project_id}")

def sync_all_schedules(db: Session):
    """
    Called on startup to load all projects and schedule those with scheduleNodes.
    """
    projects = db.query(models.Project).all()
    count = 0
    for p in projects:
        sync_project_schedule(p.id, p)
        if scheduler.get_job(f"project_{p.id}"):
            count += 1
    print(f"[Scheduler] Initialized {count} scheduled projects.")

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        print("[Scheduler] Started AsyncIOScheduler.")
