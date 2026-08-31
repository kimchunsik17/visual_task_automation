"""새 연동 노드가 지켜야 하는 계약 (한국형 노드 계획 Phase 0).

Phase 0 은 노드를 만드는 단계가 아니라 **노드를 만들 때 무엇을 함께 내야 하는지 정하는**
단계다. 한국형 노드만 15종 가까이 추가될 예정이라, 그때마다 "이번엔 mock 을 빠뜨렸네",
"이건 정화 규칙이 없네" 를 사람이 알아채는 방식으로는 버티지 못한다.

여기서 고정하는 것 셋:

  1. **mock 계약** — 성공만 흉내 내는 mock 은 목업 탭에서 초록불을 켜면서 실제로 사용자를
     막는 경로를 하나도 알려주지 않는다.
  2. **출처 기록** — 외부 API 는 조용히 바뀐다. "무엇을 근거로 만들었나"가 없으면 낡은
     구현을 알아챌 방법이 없다.
  3. **정화 규칙 자동 파생** — 새 노드가 규칙 없이 커뮤니티에 공개되는 경로를 막는다.
"""

from __future__ import annotations

import datetime

import pytest

import community_sanitize as sanitize
import node_definition
from connectors import mock as mock_fixtures
from connectors.contract import ConnectorSpec, TermsGate
from connectors.errors import ConnectorError

CONNECTOR_TYPES = [t for t in node_definition.defined_types()
                   if node_definition.get_definition(t).connector is not None]


def _spec(**overrides) -> ConnectorSpec:
    base = dict(service="Test", role="action", modes=["read"],
                sideEffectByMode={"read": "external-read"})
    base.update(overrides)
    return ConnectorSpec(**base)


# ── 1. mock 계약 ────────────────────────────────────────────────────────

def test_연동_정의가_하나도_빠짐없이_등록되어_검사된다():
    assert CONNECTOR_TYPES, "연동 정의를 하나도 찾지 못했다 — 이 파일의 검사가 전부 헛돈다"


@pytest.mark.parametrize("node_type", CONNECTOR_TYPES)
def test_모든_연동_정의가_mock_계약을_지킨다(node_type):
    definition = node_definition.get_definition(node_type)
    problems = mock_fixtures.validate_mock(definition.mock, definition.connector, label=node_type)
    assert problems == []


def test_자격증명이_없는_연동에는_인증실패_시나리오를_요구하지_않는다():
    """RSS 처럼 비로그인으로 읽는 연동에 '인증 실패' 를 요구하면 재현 못 할 상황을 지어내게 된다."""
    assert mock_fixtures.required_scenarios(_spec()) == ["success", "timeout"]


def test_자격증명이_있으면_인증실패와_호출한도를_요구한다():
    spec = _spec(credentials=[{"provider": "google_oauth", "scopes": []}])
    assert set(mock_fixtures.required_scenarios(spec)) == {
        "success", "timeout", "auth_failed", "rate_limited"}


def test_시나리오_이름만_맞고_상황을_재현하지_않으면_잡아낸다():
    """'auth_failed' 인데 200 을 돌려주는 mock 은 없느니만 못하다."""
    bad = {"scenarios": {
        "success": {"responses": [{"status": 200, "body": {}}]},
        "timeout": {"responses": [{"raise": "timeout"}]},
        "auth_failed": {"responses": [{"status": 200, "body": {}}]},
        "rate_limited": {"responses": [{"status": 429}]},
    }}
    spec = _spec(credentials=[{"provider": "google_oauth", "scopes": []}])
    problems = mock_fixtures.validate_mock(bad, spec, label="x")
    assert any("auth_failed" in p and "재현하지 않는다" in p for p in problems)


def test_timeout_시나리오는_실제로_지연을_일으켜야_한다():
    bad = {"scenarios": {"success": {"responses": [{"status": 200}]},
                         "timeout": {"responses": [{"status": 504}]}}}
    problems = mock_fixtures.validate_mock(bad, _spec(), label="x")
    assert any("raise: timeout" in p for p in problems)


def test_빠진_시나리오를_이름으로_알려준다():
    problems = mock_fixtures.validate_mock({"scenarios": {}}, _spec(), label="x")
    assert any("'success'" in p for p in problems)
    assert any("'timeout'" in p for p in problems)


def test_정의를_로드할_때_mock_계약이_실제로_강제된다(tmp_path, monkeypatch):
    """검사가 코드에만 있고 로드 경로에 안 붙어 있으면 아무도 안 지킨다."""
    import json

    source = node_definition.DEFINITIONS_DIR / "youtubeNode.json"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["mock"]["scenarios"].pop("auth_failed")

    target = tmp_path / "youtubeNode.json"
    target.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(node_definition, "DEFINITIONS_DIR", tmp_path)
    with pytest.raises(ValueError, match="auth_failed"):
        node_definition._load()


# ── 2. 출처 기록: docsUrl / verifiedAt / termsGate ──────────────────────

@pytest.mark.parametrize("node_type", CONNECTOR_TYPES)
def test_모든_연동이_무엇을_근거로_만들었는지_적는다(node_type):
    connector = node_definition.get_definition(node_type).connector
    assert connector.docsUrl, f"{node_type}: docsUrl 이 없다 — 낡은 구현을 알아챌 방법이 없어진다"


def test_확인일만_있고_무엇을_확인했는지가_없으면_거부한다():
    problems = _spec(verifiedAt="2026-08-30").validate_against_registry()
    assert any("docsUrl" in p for p in problems)


@pytest.mark.parametrize("value", ["2026/08/30", "20260830", "어제", "2026-13-01"])
def test_날짜_형식이_어긋나면_로딩에서_막는다(value):
    """형식이 틀리면 만료 비교가 조용히 실패한다 — 만료된 근거를 유효하다고 읽는 쪽으로 틀린다."""
    problems = _spec(docsUrl="https://x", verifiedAt=value).validate_against_registry()
    assert any("YYYY-MM-DD" in p for p in problems)


def test_서면_제휴는_근거를_남겨야_한다():
    spec = _spec(termsGate=TermsGate(basis="written_partnership", verifiedAt="2026-08-30"))
    assert any("evidenceUrl" in p for p in spec.validate_against_registry())


def test_근거가_없는_연동은_지금처럼_동작한다():
    """termsGate 를 선언하지 않은 기존 연동의 동작은 바뀌지 않는다."""
    assert _spec().terms_blocked_reason() is None


def test_만료되지_않은_근거는_통과한다():
    spec = _spec(termsGate=TermsGate(basis="official_feed",
                                     verifiedAt="2026-08-01", expiresAt="2027-01-01"))
    assert spec.terms_blocked_reason(today=datetime.date(2026, 8, 30)) is None


def test_만료된_근거는_HTTP_client를_만들기_전에_막는다():
    """'실수로 한 번 나갔다' 가 없으려면 session 을 만드는 자리에서 끊어야 한다."""
    spec = _spec(termsGate=TermsGate(basis="written_partnership", evidenceUrl="https://x",
                                     verifiedAt="2025-01-01", expiresAt="2026-01-01"))
    reason = spec.terms_blocked_reason(today=datetime.date(2026, 8, 30))
    assert reason and "만료" in reason

    with pytest.raises(ConnectorError) as exc:
        spec.new_session()
    assert exc.value.code == "terms_blocked"
    assert "만료" in exc.value.user_message
    # 기다린다고 풀리지 않는다 — 자동 재시도에 걸리면 안 된다
    assert exc.value.retryable is False


def test_만료일이_없으면_만료되지_않는다():
    spec = _spec(termsGate=TermsGate(basis="official_api", verifiedAt="2020-01-01"))
    assert spec.terms_blocked_reason(today=datetime.date(2030, 1, 1)) is None


def test_근거는_세_가지만_받는다():
    """'공개돼 있으니 괜찮다' 는 근거가 아니다."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        TermsGate(basis="robots_txt_allows", verifiedAt="2026-08-30")


# ── 3. 정화 규칙이 정의에서 자동으로 파생된다 ───────────────────────────

@pytest.mark.parametrize("node_type", CONNECTOR_TYPES)
def test_모든_연동_노드가_정화_규칙을_가진다(node_type):
    assert sanitize.rule_for(node_type) is not None, \
        f"{node_type}: 정화 규칙이 없어 이 노드가 든 워크플로우는 공개할 수 없다"


def test_자격증명_필드가_정화_규칙으로_자동_파생된다():
    """새 연동 노드를 추가할 때 정화 표를 따로 쓰지 않아도 되는 근거.

    `httpRequestNode` 는 연동 노드이면서 `credential`/`secret` 필드를 실제로 갖는다
    (youtubeNode 는 자격증명을 필드가 아니라 `connector.credentials` 로 선언한다)."""
    rule = sanitize.rule_for("httpRequestNode")
    definition = node_definition.get_definition("httpRequestNode")
    declared = {f.name for f in definition.fields if f.credential}
    secrets = {f.name for f in definition.fields if f.kind == "secret"}
    assert declared and secrets, "이 노드에 자격증명 필드가 없으면 이 테스트는 아무것도 확인하지 않는다"
    assert set(rule.credential_fields) == declared
    assert set(rule.secret_fields) == secrets


def test_규칙이_없는_노드_타입은_공개_자체를_거부한다():
    with pytest.raises(sanitize.SanitizeRefused):
        sanitize.sanitize_graph({"nodes": [{"id": "x", "type": "naverCafeNodeMaybe", "data": {}}],
                                 "edges": []})


# ── 4. 커뮤니티 연동은 근거 선언이 의무다 ───────────────────────────────
# 범용 크롤러에서 막는 곳을 전용 connector 로는 그냥 나가게 두면 정책이 반쪽이 된다.
# 어느 호스트가 제휴 대상인지는 url_guard 한 곳에서만 정하고 contract 가 그대로 쓴다.

import url_guard


def test_제휴_대상_호스트는_한_곳에서만_정한다():
    assert url_guard.requires_partnership("gall.dcinside.com") is True
    assert url_guard.requires_partnership("www.fmkorea.com") is True
    assert url_guard.requires_partnership("bbs.ruliweb.com") is False


def test_제휴_대상_연동이_근거_없이_정의되면_거부한다():
    spec = _spec(role="trigger", modes=["new_post"], sideEffectByMode={"new_post": "external-read"},
                 baseUrl="https://gall.dcinside.com/api")
    problems = spec.validate_against_registry()
    assert any("termsGate" in p for p in problems)


def test_근거를_선언하면_통과한다():
    spec = _spec(role="trigger", modes=["new_post"], sideEffectByMode={"new_post": "external-read"},
                 baseUrl="https://gall.dcinside.com/api",
                 termsGate=TermsGate(basis="written_partnership", evidenceUrl="https://계약문서",
                                     verifiedAt="2026-08-30", expiresAt="2027-08-30"))
    assert spec.validate_against_registry() == []


def test_제휴_대상이_아닌_연동에는_근거를_요구하지_않는다():
    """루리웹처럼 공식 RSS 를 제공하는 곳까지 계약서를 요구하면 아무것도 못 만든다."""
    spec = _spec(baseUrl="https://bbs.ruliweb.com")
    assert spec.validate_against_registry() == []


def test_기존_연동은_이_규칙에_걸리지_않는다():
    """도입한 규칙이 지금 돌아가는 연동을 깨지 않는지 — 회귀 0."""
    for node_type in CONNECTOR_TYPES:
        connector = node_definition.get_definition(node_type).connector
        assert connector.validate_against_registry() == [], node_type


# ── verifiedAt — "언제 기준의 사실인가" (F5, 2026-08-30) ────────────────
#
# `docsUrl` 은 로드 시점에 강제되지만 `verifiedAt` 은 아니다. 강제하면 "일단 오늘 날짜를
# 넣고 보자" 가 되어 필드가 거짓이 되기 때문이다 — 그래서 **비어 있는 것을 눈에 띄게** 한다.

# 문서를 실제로 열어 대조하지 못한 연동. 왜 못 했는지를 함께 적는다.
UNVERIFIED_ON_PURPOSE = {
    "jusoNode": "juso.go.kr 이 자동 요청에 403 을 준다 — 규격을 2차 출처에서 모았다. "
                "승인키를 받아 실응답과 대조한 뒤 채운다",
}


def test_대조하지_못한_연동은_목록에_적혀_있다():
    """`verifiedAt` 이 비어 있는 것이 조용히 늘지 않게 한다."""
    import node_definition

    missing = {t for t, d in node_definition.NODE_DEFINITIONS.items()
               if d.connector and not d.connector.verifiedAt}
    unlisted = missing - set(UNVERIFIED_ON_PURPOSE)
    assert not unlisted, (
        f"공식 문서 대조 기록이 없는 연동: {sorted(unlisted)} — "
        "대조했으면 verifiedAt 을 채우고, 못 했으면 이유를 UNVERIFIED_ON_PURPOSE 에 적는다")


def test_목록에_있는데_이미_채워졌으면_지운다():
    """대조를 마치고도 목록에 남겨 두면 다음 사람이 또 확인한다."""
    import node_definition

    for node_type in UNVERIFIED_ON_PURPOSE:
        definition = node_definition.get_definition(node_type)
        if definition is None or definition.connector is None:
            continue
        assert not definition.connector.verifiedAt, (
            f"{node_type} 는 이제 대조됐다 — UNVERIFIED_ON_PURPOSE 에서 빼라")


def test_verifiedAt은_날짜꼴이다():
    import datetime

    import node_definition

    for node_type, definition in node_definition.NODE_DEFINITIONS.items():
        value = definition.connector.verifiedAt if definition.connector else None
        if not value:
            continue
        parsed = datetime.date.fromisoformat(value)   # 형식이 틀리면 여기서 터진다
        assert parsed <= datetime.date.today(), f"{node_type} 의 대조일이 미래다: {value}"
