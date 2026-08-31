"""관리 목록 API가 UI에 필요한 비밀 없는 메타데이터를 제공하는지 확인한다."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest


BACKEND_DIR = pathlib.Path(__file__).resolve().parent

SCENARIO = r'''
import os, sys

os.environ["DATABASE_URL"] = sys.argv[1]
sys.path.insert(0, sys.argv[2])

from fastapi.testclient import TestClient
import main, models
from database import SessionLocal

db = SessionLocal()
user = models.User(id=1, google_id="metadata-user", email="meta@example.com", name="metadata")
db.add(user)
db.flush()

project = models.Project(
    user_id=user.id,
    title="운영 자동화",
    description="목록 메타데이터 테스트",
    current_revision=3,
    graph_data={
        "is_live": False,
        "nodes": [
            {"id": "webhook-1", "type": "webhookNode", "data": {}},
            {"id": "discord-1", "type": "discordTriggerNode", "data": {}},
            {"id": "schedule-1", "type": "scheduleNode", "data": {"cronExpression": "0 9 * * 1"}},
        ],
        "edges": [{"id": "edge-1", "source": "webhook-1", "target": "discord-1"}],
    },
)
custom_app = models.CustomApp(
    id="app-metadata",
    owner_id=user.id,
    title="업무 앱",
    ui_graph_data={
        "components": [
            {"id": "container", "type": "container", "children": [
                {"id": "button", "type": "button"},
            ]},
        ],
        "description": "메타데이터 앱",
    },
    workflow_mappings={"button": {"projectId": "1"}},
)
db.add_all([project, custom_app])
db.commit()

main.app.dependency_overrides[main.get_current_user_required] = lambda: user
main.app.dependency_overrides[main.get_current_user] = lambda: user
client = TestClient(main.app)

workflow = client.get("/api/projects/my").json()[0]
assert workflow["node_count"] == 3
assert workflow["edge_count"] == 1
assert workflow["current_revision"] == 3
assert workflow["is_live"] is False
assert workflow["created_at"] and workflow["updated_at"]

app = client.get("/api/apps/custom").json()[0]
assert app["component_count"] == 2
assert app["binding_count"] == 1
assert app["updated_at"]

webhook = client.get("/api/webhooks").json()[0]
assert webhook["projectId"] == project.id
assert webhook["nodeId"] == "webhook-1"
assert webhook["methods"] == ["GET", "POST"]
assert webhook["updatedAt"]

bot = client.get("/api/bots").json()[0]
assert bot["project_id"] == project.id
assert bot["trigger_node_id"] == "discord-1"
assert bot["platform"] == "discord"

schedule = client.get("/api/schedules").json()[0]
assert schedule["project_id"] == project.id
assert schedule["node_id"] == "schedule-1"
assert schedule["cron"] == "0 9 * * 1"
assert schedule["updated_at"]
assert schedule["last_run"] is None
assert schedule["last_outcome"] is None

print("ALL METADATA OK")
'''


def test_management_list_metadata(tmp_path):
    pytest.importorskip("httpx", reason="FastAPI TestClient requires httpx")
    scenario_path = tmp_path / "management_metadata_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'management.db'}"

    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "ALL METADATA OK" in result.stdout
