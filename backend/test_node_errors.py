"""NodeError v1 과 공통 오류 catalog (ADR-0016, 우선 백로그 21) 계약 테스트.

검증 매트릭스(LONG_TERM_PRODUCT_ROADMAP §4.11) 의 층을 그대로 따른다 —
catalog / contract / mapping / retry / 보안 / E2E / 호환.
"""

from __future__ import annotations

import datetime
import json
import re
import smtplib

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from connectors import errors as connector_errors
from connectors.errors import ConnectorError
from connectors.retry import RetryPolicy, should_retry
from database import Base
from db_query_runtime import run_readonly_query, run_readonly_query_result
from graph import compile_workflow, run_workflow
from node_errors import (
    ContractViolation,
    NodeError,
    NodeResult,
    UnknownErrorCode,
    adapters,
    catalog,
    database as db_errors,
    delivery,
    from_exception,
    make_error,
    records,
    redaction,
    runtime,
)
from node_errors.catalog import ErrorCatalog


# ── 1. catalog ──────────────────────────────────────────────────────────
def test_catalog_loads_and_has_no_problems():
    loaded = catalog.load()
    assert loaded.version == 1
    assert loaded.problems() == []
    assert len(catalog.all_codes()) >= 37


def test_every_code_is_domain_reason_and_unique():
    codes = catalog.all_codes()
    assert len(set(codes)) == len(codes)
    for code in codes:
        assert catalog.CODE_RE.match(code), code
        entry = catalog.get(code)
        assert entry.category in catalog.categories()
        assert entry.resolution in catalog.resolutions()
        assert entry.messageKey.split(".")[0] in {"credential", "validation", "artifact", "database", "delivery", "connector", "runtime"}


def _raw_catalog():
    return json.loads(catalog.CATALOG_PATH.read_text(encoding="utf-8"))


def test_duplicate_code_is_rejected():
    raw = _raw_catalog()
    raw.pop("_comment", None)
    raw["codes"].append(dict(raw["codes"][0]))
    problems = ErrorCatalog.model_validate(raw).problems()
    assert any("번 선언" in p for p in problems)


def test_bad_code_format_and_message_key_are_rejected():
    raw = _raw_catalog()
    raw.pop("_comment", None)
    raw["codes"][0]["code"] = "credentialMissing"
    with pytest.raises(Exception):
        ErrorCatalog.model_validate(raw)
    raw = _raw_catalog()
    raw.pop("_comment", None)
    raw["codes"][0]["messageKey"] = "CredentialMissing"
    with pytest.raises(Exception):
        ErrorCatalog.model_validate(raw)


def test_deprecated_alias_needs_a_live_replacement():
    raw = _raw_catalog()
    raw.pop("_comment", None)
    raw["codes"][0]["deprecated"] = True
    problems = ErrorCatalog.model_validate(raw).problems()
    assert any("replacedBy 가 없다" in p for p in problems)
    raw["codes"][0]["replacedBy"] = "NOPE_MISSING"
    problems = ErrorCatalog.model_validate(raw).problems()
    assert any("catalog 에 없다" in p for p in problems)


def test_retryable_default_cannot_pair_with_unsafe_effect_state():
    raw = _raw_catalog()
    raw.pop("_comment", None)
    entry = next(e for e in raw["codes"] if e["code"] == "DELIVERY_TIMEOUT")
    entry["retryable"] = True
    problems = ErrorCatalog.model_validate(raw).problems()
    assert any("retryable 기본값이 true 일 수 없다" in p for p in problems)


def test_generated_markdown_has_an_anchor_per_code():
    doc = catalog.render_markdown()
    for code in catalog.all_codes():
        assert f'id="{code.lower()}"' in doc, code
        assert catalog.get(code).docs.endswith(f"#{code.lower()}")


# ── 2. contract ─────────────────────────────────────────────────────────
def test_make_error_takes_defaults_from_catalog():
    error = make_error("CREDENTIAL_MISSING", safe_details={"provider": "google_oauth"})
    payload = error.to_dict()
    assert payload["version"] == 1
    assert payload["code"] == "CREDENTIAL_MISSING"
    assert payload["category"] == "credential"
    assert payload["messageKey"] == "credential.missing"
    assert payload["retryable"] is False
    assert payload["effectState"] == "not_started"
    assert payload["safeDetails"] == {"provider": "google_oauth"}
    assert re.match(r"^[0-9a-f]{16}$", payload["requestId"])
    assert set(payload) == {"version", "code", "category", "messageKey", "userMessage", "retryable",
                            "effectState", "field", "retryAfterMs", "requestId", "safeDetails"}


def test_unknown_code_is_a_programming_error():
    with pytest.raises(UnknownErrorCode):
        make_error("DELIVERY_EXPLODED")


def test_safe_details_outside_the_allowlist_are_rejected():
    with pytest.raises(ContractViolation):
        make_error("CREDENTIAL_MISSING", safe_details={"stack": "Traceback ..."})
    with pytest.raises(ContractViolation):
        make_error("DATABASE_QUERY_FAILED", safe_details={"sql": "SELECT 1"})


def test_unknown_or_applied_effect_state_disables_retry():
    error = make_error("CONNECTOR_TIMEOUT", effect_state="unknown")
    assert error.retryable is False and error.safe_to_retry is False
    error = make_error("DELIVERY_RATE_LIMITED", retryable=True)
    assert error.retryable is True and error.safe_to_retry is True
    with pytest.raises(ContractViolation):
        make_error("CONNECTOR_TIMEOUT", effect_state="maybe")


def test_success_and_error_are_mutually_exclusive():
    error = make_error("DATABASE_QUERY_FAILED")
    with pytest.raises(ContractViolation):
        NodeResult(status="error", data={"rows": []}, error=error)
    with pytest.raises(ContractViolation):
        NodeResult(status="success", data=None, error=error)
    with pytest.raises(ContractViolation):
        NodeResult(status="error")
    assert NodeResult.success({"rows": []}).ok is True
    assert NodeResult.failure(error).ok is False


def test_json_round_trip_preserves_the_contract():
    error = make_error("DELIVERY_RATE_LIMITED", retry_after_ms=1500, field="attachments[0]",
                       safe_details={"provider": "discord", "status": 429})
    result = NodeResult.failure(error, passthrough="본문")
    restored = NodeResult.from_dict(json.loads(result.to_json()))
    assert restored.status == "error" and restored.data is None
    assert restored.error.to_dict() == error.to_dict()
    ok = NodeResult.success({"rowCount": 2}, metrics={"durationMs": 3})
    restored = NodeResult.from_dict(json.loads(ok.to_json()))
    assert restored.ok and restored.data == {"rowCount": 2} and restored.metrics == {"durationMs": 3}
    with pytest.raises(ContractViolation):
        NodeError.from_dict({"code": "X", "version": 2})


def test_needs_input_is_an_error_status_with_its_own_name():
    result = NodeResult.needs_input(make_error("VALIDATION_REQUIRED", field="url"))
    assert result.status == "needs_input" and result.ok is False and result.error.field == "url"


def test_failure_display_keeps_the_passthrough_and_legacy_note():
    error = make_error("DELIVERY_TIMEOUT")
    assert str(NodeResult.failure(error, passthrough="만든 내용")) == f"만든 내용\n\n[⚠️ {error.user_message}]"
    assert str(NodeResult.failure(error)) == f"[⚠️ {error.user_message}]"
    assert str(NodeResult.success({"a": 1})) == '{\n  "a": 1\n}'
    assert str(NodeResult.success([1], display="custom")) == "custom"


# ── 3. mapping ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("connector_code, domain, expected, effect", [
    ("auth_missing", "connector", "CREDENTIAL_MISSING", "not_applicable"),
    ("auth_missing", "delivery", "CREDENTIAL_MISSING", "not_started"),
    ("auth_invalid", "delivery", "CREDENTIAL_INVALID", "not_started"),
    ("auth_forbidden", "connector", "CREDENTIAL_FORBIDDEN", "not_applicable"),
    ("not_found", "connector", "CONNECTOR_NOT_FOUND", "not_applicable"),
    ("not_found", "delivery", "DELIVERY_INVALID_RECIPIENT", "not_started"),
    ("invalid_request", "delivery", "DELIVERY_PROVIDER_REJECTED", "not_started"),
    ("rate_limited", "connector", "CONNECTOR_RATE_LIMITED", "not_applicable"),
    ("rate_limited", "delivery", "DELIVERY_RATE_LIMITED", "not_started"),
    ("quota_exceeded", "delivery", "CONNECTOR_QUOTA_EXCEEDED", "not_started"),
    ("timeout", "connector", "CONNECTOR_TIMEOUT", "not_applicable"),
    ("timeout", "delivery", "DELIVERY_TIMEOUT", "unknown"),
    ("network", "connector", "CONNECTOR_NETWORK_ERROR", "not_applicable"),
    ("network", "delivery", "DELIVERY_RESULT_UNKNOWN", "unknown"),
    ("server_error", "connector", "CONNECTOR_PROVIDER_ERROR", "not_applicable"),
    ("server_error", "delivery", "DELIVERY_RESULT_UNKNOWN", "unknown"),
    ("unknown", "connector", "INTERNAL_UNKNOWN", "not_applicable"),
])
def test_connector_codes_map_to_canonical_codes(connector_code, domain, expected, effect):
    error = ConnectorError(code=connector_code, service="Gmail", detail="raw upstream body")
    node_error = adapters.from_connector_error(error, domain=domain)
    assert node_error.code == expected
    assert node_error.effect_state == effect
    assert "Gmail" in node_error.user_message
    assert "raw upstream body" not in json.dumps(node_error.to_dict(), ensure_ascii=False)


def test_http_status_flows_through_connector_error_to_node_error():
    assert connector_errors.from_response(401, service="YouTube").to_node_error().code == "CREDENTIAL_INVALID"
    assert connector_errors.from_response(404, service="YouTube").to_node_error().code == "CONNECTOR_NOT_FOUND"
    limited = connector_errors.from_response(429, service="YouTube", headers={"Retry-After": "3"}).to_node_error(domain="delivery")
    assert limited.code == "DELIVERY_RATE_LIMITED" and limited.retry_after_ms == 3000 and limited.safe_to_retry
    assert connector_errors.from_response(503, service="YouTube").to_node_error().code == "CONNECTOR_PROVIDER_ERROR"


def test_unexpected_exception_becomes_internal_unknown_with_a_record():
    records.clear()
    error = from_exception(RuntimeError("boom password=hunter2"), node_type="posterGeneratorNode", node_id="p1")
    assert error.code == "INTERNAL_UNKNOWN" and error.effect_state == "unknown" and error.retryable is False
    record = records.find(error.request_id)
    assert record is not None and record.exception_type == "RuntimeError" and record.node_id == "p1"
    assert "hunter2" not in record.message and "[REDACTED]" in record.message
    assert "hunter2" not in json.dumps(error.to_dict())


def test_from_exception_unwraps_connector_errors():
    error = from_exception(ConnectorError(code="rate_limited", service="Drive", retry_after=1.0))
    assert error.code == "CONNECTOR_RATE_LIMITED" and error.retry_after_ms == 1000


class _OperationalError(Exception):
    pass


@pytest.mark.parametrize("exc, expected, field", [
    (ImportError("No module named 'pymysql'"), "DATABASE_DRIVER_MISSING", None),
    (_OperationalError("FATAL:  password authentication failed for user \"app\""), "DATABASE_AUTH_FAILED", None),
    (_OperationalError("could not connect to server: Connection refused"), "DATABASE_CONNECTION_FAILED", None),
    (_OperationalError("canceling statement due to statement timeout"), "DATABASE_TIMEOUT", "query"),
    (_OperationalError("no such table: items"), "DATABASE_QUERY_FAILED", "query"),
    (ValueError("statement 는 하나만 실행할 수 있습니다."), "DATABASE_QUERY_REJECTED", "query"),
    (KeyError("weird"), "INTERNAL_UNKNOWN", None),
])
def test_database_exceptions_are_classified(exc, expected, field):
    error = db_errors.classify_database_exception(exc, connection_string="postgresql://u:pw@h/db")
    assert error.code == expected and error.field == field
    assert error.effect_state == ("unknown" if expected == "INTERNAL_UNKNOWN" else "not_applicable")
    assert "pw" not in json.dumps(error.to_dict())


def test_malformed_connection_string_is_a_credential_problem():
    class ArgumentError(Exception):
        pass
    error = db_errors.classify_database_exception(ArgumentError("Could not parse SQLAlchemy URL from string"), connection_string="nonsense")
    assert error.code == "CREDENTIAL_INVALID" and error.safe_details == {"provider": "database", "service": "Database"}


@pytest.mark.parametrize("status, expected, effect, extra", [
    (401, "DELIVERY_AUTH_FAILED", "not_started", {}),
    (403, "DELIVERY_FORBIDDEN", "not_started", {}),
    (404, "DELIVERY_INVALID_RECIPIENT", "not_started", {}),
    (429, "DELIVERY_RATE_LIMITED", "not_started", {"retry_after": 2000}),
    (400, "DELIVERY_PROVIDER_REJECTED", "not_started", {"reason": "invalid_payload"}),
    (413, "DELIVERY_PROVIDER_REJECTED", "not_started", {"reason": "payload_too_large"}),
    (500, "DELIVERY_RESULT_UNKNOWN", "unknown", {}),
    (502, "DELIVERY_RESULT_UNKNOWN", "unknown", {}),
])
def test_delivery_status_codes_decide_code_and_effect_state(status, expected, effect, extra):
    error = delivery.error_from_status(status, provider="discord", headers={"Retry-After": "2"}, body="{\"message\": \"raw\"}")
    assert error.code == expected and error.effect_state == effect
    assert error.safe_to_retry is (expected == "DELIVERY_RATE_LIMITED")
    if "retry_after" in extra:
        assert error.retry_after_ms == extra["retry_after"]
    if "reason" in extra:
        assert error.safe_details["reason"] == extra["reason"]
    assert "raw" not in json.dumps(error.to_dict())


def test_delivery_exceptions_are_classified_conservatively():
    import socket
    assert delivery.error_from_exception(smtplib.SMTPAuthenticationError(535, b"bad creds"), provider="smtp").code == "DELIVERY_AUTH_FAILED"
    recipient = delivery.error_from_exception(smtplib.SMTPRecipientsRefused({"a@b.c": (550, b"no")}), provider="smtp")
    assert recipient.code == "DELIVERY_INVALID_RECIPIENT" and recipient.field == "toEmail"
    assert "a@b.c" not in json.dumps(recipient.to_dict())
    timeout = delivery.error_from_exception(socket.timeout("timed out"), provider="discord", timeout_seconds=10)
    assert timeout.code == "DELIVERY_TIMEOUT" and timeout.effect_state == "unknown" and not timeout.retryable
    refused = delivery.error_from_exception(ConnectionRefusedError("refused"), provider="smtp")
    assert refused.code == "CONNECTOR_NETWORK_ERROR" and refused.effect_state == "not_started"
    disconnected = delivery.error_from_exception(smtplib.SMTPServerDisconnected("gone"), provider="smtp")
    assert disconnected.code == "DELIVERY_RESULT_UNKNOWN" and disconnected.effect_state == "unknown"
    missing = delivery.error_from_exception(ValueError("SMTP credentials missing in API Center or .env"), provider="smtp", credential_provider="google_smtp")
    assert missing.code == "CREDENTIAL_MISSING" and missing.safe_details["provider"] == "google_smtp"
    assert delivery.error_from_exception(ValueError("Channel ID is required for Bot Token mode"), provider="discord").field == "channelId"


# ── 4. retry ────────────────────────────────────────────────────────────
POLICY = RetryPolicy(max_attempts=3, max_delay=20.0)


def test_reads_still_retry_on_transient_failures_and_never_on_auth():
    for code in ("rate_limited", "timeout", "network", "server_error"):
        assert should_retry(ConnectorError(code=code, service="S"), attempt=1, policy=POLICY, method="GET"), code
    for code in ("auth_missing", "auth_invalid", "auth_forbidden", "not_found", "invalid_request", "quota_exceeded", "unknown"):
        assert not should_retry(ConnectorError(code=code, service="S"), attempt=1, policy=POLICY, method="GET"), code


def test_writes_retry_only_when_the_provider_certainly_rejected():
    assert should_retry(ConnectorError(code="rate_limited", service="S"), attempt=1, policy=POLICY, method="POST")
    for code in ("timeout", "network", "server_error"):
        assert not should_retry(ConnectorError(code=code, service="S"), attempt=1, policy=POLICY, method="POST"), code
    # 멱등 키를 갖춘 POST 는 connector 맥락으로 열린다(ADR-0007 통로 유지)
    assert should_retry(ConnectorError(code="timeout", service="S"), attempt=1, policy=POLICY, method="POST", idempotent=True)


def test_retry_after_and_attempt_caps_use_node_error_fields():
    assert not should_retry(ConnectorError(code="rate_limited", service="S", retry_after=120.0), attempt=1, policy=POLICY)
    assert not should_retry(ConnectorError(code="rate_limited", service="S"), attempt=3, policy=POLICY)
    node_error = make_error("DELIVERY_RATE_LIMITED", retry_after_ms=5000)
    assert should_retry(node_error, attempt=1, policy=POLICY, method="POST")
    assert POLICY.delay_for(1, node_error) == 5.0
    assert not should_retry(make_error("DELIVERY_TIMEOUT"), attempt=1, policy=POLICY, method="POST")


def test_retry_decisions_do_not_spam_internal_records():
    records.clear()
    should_retry(ConnectorError(code="timeout", service="S"), attempt=1, policy=POLICY, method="GET")
    assert records.recent() == []


# ── 5. 보안 ─────────────────────────────────────────────────────────────
def test_redactor_masks_secrets_and_identifiers():
    raw = (
        'Traceback (most recent call last):\n  File "/home/ubuntu/app/backend/graph.py", line 12\n'
        "postgresql://dbuser:supersecretpw@db.internal:5432/app "
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload "
        "api_key=sk-live-1234567890 mail alice@example.com "
        "SELECT * FROM users WHERE email='alice@example.com' AND token='t0k3n' "
        "uploads/2026/poster.png C:\\Users\\me\\secret.txt"
    )
    masked = redaction.redact_text(raw, max_length=2000)
    for secret in ("supersecretpw", "dbuser", "eyJhbGci", "sk-live", "alice@example.com", "t0k3n", "/home/ubuntu", "poster.png", "secret.txt"):
        assert secret not in masked, secret
    assert "[REDACTED]" in masked and "[EMAIL]" in masked and "[PATH]" in masked and "'?'" in masked
    assert len(redaction.redact_text("x" * 5000)) <= redaction.MAX_MESSAGE_LENGTH


def test_public_payload_never_carries_provider_detail_or_stack():
    error = ConnectorError(code="server_error", service="Notion", status=500,
                           detail='{"message": "database_id abc-123 not shared with integration"}')
    public = json.dumps(error.to_dict(), ensure_ascii=False)
    assert "detail" not in error.to_dict() and "abc-123" not in public
    node_error = error.to_node_error()
    assert "abc-123" not in json.dumps(node_error.to_dict(), ensure_ascii=False)
    record = records.find(node_error.request_id)
    assert record is not None and record.provider_status == 500 and record.provider_code == "server_error"


def test_telemetry_columns_only_carry_code_category_state():
    step = {"node_type": "discordNode", "status": "error", "result_data": "본문 me@x.com",
            "error": make_error("DELIVERY_TIMEOUT", safe_details={"provider": "discord"}).to_dict()}
    columns = runtime.step_columns(step)
    assert set(columns) == {"error_code", "error_category", "effect_state", "error_legacy", "error_request_id"}
    assert columns["error_code"] == "DELIVERY_TIMEOUT" and columns["effect_state"] == "unknown" and columns["error_legacy"] is False
    assert runtime.step_columns({"status": "success"})["error_code"] is None


# ── 6. E2E — 실행 로그가 문자열 검색 없이 code/effectState 로 판별된다 ───
@pytest.fixture
def sqlite_db(tmp_path):
    path = tmp_path / "data.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text("INSERT INTO items (name) VALUES ('a'), ('b')"))
    engine.dispose()
    return f"sqlite:///{path}"


CREDENTIAL_REF = "{{API_CENTER:database}}"


@pytest.fixture
def db_project(sqlite_db):
    """API 센터에 Database 자격증명을 등록한 프로젝트. 평문 URI 는 실행 관문(P0)이 막으므로 E2E 는
    실제 제품 경로대로 reference 로 실행한다."""
    from credential_crypto import encrypt_secret

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        models.User(id=1, name="Owner", email="owner@example.com"),
        models.Project(id=10, user_id=1, title="db", graph_data={}),
        models.UserApiKey(user_id=1, provider="database", api_key=encrypt_secret(sqlite_db)),
    ])
    session.commit()
    yield session
    session.close()


def _db_graph(connection_string, query):
    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "d1", "type": "databaseNode", "data": {"connectionString": connection_string, "query": query}},
        {"id": "o1", "type": "outputNode", "data": {}},
    ]
    edges = [{"source": "s1", "target": "d1"}, {"source": "d1", "target": "o1"}]
    return nodes, edges


def _run_db(db_project, query):
    return run_workflow(*_db_graph(CREDENTIAL_REF, query), db=db_project, project_id=10, default_input="")


def _step(logs, node_id):
    return next(step for step in logs if step["node_id"] == node_id)


def test_database_success_is_structured_and_display_stays_json(sqlite_db, db_project):
    result = run_readonly_query_result(sqlite_db, "SELECT id, name FROM items ORDER BY id")
    assert result.ok and result.data["rowCount"] == 2 and result.data["dialect"] == "sqlite"
    # 컬럼 타입은 정규화 전 값에서 추론한다(ADR-0017) — 자세한 타입 검증은 test_database_query_v2.
    assert result.data["columns"] == [{"name": "id", "type": "integer"}, {"name": "name", "type": "string"}]
    assert result.data["truncated"] is False and result.data["durationMs"] >= 0
    assert json.loads(str(result)) == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    assert json.loads(run_readonly_query(sqlite_db, "SELECT COUNT(*) AS c FROM items")) == [{"c": 2}]   # 호환 래퍼

    text_result, _, logs = _run_db(db_project, "SELECT name FROM items ORDER BY id")
    step = _step(logs, "d1")
    assert step["status"] == "success" and step["result_status"] == "success" and step["error"] is None
    assert json.loads(step["result_data"]) == [{"name": "a"}, {"name": "b"}]
    assert runtime.flow_outcome(text_result, logs) == "success"


def test_database_failures_carry_codes_not_strings(db_project):
    _, _, logs = _run_db(db_project, "SELECT * FROM nope")
    step = _step(logs, "d1")
    assert step["status"] == "error" and step["error"]["code"] == "DATABASE_QUERY_FAILED"
    assert step["error"]["field"] == "query" and step["error"]["effectState"] == "not_applicable"
    assert step["result_data"].startswith("Database Error:")      # 이행기 표시 문자열은 유지

    _, _, logs = _run_db(db_project, "DELETE FROM items")
    assert _step(logs, "d1")["error"]["code"] == "DATABASE_QUERY_REJECTED"


def test_unreachable_postgres_is_a_connection_failure_without_leaking_the_uri():
    result = run_readonly_query_result("postgresql://dbuser:supersecretpw@127.0.0.1:9/nope", "SELECT 1")
    assert result.status == "error"
    assert result.error.code in {"DATABASE_CONNECTION_FAILED", "DATABASE_DRIVER_MISSING"}
    assert result.error.safe_to_retry is (result.error.code == "DATABASE_CONNECTION_FAILED")
    serialized = result.to_json() + str(result)
    assert "supersecretpw" not in serialized and "dbuser" not in serialized
    record = records.find(result.error.request_id)
    assert record is not None and "supersecretpw" not in record.message and "dbuser" not in record.message


def test_missing_database_credential_is_credential_missing_before_any_connection():
    _, _, logs = run_workflow(*_db_graph("{{API_CENTER:database}}", "SELECT 1"), default_input="")
    step = _step(logs, "d1")
    assert step["error"]["code"] == "CREDENTIAL_MISSING" and step["error"]["field"] == "connectionString"
    assert step["error"]["safeDetails"] == {"provider": "database", "service": "Database"}
    assert step["error"]["effectState"] == "not_started"


class _FakeResponse:
    def __init__(self, status_code, headers=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text


def _discord_graph(token="https://discord.com/api/webhooks/1/abc"):
    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "v1", "type": "valueNode", "data": {"value": "공지 본문"}},
        {"id": "dc", "type": "discordNode", "data": {"botToken": token, "channelId": ""}},
    ]
    edges = [{"source": "s1", "target": "v1"}, {"source": "v1", "target": "dc"}]
    return nodes, edges


def test_discord_rate_limit_is_retryable_but_timeout_is_not(monkeypatch):
    import requests

    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(429, {"Retry-After": "2"}, '{"retry_after": 2.0}'))
    result_text, _, logs = run_workflow(*_discord_graph(), default_input="")
    step = _step(logs, "dc")
    error = step["error"]
    assert error["code"] == "DELIVERY_RATE_LIMITED" and error["effectState"] == "not_started"
    assert error["retryable"] is True and error["retryAfterMs"] == 2000
    assert result_text.startswith("공지 본문") and "[⚠️ Discord 발송 실패:" in result_text   # 만든 내용은 보존
    assert runtime.flow_outcome(result_text, logs) == "error"

    def _timeout(*a, **k):
        raise requests.exceptions.Timeout("read timed out")
    monkeypatch.setattr(requests, "post", _timeout)
    _, _, logs = run_workflow(*_discord_graph(), default_input="")
    error = _step(logs, "dc")["error"]
    assert error["code"] == "DELIVERY_TIMEOUT" and error["effectState"] == "unknown" and error["retryable"] is False

    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(502, {}, "bad gateway"))
    _, _, logs = run_workflow(*_discord_graph(), default_input="")
    error = _step(logs, "dc")["error"]
    assert error["code"] == "DELIVERY_RESULT_UNKNOWN" and error["retryable"] is False


def test_discord_without_a_token_is_credential_missing():
    result_text, _, logs = run_workflow(*_discord_graph(token=""), default_input="")
    error = _step(logs, "dc")["error"]
    assert error["code"] == "CREDENTIAL_MISSING" and error["effectState"] == "not_started"
    assert "Discord 봇 토큰/웹훅이 설정되지 않아" in result_text                 # discord_bot 호환 문구 유지
    assert runtime.has_node_error(logs, "discordNode")


def _email_graph():
    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "v1", "type": "valueNode", "data": {"value": "메일 본문"}},
        {"id": "em", "type": "emailNode", "data": {"toEmail": "to@example.com", "subject": "제목", "smtp_credentials": ""}},
    ]
    edges = [{"source": "s1", "target": "v1"}, {"source": "v1", "target": "em"}]
    return nodes, edges


def test_smtp_failures_are_classified_and_addresses_stay_private(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def starttls(self):
            pass

        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted for sender@example.com")

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    result_text, _, logs = run_workflow(*_email_graph(), default_input="")
    error = _step(logs, "em")["error"]
    assert error["code"] == "DELIVERY_AUTH_FAILED" and error["effectState"] == "not_started"
    assert "sender@example.com" not in json.dumps(error) and "sender@example.com" not in result_text
    assert result_text.startswith("메일 본문") and "[⚠️ 이메일 발송 실패:" in result_text

    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    _, _, logs = run_workflow(*_email_graph(), default_input="")
    assert _step(logs, "em")["error"]["code"] == "CREDENTIAL_MISSING"


def _mock_run(graph, scenario):
    import mock_service
    return mock_service.run(graph, db=None, project_id=1, entry_node_id="w1", payload={"event": "x"}, scenario=scenario)


def _connector_graph(node):
    return {"nodes": [{"id": "w1", "type": "webhookNode", "data": {}}, node, {"id": "o1", "type": "outputNode", "data": {}}],
            "edges": [{"source": "w1", "target": node["id"]}, {"source": node["id"], "target": "o1"}]}


@pytest.mark.parametrize("node, scenario, expected, effect", [
    ({"id": "h1", "type": "httpRequestNode", "data": {"method": "GET", "url": "https://api.example.com/x"}}, "auth_failed", "CREDENTIAL_INVALID", "not_applicable"),
    ({"id": "h1", "type": "httpRequestNode", "data": {"method": "GET", "url": "https://api.example.com/x"}}, "server_error", "CONNECTOR_PROVIDER_ERROR", "not_applicable"),
    ({"id": "y1", "type": "youtubeTriggerNode", "data": {"channelId": "UC1"}}, "not_found", "CONNECTOR_NOT_FOUND", "not_applicable"),
    ({"id": "y1", "type": "youtubeTriggerNode", "data": {"channelId": "UC1"}}, "rate_limited", "CONNECTOR_RATE_LIMITED", "not_applicable"),
    ({"id": "y2", "type": "youtubeNode", "data": {"mode": "create_comment", "videoId": "v", "commentText": "c"}}, "rate_limited", "DELIVERY_RATE_LIMITED", "not_started"),
    ({"id": "y2", "type": "youtubeNode", "data": {"mode": "create_comment", "videoId": "v", "commentText": "c"}}, "timeout", "DELIVERY_TIMEOUT", "unknown"),
    ({"id": "g1", "type": "gmailNode", "data": {"mode": "send_email", "to": "a@b.c", "subject": "s", "body": "b"}}, "auth_failed", "CREDENTIAL_INVALID", "not_started"),
    ({"id": "g1", "type": "gmailNode", "data": {"mode": "send_email", "to": "a@b.c", "subject": "s", "body": "b"}}, "timeout", "DELIVERY_TIMEOUT", "unknown"),
])
def test_connector_mock_failures_snapshot_to_canonical_codes(node, scenario, expected, effect):
    result = _mock_run(_connector_graph(node), scenario)
    step = _step(result["logs"], node["id"])
    assert step["status"] == "error", step
    assert step["error"]["code"] == expected and step["error"]["effectState"] == effect
    assert result["success"] is False


def test_uncaught_node_exception_becomes_a_workflow_level_error_step(monkeypatch, db_project):
    import db_query_runtime

    def _boom(*a, **k):
        raise RuntimeError("driver exploded token=abc123")
    monkeypatch.setattr(db_query_runtime, "run_readonly_query_result", _boom)
    result_text, _, logs = _run_db(db_project, "SELECT 1")
    assert result_text.startswith("► Flow 1 Error:")                     # 표시 문자열 유지
    workflow_step = next(step for step in logs if step["node_type"] == "workflow")
    assert workflow_step["error"]["code"] == "INTERNAL_UNKNOWN"
    assert runtime.runtime_failure_message(logs) == workflow_step["error_message"]
    assert runtime.summarize_logs(logs)["runtime_failed"] is True
    assert runtime.flow_outcome("아무 문구", logs) == "error"
    assert "abc123" not in json.dumps(logs)


def test_flow_outcome_reads_structure_first_and_only_then_legacy_markers():
    assert runtime.flow_outcome("정상 결과에 Error 라는 단어가 들어 있다", []) == "success"    # 예전 오탐 제거
    assert runtime.flow_outcome_with_source("❌ 워크플로우 실행 중 오류", []) == ("error", "legacy_fallback")
    assert runtime.flow_outcome_with_source("► Flow 1 Error: boom", []) == ("error", "legacy_fallback")
    error_step = runtime.error_step(make_error("RUNTIME_CANCELLED"))
    assert runtime.flow_outcome_with_source("아무 결과", [error_step]) == ("error", "structured")
    fields = runtime.response_fields("결과", [error_step])
    assert fields["error_schema"] == 1 and fields["outcome"] == "error" and fields["errors"][0]["error"]["code"] == "RUNTIME_CANCELLED"
    assert isinstance(fields["node_error_v1"], bool)


def test_feature_flag_only_controls_display(monkeypatch):
    monkeypatch.setenv("NODE_ERROR_V1", "0")
    assert runtime.is_enabled() is False
    error_step = runtime.error_step(make_error("RUNTIME_CANCELLED"))
    assert runtime.flow_outcome("결과", [error_step]) == "error"       # 내부 분기는 플래그와 무관
    monkeypatch.setenv("NODE_ERROR_V1", "1")
    assert runtime.is_enabled() is True


# ── 7. 호환 — legacy 노드와 새 노드가 한 workflow 에 있어도 깨지지 않는다 ─
def test_legacy_and_structured_nodes_coexist(db_project):
    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "d1", "type": "databaseNode", "data": {"connectionString": CREDENTIAL_REF, "query": "SELECT name FROM items ORDER BY id"}},
        {"id": "k1", "type": "kakaoNode", "data": {"accessToken": "", "receiver": ""}},
        {"id": "o1", "type": "outputNode", "data": {}},
    ]
    edges = [{"source": "s1", "target": "d1"}, {"source": "d1", "target": "k1"}, {"source": "k1", "target": "o1"}]
    result_text, _, logs = run_workflow(nodes, edges, db=db_project, project_id=10, default_input="")
    db_step, kakao_step = _step(logs, "d1"), _step(logs, "k1")
    assert db_step["status"] == "success" and db_step["error"] is None
    assert kakao_step["status"] == "error" and kakao_step["error"]["code"] == "LEGACY_NODE_ERROR"
    assert kakao_step["error"]["safeDetails"] == {"legacyPattern": "warning_note"}
    assert "카카오 액세스 토큰" in kakao_step["error"]["userMessage"]
    assert "[⚠️ 카카오 액세스 토큰" in result_text                          # 하류/evaluator 가 보는 문자열은 그대로
    summary = runtime.summarize_logs(logs)
    assert summary["error_count"] == 1 and summary["legacy_count"] == 1 and summary["runtime_failed"] is False


def test_success_results_are_not_flagged_as_legacy_errors():
    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "v1", "type": "valueNode", "data": {"value": "이 문장에는 Error 라는 단어와 실패라는 단어가 있다"}},
        {"id": "o1", "type": "outputNode", "data": {}},
    ]
    edges = [{"source": "s1", "target": "v1"}, {"source": "v1", "target": "o1"}]
    result_text, _, logs = run_workflow(nodes, edges, default_input="")
    assert all(step["status"] == "success" and step["error"] is None for step in logs)
    assert runtime.flow_outcome(result_text, logs) == "success"


MIGRATED_NODE_TYPES = {
    "databaseNode": {"connectionString": "sqlite:///x.db", "query": "SELECT 1"},
    "httpRequestNode": {"method": "GET", "url": "https://api.example.com/x"},
    "discordNode": {"botToken": "https://discord.com/api/webhooks/1/a", "channelId": ""},
    "emailNode": {"toEmail": "a@b.c", "subject": "s", "smtp_credentials": ""},
    "youtubeTriggerNode": {"channelId": "UC1"},
    "youtubeNode": {"mode": "create_comment", "videoId": "v", "commentText": "c"},
    "rssTriggerNode": {"feedUrl": "https://example.com/feed.xml"},
    "gmailTriggerNode": {"query": "is:unread"},
    "gmailNode": {"mode": "send_email", "to": "a@b.c", "subject": "s", "body": "b"},
    "googleDriveNode": {"mode": "search_files", "query": "q"},
}


@pytest.mark.parametrize("node_type, data", sorted(MIGRATED_NODE_TYPES.items()))
def test_migrated_generators_log_structured_errors(node_type, data):
    """이전된 생성기는 log_step 에 NodeResult 또는 NodeError 를 실어야 한다 — 오류 문자열만 결과에 붙이는
    새 executor 는 여기서 걸린다(ADR-0016 ERROR-3.4)."""
    nodes = [{"id": "s1", "type": "startNode", "data": {}}, {"id": "n1", "type": node_type, "data": data}]
    edges = [{"source": "s1", "target": "n1"}]
    if node_type.endswith("TriggerNode"):
        nodes, edges = [{"id": "n1", "type": node_type, "data": data}, {"id": "o1", "type": "outputNode", "data": {}}], [{"source": "n1", "target": "o1"}]
    source = compile_workflow(nodes, edges)
    assert not source.startswith("Error"), source
    calls = re.findall(r"log_step\('n1', '%s', [^\n]*\)" % node_type, source)
    assert calls, source
    # `result=_..._res_` 는 NodeResult 를 그대로 싣는 형태다(databaseNode·발송 노드).
    # `error=_...` 는 NodeError 를 따로 넘기는 형태다(connector 노드).
    assert all(("error=_" in call) or re.search(r"result=_\w+_res_", call) for call in calls), calls


# ── 8. 번들·문서 드리프트와 telemetry ─────────────────────────────────────
def test_frontend_error_catalog_bundle_and_doc_are_up_to_date():
    from export_node_definitions import (
        ERROR_CATALOG_BUNDLE_PATH, ERROR_CATALOG_DOC_PATH, render_error_catalog_bundle, render_error_catalog_doc,
    )
    assert ERROR_CATALOG_BUNDLE_PATH.exists(), "python backend/export_node_definitions.py 를 실행하라"
    assert ERROR_CATALOG_BUNDLE_PATH.read_text(encoding="utf-8") == render_error_catalog_bundle(), \
        "프론트엔드 오류 catalog 번들이 정본과 다르다 — python backend/export_node_definitions.py 를 실행하라"
    assert ERROR_CATALOG_DOC_PATH.read_text(encoding="utf-8") == render_error_catalog_doc(), \
        "Documents/ERROR_CATALOG.md 가 정본과 다르다 — python backend/export_node_definitions.py 를 실행하라"
    bundle = json.loads(ERROR_CATALOG_BUNDLE_PATH.read_text(encoding="utf-8"))
    assert bundle["codes"]["CREDENTIAL_MISSING"]["resolution"] == "open_api_center"
    assert bundle["resolutions"]["open_api_center"]["target"] == "/settings/api-center"


def test_telemetry_summary_counts_codes_and_legacy_ratio():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    now = datetime.datetime.utcnow()
    rows = [
        ("discordNode", "DELIVERY_TIMEOUT", "delivery", "unknown", False),
        ("discordNode", "DELIVERY_TIMEOUT", "delivery", "unknown", False),
        ("kakaoNode", "LEGACY_NODE_ERROR", "runtime", "unknown", True),
        ("posterGeneratorNode", "INTERNAL_UNKNOWN", "runtime", "unknown", False),
    ]
    for node_type, code, category, state, legacy in rows:
        db.add(models.NodeExecutionLog(node_id="n", node_type=node_type, start_time=now, end_time=now, status="error",
                                       error_code=code, error_category=category, effect_state=state, error_legacy=legacy))
    db.add(models.NodeExecutionLog(node_id="ok", node_type="valueNode", start_time=now, end_time=now, status="success"))
    db.commit()

    from node_errors import telemetry
    summary = telemetry.summary(db, days=1)
    assert summary["total_steps"] == 5 and summary["error_steps"] == 4 and summary["structured_error_steps"] == 4
    assert summary["legacy_error_steps"] == 1 and summary["legacy_ratio"] == 0.25
    assert summary["by_code"][0] == {"code": "DELIVERY_TIMEOUT", "category": "delivery", "count": 2}
    assert summary["internal_unknown_by_node_type"] == [{"node_type": "posterGeneratorNode", "count": 1}]
    assert not any(key in json.dumps(summary) for key in ("result_data", "error_message"))


def test_migration_0008_adds_the_telemetry_columns(tmp_path):
    from sqlalchemy import inspect
    import db_migrate

    url = f"sqlite:///{tmp_path / 'm.db'}"
    engine = create_engine(url)
    db_migrate.ensure_schema(engine, url)
    columns = {c["name"] for c in inspect(engine).get_columns("node_execution_logs")}
    assert {"error_code", "error_category", "effect_state", "error_legacy", "error_request_id"} <= columns
    engine.dispose()
