"""부스 시연 시딩(seed_demo_booth)의 그래프 유효성·배선·멱등성 검사."""

from __future__ import annotations

import pathlib
import subprocess
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent


def test_workflow_graphs_pass_dry_run():
    """5개 그래프 전부 컴파일·정적 검증 통과 — 시연 직전에 깨진 그래프가 심기면 안 된다."""
    from dry_run import dry_run_workflow
    from seed_demo_booth import build_workflows

    flows = build_workflows(owner_email="booth@example.com")
    assert len(flows) == 5
    for title, (_desc, nodes, edges) in flows.items():
        result = dry_run_workflow({"nodes": nodes, "edges": edges})
        assert result.success and result.compile_passed, f"{title}: {result.issues}"


def test_app_blueprints_reference_real_targets():
    """앱의 submit 필드가 (1) 실재하는 컴포넌트, (2) 워크플로우의 동적 입력 노드 id 를 가리킨다."""
    from seed_demo_booth import build_apps, build_workflows

    flows = build_workflows(owner_email="booth@example.com")
    dyn_ids = {}
    for title, (_desc, nodes, _edges) in flows.items():
        dyn_ids[title] = {n["id"] for n in nodes if n["type"] == "dynamicInputNode"}

    apps = build_apps({title: index + 1 for index, title in enumerate(flows)})
    assert len(apps) == 2
    for app_title, (ui, logic, mappings) in apps.items():
        component_ids = {c["id"] for c in ui["components"]}
        submit = next(n for n in logic["nodes"] if n["type"] == "submitNode")
        trigger = next(n for n in logic["nodes"] if n["type"] == "triggerNode")
        output = next(n for n in logic["nodes"] if n["type"] == "outputNode")
        assert trigger["data"]["componentId"] in component_ids
        assert output["data"]["componentId"] in component_ids
        all_dyn = set().union(*dyn_ids.values())
        for field in submit["data"]["fields"]:
            assert field["componentId"] in component_ids, f"{app_title}: {field}"
            assert field["name"] in all_dyn, (
                f"{app_title}: submit 필드 '{field['name']}' 가 어떤 워크플로우의 동적 입력 노드 id 와도 "
                f"일치하지 않는다 — 앱 입력이 워크플로우에 전달되지 않는다")
        # 버튼 매핑과 blueprint 의 projectId 가 같은 워크플로우를 가리킨다
        assert mappings[trigger["data"]["componentId"]]["projectId"] == submit["data"]["projectId"]


SCENARIO = r'''
import os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
sys.path.insert(0, sys.argv[2])
os.chdir(os.path.dirname(sys.argv[1].replace("sqlite:///", "")))

from database import engine, SessionLocal, Base
import models
Base.metadata.create_all(engine)

db = SessionLocal()
user = models.User(id=1, google_id="booth", email="booth@example.com", name="booth")
db.add(user)
db.commit()

import seed_demo_booth
result = seed_demo_booth.seed(db, user)

assert len(result["projects"]) == 5 and len(result["apps"]) == 2
assert result["formats"] == ["demo-news-briefing"]

# 포맷이 저장 규칙(validate)을 통과한 상태로 존재한다
fmt = db.query(models.DocumentFormat).get("demo-news-briefing")
assert fmt is not None and fmt.owner_user_id == 1 and fmt.spec["layout"] == "document"

# 워크플로우 5개 — share_token(층 1 QR)과 그래프가 있다
projects = db.query(models.Project).filter(models.Project.user_id == 1).all()
assert len(projects) == 5
for p in projects:
    assert p.title.startswith("[시연] ") and p.share_token and p.graph_data["nodes"]

# 앱 2개 — 매핑이 실재하는 프로젝트 id 를 가리킨다
project_ids = {str(p.id) for p in projects}
apps = db.query(models.CustomApp).filter(models.CustomApp.owner_id == 1).all()
assert len(apps) == 2
for a in apps:
    assert a.ui_graph_data["ui"]["components"] and a.ui_graph_data["logic"]["nodes"]
    for mapping in a.workflow_mappings.values():
        assert mapping["projectId"] in project_ids, a.workflow_mappings

# 멱등성 — 다시 돌려도 개수가 늘지 않고 id 가 유지된다. 목록에서 빠진 옛 [시연] 항목은
# 삭제 대신 "[시연-보관]" 으로 개명된다(실행 로그 FK 보호).
stale = models.Project(user_id=1, title="[시연] 옛 콘텐츠", graph_data={"nodes": [], "edges": []})
db.add(stale)
db.commit()
before_ids = sorted(p.id for p in projects)
result2 = seed_demo_booth.seed(db, user)
live = db.query(models.Project).filter(models.Project.user_id == 1,
                                       models.Project.title.like("[시연] %")).all()
assert sorted(p.id for p in live) == before_ids
db.refresh(stale)
assert stale.title == "[시연-보관] 옛 콘텐츠", stale.title
assert db.query(models.CustomApp).filter(models.CustomApp.owner_id == 1).count() == 2
assert result2["projects"] == result["projects"]

print("DEMO BOOTH SEED ALL OK")
'''


def test_seed_end_to_end(tmp_path):
    scenario_path = tmp_path / "seed_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'seed.db'}"

    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "DEMO BOOTH SEED ALL OK" in result.stdout
