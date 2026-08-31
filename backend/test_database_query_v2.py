"""Database Query v2 — PostgreSQL 실작동 vertical slice (ADR-0017, 우선 백로그 19) 계약 테스트.

§4.9 검증 매트릭스의 층을 따른다 — 단위(AST 판별·바인드 파라미터·직렬화·redaction), 정책(egress·
driver·TLS), 자격증명(명명·해석), 실행 경로(run_workflow), API(subprocess 시나리오), PostgreSQL 통합
(`TEST_POSTGRES_URL` 이 있을 때만; 없으면 skip — CI 는 임시 PostgreSQL 을 띄우고 이 변수를 넣는다).
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database_credentials as credentials
import database_diagnostics as diagnostics
import database_policy as policy
import db_query_parameters as params
import meta_agent
import models
import node_definition
from credential_crypto import encrypt_secret
from database import Base
from db_query_runtime import _apply_readonly_session, run_readonly_query, run_readonly_query_result
from graph import compile_workflow, run_workflow
from sql_guard import QueryRejected, analyze_read_query

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
REF = "{{API_CENTER:database}}"


# ── 1. SQL 판별기 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("query, reason", [
    ("INSERT INTO t VALUES (1)", "not_a_read_query"),
    ("UPDATE t SET a = 1 WHERE id = 1", "not_a_read_query"),
    ("DROP TABLE t", "not_a_read_query"),
    ("SELECT 1; DROP TABLE t", "multiple_statements"),
    ("WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d", "write_statement"),
    ("WITH u AS (UPDATE t SET a = 1 RETURNING *) SELECT * FROM u", "write_statement"),
    ("SELECT * FROM t FOR UPDATE", "locking_clause"),
    ("SELECT * INTO newt FROM t", "select_into"),
    ("SELECT pg_read_file('/etc/passwd')", "forbidden_function"),
    ("SELECT pg_sleep(30)", "forbidden_function"),
    ("SELECT set_config('x', 'y', false)", "forbidden_function"),
    ("SELECT * FROM sales.orders", "schema_not_allowed"),
    ("SELECT * FROM pg_catalog.pg_tables", "system_schema"),
    ("SELECT * FROM information_schema.tables", "system_schema"),
    ("SELECT * FROM t WHERE id = $1", "positional_parameter"),
    ("SELECT * FROM t WHERE id = ?", "positional_parameter"),
    ("", "empty"),
    ("SELECT * FROM t WHERE (", "unparseable"),
])
def test_guard_rejects_everything_that_is_not_a_plain_read(query, reason):
    with pytest.raises(QueryRejected) as caught:
        analyze_read_query(query, allowed_schemas=["public"])
    assert caught.value.reason == reason


def test_guard_accepts_reads_and_extracts_placeholders_and_tables():
    analysis = analyze_read_query(
        "WITH recent AS (SELECT * FROM orders WHERE created_at >= :since) "
        "SELECT r.id, u.name FROM recent r JOIN public.users u ON u.id = r.user_id WHERE u.tier = :tier AND r.total > :min_total",
        allowed_schemas=["public"],
    )
    assert analysis.placeholders == ["since", "tier", "min_total"]            # 등장 순, 중복 제거
    assert (None, "orders") in analysis.tables and ("public", "users") in analysis.tables
    assert all(name != "recent" for _, name in analysis.tables)               # CTE 이름은 테이블이 아니다
    union = analyze_read_query("SELECT 1 AS a UNION ALL SELECT 2", allowed_schemas=["public"])
    assert union.placeholders == []
    other_schema = analyze_read_query("SELECT * FROM sales.orders", allowed_schemas=["public", "sales"])
    assert ("sales", "orders") in other_schema.tables


def test_generation_time_validation_uses_the_same_guard():
    node = meta_agent.FlowNode(id="d1", type="databaseNode", data={"connectionString": REF, "query": "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d"})
    errors = meta_agent._validate_node_data(node)
    assert any("바꾸는 구문" in e for e in errors)
    node = meta_agent.FlowNode(id="d1", type="databaseNode", data={"connectionString": REF, "query": "SELECT * FROM t WHERE id = :uid"})
    errors = meta_agent._validate_node_data(node)
    assert any(":uid" in e and "parameters" in e for e in errors)
    node = meta_agent.FlowNode(id="d1", type="databaseNode",
                               data={"connectionString": REF, "query": "SELECT * FROM t WHERE id = :uid", "parameters": [{"name": "uid", "source": "value", "value": "1", "type": "integer"}]})
    assert meta_agent._validate_node_data(node) == []


def test_definition_validates_parameter_items_and_limits():
    errors = node_definition.validate_node_data("databaseNode", "d1", {
        "query": "SELECT 1", "parameters": [{"name": "", "source": "value"}, {"name": "a", "type": "string"}, {"name": "a"}],
        "maxRows": 0, "timeoutSeconds": "abc", "outputFormat": "xml",
    })
    joined = "\n".join(errors)
    assert "name이 없다" in joined and "중복" in joined and "maxRows는 1 이상" in joined
    assert "timeoutSeconds는 숫자" in joined and "outputFormat" in joined


# ── 2. 바인드 파라미터 ────────────────────────────────────────────────────
def test_parameters_bind_by_type_and_source():
    definitions = [
        {"name": "who", "source": "input", "path": "customer.name", "type": "string"},
        {"name": "minp", "source": "input", "path": "filters[0].min", "type": "number"},
        {"name": "active", "source": "value", "value": "true", "type": "boolean"},
        {"name": "since", "source": "value", "value": "2026-01-02", "type": "date"},
        {"name": "unused", "source": "value", "value": "x", "type": "string"},
    ]
    upstream = json.dumps({"customer": {"name": "b"}, "filters": [{"min": "2.5"}]})
    bound = params.bind_parameters(definitions, ["who", "minp", "active", "since"], upstream)
    assert bound == {"who": "b", "minp": 2.5, "active": True, "since": __import__("datetime").date(2026, 1, 2)}
    assert "unused" not in bound                                              # 선언만 있고 쿼리에 없으면 바인드하지 않는다
    whole = params.bind_parameters([{"name": "raw", "source": "input", "path": "", "type": "string"}], ["raw"], "plain text")
    assert whole == {"raw": "plain text"}
    overridden = params.bind_parameters(definitions[:1], ["who"], upstream, overrides={"who": "z"})
    assert overridden == {"who": "z"}


@pytest.mark.parametrize("definitions, placeholders, upstream, code, needle", [
    ([], ["uid"], None, "VALIDATION_REQUIRED", ":uid"),
    ([{"name": "uid", "source": "value", "value": "", "required": True}], ["uid"], None, "VALIDATION_REQUIRED", "비어"),
    ([{"name": "uid", "source": "value", "value": "abc", "type": "integer"}], ["uid"], None, "VALIDATION_INVALID_TYPE", "integer"),
    ([{"name": "uid", "source": "input", "path": "nope", "type": "string"}], ["uid"], '{"a": 1}', "VALIDATION_REQUIRED", "비어"),
    ([{"name": "bad-name", "source": "value", "value": "1"}], [], None, "VALIDATION_INVALID_TYPE", "밑줄"),
    ([{"name": "a", "source": "value", "value": "1"}, {"name": "a", "source": "value", "value": "2"}], [], None, "VALIDATION_INVALID_TYPE", "중복"),
])
def test_parameter_problems_are_validation_errors_before_any_connection(definitions, placeholders, upstream, code, needle):
    with pytest.raises(params.ParameterError) as caught:
        params.bind_parameters(definitions, placeholders, upstream)
    assert caught.value.error.code == code and needle in caught.value.error.user_message
    assert caught.value.error.field.startswith("parameters")


def test_optional_parameter_without_value_binds_null():
    bound = params.bind_parameters([{"name": "q", "source": "input", "path": "missing", "required": False}], ["q"], "{}")
    assert bound == {"q": None}


# ── 3. 접속 정책 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("connection_string, code, phase", [
    ("postgresql://u:p@localhost/db", "DATABASE_CONNECTION_FAILED", "egress_policy"),
    ("postgresql://u:p@127.0.0.1/db", "DATABASE_CONNECTION_FAILED", "egress_policy"),
    ("postgresql://u:p@[::1]/db", "DATABASE_CONNECTION_FAILED", "egress_policy"),
    ("postgresql://u:p@169.254.169.254/db", "DATABASE_CONNECTION_FAILED", "egress_policy"),
    ("postgresql://u:p@10.0.0.5/db", "DATABASE_CONNECTION_FAILED", "egress_policy"),
    ("postgresql://u:p@192.168.1.10/db", "DATABASE_CONNECTION_FAILED", "egress_policy"),
    ("mysql+pymysql://u:p@example.com/db", "DATABASE_DRIVER_MISSING", None),
    ("nonsense", "CREDENTIAL_INVALID", None),
])
def test_policy_blocks_internal_targets_and_unsupported_drivers(monkeypatch, connection_string, code, phase):
    monkeypatch.delenv("DATABASE_QUERY_ALLOW_PRIVATE_HOSTS", raising=False)
    with pytest.raises(policy.PolicyViolation) as caught:
        policy.prepare_connection(connection_string, timeout_seconds=3)
    assert caught.value.code == code
    if phase:
        assert caught.value.safe_details["phase"] == phase


def test_policy_pins_dns_and_defaults_to_tls(monkeypatch):
    monkeypatch.setattr(policy, "resolve_host", lambda host, port: ["93.184.216.34"])
    monkeypatch.delenv("DATABASE_QUERY_DEFAULT_SSLMODE", raising=False)
    spec = policy.prepare_connection("postgresql://u:p@db.example.com:5433/app", timeout_seconds=7)
    assert spec.dialect == "postgresql" and spec.resolved_ip == "93.184.216.34" and spec.port == 5433
    assert spec.connect_args == {"connect_timeout": 7, "hostaddr": "93.184.216.34", "sslmode": "require"}
    explicit = policy.prepare_connection("postgresql://u:p@db.example.com/app?sslmode=disable", timeout_seconds=7)
    assert "sslmode" not in explicit.connect_args                             # 사용자가 명시하면 존중한다
    monkeypatch.setattr(policy, "resolve_host", lambda host, port: [])
    with pytest.raises(policy.PolicyViolation) as caught:
        policy.prepare_connection("postgresql://u:p@nope.invalid/app")
    assert caught.value.safe_details["phase"] == "dns"


def test_private_hosts_open_only_with_the_self_host_flag(monkeypatch):
    monkeypatch.setattr(policy, "resolve_host", lambda host, port: ["10.1.2.3"])
    monkeypatch.setenv("DATABASE_QUERY_ALLOW_PRIVATE_HOSTS", "1")
    spec = policy.prepare_connection("postgresql://u:p@db.internal/app")
    assert spec.resolved_ip == "10.1.2.3"
    monkeypatch.setenv("DATABASE_QUERY_ALLOW_PRIVATE_HOSTS", "0")
    with pytest.raises(policy.PolicyViolation):
        policy.prepare_connection("postgresql://u:p@db.internal/app")


def test_sqlite_is_a_test_fixture_not_a_production_target(monkeypatch):
    monkeypatch.setenv("DATABASE_QUERY_ALLOW_SQLITE", "0")
    with pytest.raises(policy.PolicyViolation) as caught:
        policy.prepare_connection("sqlite:////etc/passwd")
    assert caught.value.code == "DATABASE_DRIVER_MISSING"
    result = run_readonly_query_result("sqlite:////etc/passwd", "SELECT 1")
    assert result.status == "error" and result.error.code == "DATABASE_DRIVER_MISSING"


# ── 4. 명명된 자격증명 ─────────────────────────────────────────────────────
@pytest.fixture
def sqlite_db(tmp_path):
    path = tmp_path / "data.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, price REAL, created_at TEXT)"))
        conn.execute(text("INSERT INTO items (name, price, created_at) VALUES ('a', 1.5, '2026-01-01'), ('b', 2.5, '2026-02-01'), ('c', 3.5, '2026-03-01')"))
    engine.dispose()
    return f"sqlite:///{path}"


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        models.User(id=1, name="Owner", email="owner@example.com"),
        models.User(id=2, name="Other", email="other@example.com"),
        models.Project(id=10, user_id=1, title="db", graph_data={}),
    ])
    session.commit()
    yield session
    session.close()


def test_reference_format_and_labels(db, sqlite_db):
    assert credentials.parse_reference(REF) is None and credentials.parse_reference("{{API_CENTER:database#7}}") == 7
    assert credentials.make_reference(None) == REF and credentials.make_reference(7) == "{{API_CENTER:database#7}}"
    assert not credentials.is_reference("postgresql://u:p@h/db")
    with pytest.raises(ValueError):
        credentials.create(db, 1, label="bad", connection_string="not a uri")
    row = credentials.create(db, 1, label="운영", connection_string=sqlite_db)
    listed = credentials.list_credentials(db, 1)
    assert [c["label"] for c in listed] == ["운영"] and listed[0]["id"] == row.id and listed[0]["dialect"] == "sqlite"
    assert sqlite_db not in json.dumps(listed) and row.label == "운영"           # 목록에는 비밀이 없다
    assert credentials.list_credentials(db, 2) == []                            # 다른 사용자에게는 보이지 않는다
    assert credentials.delete(db, 2, row.id) is False and credentials.delete(db, 1, row.id) is True


def test_reference_resolution_rules(db, sqlite_db):
    from node_errors import NodeErrorException

    with pytest.raises(NodeErrorException) as caught:
        credentials.resolve(db, 1, REF)
    assert caught.value.error.code == "CREDENTIAL_MISSING" and "API 센터" in caught.value.error.user_message

    first = credentials.create(db, 1, label="첫째", connection_string=sqlite_db)
    secret, summary = credentials.resolve(db, 1, REF)
    assert secret == sqlite_db and summary["id"] == first.id

    second = credentials.create(db, 1, label="둘째", connection_string=sqlite_db)
    with pytest.raises(NodeErrorException) as caught:
        credentials.resolve(db, 1, REF)                                          # 여러 개면 자동 선택하지 않는다
    assert caught.value.error.code == "VALIDATION_REQUIRED" and caught.value.error.field == "connectionString"
    assert credentials.resolve(db, 1, credentials.make_reference(second.id))[1]["label"] == "둘째"

    with pytest.raises(NodeErrorException) as caught:
        credentials.resolve(db, 2, credentials.make_reference(first.id))          # 남의 자격증명
    assert caught.value.error.code == "CREDENTIAL_MISSING"
    with pytest.raises(NodeErrorException) as caught:
        credentials.resolve(None, 1, REF)
    assert caught.value.error.code == "CREDENTIAL_MISSING"


# ── 5. 실행 경로 ─────────────────────────────────────────────────────────
def _graph(query, *, connection=REF, upstream_value=None, **extra):
    nodes = [{"id": "s1", "type": "startNode", "data": {}}]
    edges = []
    previous = "s1"
    if upstream_value is not None:
        nodes.append({"id": "v1", "type": "valueNode", "data": {"value": upstream_value}})
        edges.append({"source": "s1", "target": "v1"})
        previous = "v1"
    nodes += [{"id": "d1", "type": "databaseNode", "data": {"connectionString": connection, "query": query, **extra}},
              {"id": "o1", "type": "outputNode", "data": {}}]
    edges += [{"source": previous, "target": "d1"}, {"source": "d1", "target": "o1"}]
    return nodes, edges


def _run(db, nodes, edges):
    result_text, _, logs = run_workflow(nodes, edges, db=db, project_id=10, default_input="")
    return result_text, next(step for step in logs if step["node_id"] == "d1")


def test_generated_code_carries_the_reference_not_the_uri(db, sqlite_db):
    credentials.create(db, 1, label="운영", connection_string=sqlite_db)
    source = compile_workflow(*_graph("SELECT id FROM items"))
    assert sqlite_db not in source and 'credential_ref="{{API_CENTER:database}}"' in source
    assert "owner_user_id=__owner_user_id__" in source


def test_workflow_reads_through_the_named_credential(db, sqlite_db):
    row = credentials.create(db, 1, label="운영", connection_string=sqlite_db)
    result_text, step = _run(db, *_graph("SELECT id, name FROM items ORDER BY id"))
    assert step["status"] == "success" and step["error"] is None
    assert json.loads(result_text) == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c"}]
    assert sqlite_db not in json.dumps(step)                                    # 로그에도 URI 는 없다
    result_text, step = _run(db, *_graph("SELECT count(*) AS c FROM items", connection=credentials.make_reference(row.id)))
    assert json.loads(result_text) == [{"c": 3}]


def test_parameters_flow_from_upstream_json(db, sqlite_db):
    credentials.create(db, 1, label="운영", connection_string=sqlite_db)
    upstream = json.dumps({"customer": {"name": "b"}, "min": "2"})
    result_text, step = _run(db, *_graph(
        "SELECT name, price FROM items WHERE name = :who AND price >= :minp",
        upstream_value=upstream,
        parameters=[{"name": "who", "source": "input", "path": "customer.name", "type": "string"},
                    {"name": "minp", "source": "input", "path": "min", "type": "number"}],
    ))
    assert step["status"] == "success", step
    assert json.loads(result_text) == [{"name": "b", "price": 2.5}]

    _, step = _run(db, *_graph("SELECT * FROM items WHERE id = :missing"))
    assert step["error"]["code"] == "VALIDATION_REQUIRED" and ":missing" in step["error"]["userMessage"]


def test_output_format_result_gives_downstream_a_typed_envelope(db, sqlite_db):
    credentials.create(db, 1, label="운영", connection_string=sqlite_db)
    result_text, step = _run(db, *_graph("SELECT count(*) AS c FROM items", outputFormat="result"))
    envelope = json.loads(result_text)
    assert envelope["ok"] is True and envelope["data"]["rows"] == [{"c": 3}] and envelope["data"]["rowCount"] == 1
    assert envelope["data"]["columns"] == [{"name": "c", "type": "integer"}] and envelope["data"]["truncated"] is False
    assert envelope["error"] is None
    result_text, step = _run(db, *_graph("DELETE FROM items", outputFormat="result"))
    envelope = json.loads(result_text)
    assert envelope["ok"] is False and envelope["error"]["code"] == "DATABASE_QUERY_REJECTED"


def test_rejections_and_missing_credentials_are_structured(db, sqlite_db):
    _, step = _run(db, *_graph("SELECT 1"))
    assert step["error"]["code"] == "CREDENTIAL_MISSING" and step["error"]["field"] == "connectionString"
    credentials.create(db, 1, label="운영", connection_string=sqlite_db)
    _, step = _run(db, *_graph("WITH d AS (DELETE FROM items RETURNING *) SELECT * FROM d"))
    assert step["error"]["code"] == "DATABASE_QUERY_REJECTED" and step["error"]["safeDetails"]["reason"] == "write_statement"
    _, step = _run(db, *_graph("SELECT * FROM other.items"))
    assert step["error"]["safeDetails"]["reason"] == "schema_not_allowed"
    result_text, step = _run(db, *_graph("SELECT * FROM other.items", allowedSchemas="public, other"))
    assert step["error"]["code"] == "DATABASE_QUERY_FAILED"                        # 허용 schema 통과 → DB 가 없는 테이블로 거절
    credentials.create(db, 1, label="둘째", connection_string=sqlite_db)
    result_text, step = _run(db, *_graph("SELECT 1"))
    assert step["error"]["code"] == "VALIDATION_REQUIRED" and "여러 개" in result_text


def test_row_limits_and_legacy_string_wrapper_still_work(db, sqlite_db):
    result = run_readonly_query_result(sqlite_db, "SELECT * FROM items", max_rows=2)
    assert result.ok and result.data["truncated"] is True and result.data["rowCount"] == 2
    assert "[⚠️" in str(result) and "생략" in str(result)
    assert json.loads(run_readonly_query(sqlite_db, "SELECT count(*) AS c FROM items")) == [{"c": 3}]
    assert run_readonly_query(sqlite_db, "INSERT INTO items (name) VALUES ('x')").startswith("Database Error:")


def test_v1_fallback_flag_uses_the_substituted_uri(monkeypatch, db, sqlite_db):
    monkeypatch.setenv("DATABASE_QUERY_V2", "0")
    credentials.create(db, 1, label="운영", connection_string=sqlite_db)
    result_text, step = _run(db, *_graph("SELECT count(*) AS c FROM items"))
    assert step["status"] == "success" and json.loads(result_text) == [{"c": 3}]
    source = compile_workflow(*_graph("SELECT 1"))
    assert "credential_ref=" not in source


def test_diagnostics_on_sqlite(db, sqlite_db):
    row = credentials.create(db, 1, label="운영", connection_string=sqlite_db)
    report = diagnostics.test_connection(sqlite_db)
    assert report["ok"] is True and [s["stage"] for s in report["stages"]] == ["driver", "auth", "readonly_probe"]
    schema = diagnostics.fetch_schema(row.id, sqlite_db, schema="main")
    assert schema["ok"] and [t["name"] for t in schema["tables"]] == ["items"]
    assert [c["name"] for c in schema["tables"][0]["columns"]] == ["id", "name", "price", "created_at"]
    assert diagnostics.fetch_schema(row.id, sqlite_db, schema="main")["cached"] is True
    diagnostics.invalidate_schema_cache(row.id)
    assert diagnostics.fetch_schema(row.id, sqlite_db, schema="main")["cached"] is False
    failed = diagnostics.test_connection("postgresql://u:p@127.0.0.1:9/nope")
    assert failed["ok"] is False and failed["error"]["code"] == "DATABASE_CONNECTION_FAILED" and "127.0.0.1" not in json.dumps(failed)


def test_builtin_templates_carry_no_plaintext_database_uris():
    template_source = (REPO_ROOT / "frontend" / "src" / "TemplateModal.jsx").read_text(encoding="utf-8")
    assert "sqlite:///" not in template_source
    for match in re.finditer(r"type: 'databaseNode'.*?connectionString: '([^']*)'", template_source):
        assert credentials.is_reference(match.group(1)), match.group(1)


# ── 6. API — 자격증명 CRUD · 연결 테스트 · schema · 미리보기 ─────────────────
SCENARIO = '''
import json, os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
os.environ["DATABASE_QUERY_ALLOW_SQLITE"] = "1"
sys.path.insert(0, sys.argv[2])
fixture_uri = sys.argv[3]

from fastapi.testclient import TestClient
import main, models
from database import SessionLocal

db = SessionLocal()
owner = models.User(id=1, google_id="g1", email="o@e.st", name="owner")
db.add(owner); db.commit()
main.app.dependency_overrides[main.get_current_user_required] = lambda: owner
main.app.dependency_overrides[main.get_current_user] = lambda: owner
main.app.dependency_overrides[main.get_sudo_user] = lambda: owner
client = TestClient(main.app)

def check(label, cond, extra=""):
    if not cond:
        print(f"FAIL: {label} {extra}"); sys.exit(1)
    print(f"ok: {label}")

r = client.get("/api/features"); check("features", r.status_code == 200 and r.json()["database_query_v2"] is True, r.text)
r = client.post("/api/database/credentials", json={"label": "bad", "connection_string": "nope"}); check("잘못된 URI 거부", r.status_code == 400, r.text)
r = client.post("/api/database/credentials", json={"label": "테스트 DB", "connection_string": fixture_uri})
check("자격증명 생성", r.status_code == 200 and r.json()["credential"]["label"] == "테스트 DB", r.text)
cred = r.json()["credential"]; check("응답에 비밀 없음", fixture_uri not in r.text, r.text)
r = client.get("/api/database/credentials"); check("목록", r.status_code == 200 and len(r.json()["credentials"]) == 1, r.text)
r = client.get("/api/user/apikeys"); check("apikeys 에 id·label", r.json()[0]["id"] == cred["id"] and r.json()[0]["label"] == "테스트 DB", r.text)
r = client.post(f"/api/database/credentials/{cred['id']}/test"); check("연결 테스트", r.status_code == 200 and r.json()["ok"] is True, r.text)
r = client.get(f"/api/database/credentials/{cred['id']}/schema", params={"schema": "main"})
check("schema", r.status_code == 200 and [t["name"] for t in r.json()["tables"]] == ["items"], r.text)
r = client.post("/api/database/preview", json={"connection_string": cred["reference"], "query": "SELECT name FROM items WHERE price >= :minp ORDER BY id",
                                               "parameters": [{"name": "minp", "source": "input", "path": "", "type": "number"}], "parameter_values": {"minp": "2"}})
check("미리보기", r.status_code == 200 and r.json()["ok"] and [row["name"] for row in r.json()["data"]["rows"]] == ["b", "c"], r.text)
r = client.post("/api/database/preview", json={"connection_string": cred["reference"], "query": "DELETE FROM items"})
check("미리보기도 판별기를 지난다", r.status_code == 200 and r.json()["ok"] is False and r.json()["error"]["code"] == "DATABASE_QUERY_REJECTED", r.text)
r = client.get("/api/database/credentials/999/schema"); check("없는 자격증명 404", r.status_code == 404, r.text)
r = client.delete(f"/api/database/credentials/{cred['id']}"); check("삭제", r.status_code == 200, r.text)
r = client.get("/api/database/credentials"); check("삭제 후 빈 목록", r.json()["credentials"] == [], r.text)
print("ALL OK")
'''


def test_database_api_scenario(tmp_path, sqlite_db):
    pytest.importorskip("httpx", reason="fastapi.testclient 는 httpx 가 필요하다")
    scenario = tmp_path / "scenario.py"
    scenario.write_text(SCENARIO, encoding="utf-8")
    workdir = tmp_path / "run"
    workdir.mkdir()
    result = subprocess.run(
        [sys.executable, str(scenario), f"sqlite:///{tmp_path / 'app.db'}", str(BACKEND_DIR), sqlite_db],
        cwd=workdir, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "ALL OK" in result.stdout


# ── 7. PostgreSQL 통합 (TEST_POSTGRES_URL 이 있을 때만) ─────────────────────
POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", "").strip()
postgres = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL 이 없다 — CI 는 임시 PostgreSQL 을 띄우고 이 변수를 넣는다")


@pytest.fixture(scope="module")
def pg_fixture():
    if not POSTGRES_URL:
        pytest.skip("TEST_POSTGRES_URL 없음")
    # CI 의 임시 PostgreSQL 과 self-host DB 는 사설 주소(172.16/12, docker 네트워크 등)에 있다.
    # 기본 정책은 그것을 막고(SSRF 방지), self-host 운영자용 escape hatch 가 이 플래그다 —
    # 기본값이 차단이라는 것은 test_private_hosts_open_only_with_the_self_host_flag 가 지킨다.
    previous = os.environ.get("DATABASE_QUERY_ALLOW_PRIVATE_HOSTS")
    os.environ["DATABASE_QUERY_ALLOW_PRIVATE_HOSTS"] = "1"
    engine = create_engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS dbq_items"))
        conn.execute(text("CREATE TABLE dbq_items (id SERIAL PRIMARY KEY, name TEXT NOT NULL, price NUMERIC(10,2), created_at TIMESTAMPTZ DEFAULT now(), tags JSONB)"))
        conn.execute(text("INSERT INTO dbq_items (name, price, tags) VALUES ('a', 1.50, '[\"x\"]'), ('b', 2.50, '{\"k\": 1}'), ('c', 3.50, NULL)"))
    engine.dispose()
    yield POSTGRES_URL
    engine = create_engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS dbq_items"))
    engine.dispose()
    if previous is None:
        os.environ.pop("DATABASE_QUERY_ALLOW_PRIVATE_HOSTS", None)
    else:
        os.environ["DATABASE_QUERY_ALLOW_PRIVATE_HOSTS"] = previous


@postgres
def test_postgres_query_with_parameters_and_types(pg_fixture, db):
    credentials.create(db, 1, label="pg", connection_string=pg_fixture)
    result_text, step = _run(db, *_graph(
        "SELECT id, name, price, created_at, tags FROM dbq_items WHERE price >= :minp ORDER BY id",
        parameters=[{"name": "minp", "source": "value", "value": "2", "type": "number"}],
    ))
    assert step["status"] == "success", step
    rows = json.loads(result_text)
    assert [r["name"] for r in rows] == ["b", "c"] and rows[0]["price"] == 2.5
    result = run_readonly_query_result(pg_fixture, "SELECT id, name, price, created_at, tags FROM dbq_items ORDER BY id")
    assert result.data["dialect"] == "postgresql"
    types = {c["name"]: c["type"] for c in result.data["columns"]}
    assert types == {"id": "integer", "name": "string", "price": "number", "created_at": "datetime", "tags": "json"}


@postgres
def test_postgres_connection_is_tls_and_readonly_with_statement_timeout(pg_fixture):
    result = run_readonly_query_result(pg_fixture, "SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
    assert result.ok and result.data["rows"][0]["ssl"] is True
    engine = create_engine(pg_fixture)
    with engine.connect() as conn:
        _apply_readonly_session(conn, "postgresql", 1)
        assert conn.execute(text("SHOW statement_timeout")).scalar() == "1s"
        with pytest.raises(Exception) as caught:
            conn.execute(text("INSERT INTO dbq_items (name) VALUES ('smuggled')"))
        assert "read-only" in str(caught.value).lower()
    engine.dispose()


@postgres
def test_postgres_failures_are_classified_without_leaking_the_uri(pg_fixture):
    from sqlalchemy.engine import make_url

    bad_password = make_url(pg_fixture).set(password="definitely-wrong").render_as_string(hide_password=False)
    result = run_readonly_query_result(bad_password, "SELECT 1", timeout_seconds=5)
    assert result.error.code == "DATABASE_AUTH_FAILED", result.error.to_dict()
    assert "definitely-wrong" not in result.to_json() and "definitely-wrong" not in str(result)
    bad_port = make_url(pg_fixture).set(port=5433).render_as_string(hide_password=False)
    result = run_readonly_query_result(bad_port, "SELECT 1", timeout_seconds=3)
    assert result.error.code == "DATABASE_CONNECTION_FAILED"
    result = run_readonly_query_result(pg_fixture, "SELECT * FROM dbq_nope")
    assert result.error.code == "DATABASE_QUERY_FAILED" and result.error.field == "query"


@postgres
def test_postgres_diagnostics_and_schema(pg_fixture, db):
    row = credentials.create(db, 1, label="pg", connection_string=pg_fixture)
    report = diagnostics.test_connection(pg_fixture, timeout_seconds=5)
    assert report["ok"] is True, report
    assert [s["stage"] for s in report["stages"]] == ["driver", "dns", "tcp", "auth", "readonly_probe"]
    schema = diagnostics.fetch_schema(row.id, pg_fixture, schema="public")
    assert schema["ok"], schema
    table = next(t for t in schema["tables"] if t["name"] == "dbq_items")
    assert {c["name"]: c["type"] for c in table["columns"]}["price"] == "numeric"


@postgres
def test_postgres_repeated_runs_do_not_leak_connections(pg_fixture):
    engine = create_engine(pg_fixture)
    count_sql = text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()")
    with engine.connect() as conn:
        before = conn.execute(count_sql).scalar()
    for _ in range(20):
        assert run_readonly_query_result(pg_fixture, "SELECT count(*) AS c FROM dbq_items").ok
    with engine.connect() as conn:
        after = conn.execute(count_sql).scalar()
    engine.dispose()
    assert after <= before + 1
