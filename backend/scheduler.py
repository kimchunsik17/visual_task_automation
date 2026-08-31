import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from graph import run_workflow
import traceback
import json
from usage_tracking import EVENT_WORKFLOW_EXECUTION, outcome_from_result, record_usage

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
        
        owner_id = project.user_id
        record_usage(
            db,
            billable_user_id=owner_id,
            actor_user_id=None,
            project_id=project_id,
            token_usage=tokens if isinstance(tokens, dict) else None,
            payload=json.dumps({"trigger": "scheduler", "cron": True}, ensure_ascii=False),
            result=result_text,
            event_type=EVENT_WORKFLOW_EXECUTION,
            outcome=outcome_from_result(result_text),
            trigger_type="scheduler",
        )
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

def purge_expired_uploads_job():
    """보존 기간이 지난 업로드를 정리한다 (ADR-0010).

    기록이 없는 파일(이 기능 도입 전에 올라온 것)은 건드리지 않는다 — upload_security 쪽에서
    그렇게 처리한다. 소유자를 모르는 파일을 추측해 지우면 사용자의 결과물이 조용히 사라진다.
    """
    from database import SessionLocal
    from upload_security import purge_expired_uploads

    db = SessionLocal()
    try:
        summary = purge_expired_uploads(db)
        if summary["removed_files"]:
            print(f"[Uploads] 만료 파일 {summary['removed_files']}개 "
                  f"({summary['removed_bytes'] // 1024}KB) 정리")
    except Exception as exc:
        print(f"[Uploads] 만료 파일 정리 실패: {exc}")
    finally:
        db.close()


def purge_rate_limit_counters_job():
    """만료된 rate limit 카운터를 지운다 (ADR-0020).

    고정 윈도우라 행이 시간마다 새로 생긴다. 지우지 않으면 테이블이 단조 증가한다 —
    데이터가 아니라 **잔여물**이므로 보존 정책과 무관하게 정리한다.
    """
    from database import SessionLocal
    import rate_limit

    db = SessionLocal()
    try:
        removed = rate_limit.purge_expired(db)
        if removed:
            print(f"[RateLimit] 만료 카운터 {removed}행 정리")
    except Exception as exc:
        print(f"[RateLimit] 카운터 정리 실패: {exc}")
    finally:
        db.close()


def measure_template_retention_job():
    """설치 7일 뒤에도 프로젝트가 남아 있는지 본다 (ADR-0023 품질 신호).

    설치 수는 조작하기 쉽지만 **7일 유지**는 그렇지 않다 — 가져다 놓고 지웠는지, 계속 쓰는지가
    드러난다. 아직 7일이 지나지 않은 설치는 건드리지 않는다(판단할 시점이 아니다).
    """
    import datetime

    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)
        pending = db.query(models.TemplateInstall).filter(
            models.TemplateInstall.retained_at_7d.is_(None),
            models.TemplateInstall.installed_at <= cutoff,
        ).limit(500).all()
        for row in pending:
            project = db.query(models.Project).filter(
                models.Project.id == row.installed_project_id).first()
            row.retained_at_7d = project is not None
        if pending:
            db.commit()
            print(f"[Templates] 7일 유지 여부 {len(pending)}건 측정")
    except Exception as exc:
        print(f"[Templates] 유지율 측정 실패: {exc}")
    finally:
        db.close()


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        print("[Scheduler] Started AsyncIOScheduler.")
    if not scheduler.get_job("purge_expired_uploads"):
        # 하루 한 번이면 충분하다 — 보존 기간이 일 단위이고, 잦은 삭제는 실행 중인
        # 워크플로우가 참조하는 파일과 경쟁할 위험만 늘린다.
        scheduler.add_job(
            purge_expired_uploads_job,
            "interval",
            hours=24,
            id="purge_expired_uploads",
            replace_existing=True,
        )
        print("[Scheduler] Registered daily upload cleanup.")
    if not scheduler.get_job("purge_rate_limit_counters"):
        # 카운터는 시간 단위로 만료되므로 업로드 정리보다 자주 돈다.
        scheduler.add_job(
            purge_rate_limit_counters_job,
            "interval",
            hours=6,
            id="purge_rate_limit_counters",
            replace_existing=True,
        )
        print("[Scheduler] Registered rate limit counter cleanup.")
    if not scheduler.get_job("measure_template_retention"):
        # 유지 여부는 일 단위 판단이라 하루 한 번이면 충분하다.
        scheduler.add_job(
            measure_template_retention_job,
            "interval",
            hours=24,
            id="measure_template_retention",
            replace_existing=True,
        )
        print("[Scheduler] Registered template retention measurement.")
