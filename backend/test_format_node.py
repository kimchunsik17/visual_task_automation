"""formatNode(포맷 스튜디오 계획 Phase 1)의 계약·코드젠·실행·API 검사."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

import meta_agent
from documents import format_runtime
from dry_run import dry_run_workflow
from graph import compile_workflow

BACKEND_DIR = pathlib.Path(__file__).resolve().parent


# ── 계약 ────────────────────────────────────────────────────────────────

def test_format_node_is_in_generation_contract():
    """카탈로그·출력 스키마 어느 한쪽에만 있으면 2026-08-30 사고(생성 불가 노드)가 재현된다."""
    from typing import get_args
    assert "formatNode" in meta_agent.NODE_CATALOG_ENTRIES
    assert "formatNode" in get_args(meta_agent.NodeType)
    entry = meta_agent.NODE_CATALOG_ENTRIES["formatNode"]
    assert "지어내지 마라" in entry and "incident-report" in entry


def test_catalog_mentions_all_preset_ids():
    """LLM 에게 알려주는 프리셋 id 목록이 실제 프리셋과 어긋나면 안 된다."""
    from documents import format_presets
    entry = meta_agent.NODE_CATALOG_ENTRIES["formatNode"]
    for preset in format_presets.PRESETS:
        assert preset["id"] in entry, f"카탈로그에 프리셋 {preset['id']} 안내가 없다"


# ── 코드젠·dry_run ───────────────────────────────────────────────────────

GRAPH = {
    "nodes": [
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "n2", "type": "valueNode",
         "data": {"value": '{"docNumber": "워크-1", "sender": "운영팀", "receiver": "총무팀", '
                           '"subject": "테스트", "body": "본문", "date": "2026-08-31"}'}},
        {"id": "n3", "type": "formatNode",
         "data": {"formatId": "official-letter", "output": "hwpx"}},
        {"id": "n4", "type": "outputNode", "data": {}},
    ],
    "edges": [
        {"id": "e1", "source": "n1", "target": "n2"},
        {"id": "e2", "source": "n2", "target": "n3"},
        {"id": "e3", "source": "n3", "target": "n4"},
    ],
}


def test_format_node_compiles():
    source = compile_workflow(GRAPH["nodes"], GRAPH["edges"])
    assert not source.startswith("Error"), source[:300]
    assert "format_runtime" in source and "register_generated_file" in source


def test_format_node_dry_run_passes():
    result = dry_run_workflow(GRAPH)
    assert result.success and result.compile_passed, result.issues


def test_format_node_codegen_keeps_node_errors():
    """바인딩(BINDING_*)·artifact 오류는 NodeError 를 품고 온다 — generic except 로 문자열이
    되면 원인 안내가 사라지므로, 전용 except 절이 생성 코드에 있어야 한다."""
    source = compile_workflow(GRAPH["nodes"], GRAPH["edges"])
    assert "except _NodeErrorException" in source


# ── 런타임 단위 ──────────────────────────────────────────────────────────

def test_load_format_finds_presets_and_rejects_unknown():
    spec = format_runtime.load_format("incident-report")
    assert spec["name"] == "시말서"
    with pytest.raises(format_runtime.FormatNodeError) as exc:
        format_runtime.load_format("made-up-format")
    assert exc.value.reason == "FORMAT_NOT_FOUND"
    with pytest.raises(format_runtime.FormatNodeError):
        format_runtime.load_format("")


def test_values_from_accepts_fenced_json_and_dict():
    assert format_runtime._values_from("", '```json\n{"a": 1}\n```') == {"a": 1}
    assert format_runtime._values_from('{"b": 2}', "무시된다") == {"b": 2}
    assert format_runtime._values_from("", "JSON 아님") == {}
    assert format_runtime._values_from("", {"c": 3}) == {"c": 3}


def test_run_missing_required_reports_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # uploads/ 가 저장소에 생기지 않게
    with pytest.raises(format_runtime.FormatNodeError) as exc:
        format_runtime.run(format_id="official-letter", incoming='{"subject": "제목만"}')
    assert exc.value.reason == "FORMAT_FIELD_MISSING"
    assert "docNumber" in exc.value.missing_fields


def test_run_rejects_output_outside_spec_allowed():
    """정본(output.allowed) 밖 조합 — 시말서를 xlsx 로 — 은 렌더 전에 거부된다(감사 지적).
    layout 단위 검사만으로는 이 조합이 조용히 성공해 이상한 파일이 첨부됐다."""
    with pytest.raises(format_runtime.FormatNodeError) as exc:
        format_runtime.run(format_id="incident-report", output="xlsx", incoming="{}")
    assert exc.value.reason == "FORMAT_OUTPUT_UNSUPPORTED"
    with pytest.raises(format_runtime.FormatNodeError) as exc2:
        format_runtime.run(format_id="event-poster", output="hwpx", incoming="{}")
    assert exc2.value.reason == "FORMAT_OUTPUT_UNSUPPORTED"


_OFFICIAL_LETTER_VALUES = ('{"docNumber": "워크-1", "sender": "운영팀", "receiver": "총무팀", '
                           '"subject": "테스트", "body": "본문", "date": "2026-08-31"}')


def test_run_converts_renderer_errors_to_format_error(tmp_path, monkeypatch):
    """하위 렌더러·이미지 로더의 SpecError 가 FORMAT_* 로 변환된다 — 그대로 새면 생성 코드의
    generic except 가 '문서 포맷 처리 실패' 로 뭉개 사용자 안내가 사라진다."""
    from documents import hwpx
    monkeypatch.chdir(tmp_path)

    def _boom(*_args, **_kwargs):
        raise hwpx.SpecError("이미지를 열 수 없습니다(a1): 보존 기간이 지났습니다")

    monkeypatch.setattr(format_runtime, "render_format", _boom)
    with pytest.raises(format_runtime.FormatNodeError) as exc:
        format_runtime.run(format_id="official-letter", incoming=_OFFICIAL_LETTER_VALUES)
    assert exc.value.reason == "FORMAT_SPEC_INVALID"
    assert "이미지를 열 수 없습니다" in str(exc.value)


def test_run_rejects_empty_output_filename(tmp_path, monkeypatch):
    """output_path 가 이름 없는 경로면 HwpxNodeError 가 아니라 FORMAT_* 로 멈춘다."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(format_runtime.FormatNodeError) as exc:
        format_runtime.run(format_id="official-letter", output_path="   /",
                           incoming=_OFFICIAL_LETTER_VALUES)
    assert exc.value.reason == "FORMAT_SPEC_INVALID"


def test_run_renders_preset_from_incoming_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = format_runtime.run(
        format_id="official-letter", output="docx",
        incoming='{"docNumber": "워크-1", "sender": "운영팀", "receiver": "총무팀", '
                 '"subject": "테스트", "body": "본문", "date": "2026-08-31"}')
    path = tmp_path / result["path"]
    assert path.exists() and path.stat().st_size > 0
    assert result["output"] == "docx" and result["layout"] == "document"


# ── 실행·API 통합 (sqlite 서브프로세스 — 저장소 관례) ────────────────────

SCENARIO = r'''
import os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
sys.path.insert(0, sys.argv[2])
os.chdir(os.path.dirname(sys.argv[1].replace("sqlite:///", "")))  # uploads/ 를 tmp 에

from fastapi.testclient import TestClient
import main, models
from database import SessionLocal

db = SessionLocal()
user = models.User(id=1, google_id="fmt-user", email="fmt@example.com", name="fmt")
db.add(user)
db.flush()
# 실행의 소유자(owner_user_id)는 project_id 에서 파생된다 — 에디터가 실행 전 자동 저장하는
# 실제 경로와 동일하게 프로젝트를 만들어 넘긴다.
project = models.Project(user_id=user.id, title="포맷 테스트", graph_data={"nodes": [], "edges": []})
db.add(project)
db.commit()

main.app.dependency_overrides[main.get_current_user_required] = lambda: user
main.app.dependency_overrides[main.get_current_user] = lambda: user
client = TestClient(main.app)

# 1) 프리셋 목록
presets = client.get("/api/formats/presets").json()["formats"]
assert any(p["id"] == "incident-report" for p in presets), "프리셋 API 에 시말서가 없다"

# 2) CRUD — 생성(검증 통과) → 목록 → 수정 → 삭제
spec = {
    "version": 1, "layout": "document",
    "fields": [{"name": "who", "label": "누가", "kind": "text", "required": True}],
    "blocks": [{"type": "paragraph", "text": "{{who}} 님께"}],
}
created = client.post("/api/formats", json={"name": "내 인사장", "spec": spec})
assert created.status_code == 200, created.text
fmt_id = created.json()["id"]
assert client.get("/api/formats").json()["formats"][0]["name"] == "내 인사장"

bad = client.post("/api/formats", json={"name": "x", "spec": {"layout": "document", "fields": [], "blocks": [{"type": "paragraph", "text": "{{ghost}}"}]}})
assert bad.status_code == 422, "잘못된 스펙이 저장을 통과했다"

updated = client.put(f"/api/formats/{fmt_id}", json={"name": "내 인사장 v2", "spec": spec})
assert updated.status_code == 200 and updated.json()["name"] == "내 인사장 v2"

# 3) 실행 — 사용자 포맷을 formatNode 로 렌더 (run_workflow 전체 경로)
import graph as graph_mod
nodes = [
    {"id": "n1", "type": "startNode", "data": {}},
    {"id": "n2", "type": "valueNode", "data": {"value": '{"who": "김워크"}'}},
    {"id": "n3", "type": "formatNode", "data": {"formatId": fmt_id, "output": "docx"}},
    {"id": "n4", "type": "outputNode", "data": {}},
]
edges = [
    {"id": "e1", "source": "n1", "target": "n2"},
    {"id": "e2", "source": "n2", "target": "n3"},
    {"id": "e3", "source": "n3", "target": "n4"},
]
response_text, _tokens, logs = graph_mod.run_workflow(nodes, edges, db=db, project_id=project.id)
fmt_log = next(l for l in (logs or []) if l["node_id"] == "n3")
assert fmt_log["status"] == "success", fmt_log
assert fmt_log.get("artifacts"), "완성 파일이 artifact 로 등록되지 않았다"
assert str(response_text).endswith(".docx"), response_text

# 4) 실행 — 필수 빈칸 누락이 FORMAT_FIELD_MISSING 으로 남는다
nodes_missing = [
    {"id": "n1", "type": "startNode", "data": {}},
    {"id": "n3", "type": "formatNode", "data": {"formatId": fmt_id, "output": "docx"}},
    {"id": "n4", "type": "outputNode", "data": {}},
]
edges_missing = [
    {"id": "e1", "source": "n1", "target": "n3"},
    {"id": "e2", "source": "n3", "target": "n4"},
]
_resp2, _tok2, logs2 = graph_mod.run_workflow(nodes_missing, edges_missing, db=db, project_id=project.id)
err_log = next(l for l in (logs2 or []) if l["node_id"] == "n3")
assert err_log["status"] == "error" and err_log["error"]["code"] == "FORMAT_FIELD_MISSING", err_log

# 5) 소유 격리 — 남의 포맷은 실행에서도 열리지 않는다
other = models.User(id=2, google_id="fmt-other", email="other@example.com", name="other")
db.add(other); db.commit()
from documents import format_runtime as rt
try:
    rt.load_format(fmt_id, db=db, owner_user_id=other.id)
    raise SystemExit("남의 포맷이 열렸다")
except rt.FormatNodeError as e:
    assert e.reason == "FORMAT_NOT_FOUND"

# 6) 삭제
assert client.delete(f"/api/formats/{fmt_id}").status_code == 200
assert client.get("/api/formats").json()["formats"] == []

print("FORMAT NODE ALL OK")
'''


def test_format_node_end_to_end(tmp_path):
    pytest.importorskip("httpx", reason="FastAPI TestClient requires httpx")
    scenario_path = tmp_path / "format_node_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'format.db'}"

    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "FORMAT NODE ALL OK" in result.stdout


# ── AI 생성 (Phase 2) — LLM 을 모의하고 검증 관문만 본다 ─────────────────

def test_generate_format_spec_validates_llm_output(monkeypatch):
    import format_studio

    class _FakeStructured:
        def __init__(self, result): self._result = result
        def invoke(self, _messages): return self._result

    class _FakeLLM:
        def __init__(self, result): self._result = result
        def with_structured_output(self, *_a, **_k): return _FakeStructured(self._result)

    good = format_studio.GeneratedFormatSpec(
        name="주간 보고", layout="document",
        fields=[format_studio.GeneratedField(name="summary", label="요약", kind="multiline", required=True)],
        blocks=[format_studio.GeneratedBlock(type="heading", level=1, text="주간 보고"),
                format_studio.GeneratedBlock(type="paragraph", text="{{summary}}")])
    monkeypatch.setattr("meta_agent.get_llm", lambda **_k: _FakeLLM(good))
    spec = format_studio.generate_format_spec("주간 보고서 양식")
    assert spec["layout"] == "document" and spec["fields"][0]["name"] == "summary"

    # LLM 이 규칙을 어기면(미선언 변수 참조) 저장 전에 걸린다
    bad = format_studio.GeneratedFormatSpec(
        name="x", layout="document", fields=[],
        blocks=[format_studio.GeneratedBlock(type="paragraph", text="{{ghost}}")])
    monkeypatch.setattr("meta_agent.get_llm", lambda **_k: _FakeLLM(bad))
    from documents.format_spec import FormatSpecError
    with pytest.raises(FormatSpecError):
        format_studio.generate_format_spec("아무거나")


def test_generate_rejects_empty_and_oversized_prompt():
    import format_studio
    from documents.format_spec import FormatSpecError
    with pytest.raises(FormatSpecError):
        format_studio.generate_format_spec("")
    with pytest.raises(FormatSpecError):
        format_studio.generate_format_spec("가" * 3000)

