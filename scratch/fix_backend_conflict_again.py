import re

with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

conflict_pattern = re.compile(r"<<<<<<< HEAD.*?=======\n(.*?)\n>>>>>>> origin/feature/visibility-friends-system", re.DOTALL)

def replacement(match):
    return """
    try:
        if scheduler.scheduler.get_job(f"project_{project_id}"):
            scheduler.scheduler.remove_job(f"project_{project_id}")
    except Exception as e:
        print(f"Failed to remove schedule: {e}")

    # Stop bot if running
    discord_bot.stop_discord_bot(project_id)
    
    # Delete bot logs to avoid IntegrityError
    db.query(models.BotLog).filter(models.BotLog.project_id == project_id).delete(synchronize_session=False)
"""

content = conflict_pattern.sub(replacement, content, count=1)

with open('backend/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
