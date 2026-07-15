import re

with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

conflict_pattern = re.compile(r"<<<<<<< HEAD.*?=======\n(.*?)\n>>>>>>> origin/feature/visibility-friends-system", re.DOTALL)

def replacement(match):
    return """
    old_graph_data = project.graph_data or {}
    new_graph_data = payload.graph_data or {}
    if isinstance(old_graph_data, dict) and isinstance(new_graph_data, dict):
        if "discord_bot_token" in old_graph_data:
            new_graph_data["discord_bot_token"] = old_graph_data["discord_bot_token"]
            
    project.graph_data = new_graph_data
    flag_modified(project, "graph_data")
    project.visibility = payload.visibility
"""

content = conflict_pattern.sub(replacement, content, count=1)

with open('backend/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
