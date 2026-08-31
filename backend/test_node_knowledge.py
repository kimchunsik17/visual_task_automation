"""node_knowledge(ADR-0013) 테스트 — 색인 문서/동기화/lexical·hybrid 선별/트레이스 수집.

embedding은 FakeEmbeddingProvider(결정론적 해시 벡터)로 대체해 네트워크 없이 돈다.
Chroma 저장소는 케이스마다 tmp_path로 격리한다(운영 chroma_db를 건드리지 않는다).
"""

import hashlib

import pytest

import node_knowledge
from node_knowledge import (
    NODE_ALIASES,
    begin_selection_trace,
    build_capability_documents,
    collect_selection_trace,
    hybrid_select_node_types,
    known_node_types,
    lexical_candidates,
    record_selection_event,
    summarize_selection,
    sync_node_index,
)


class FakeEmbeddingProvider(node_knowledge.EmbeddingProvider):
    """텍스트 해시로 만드는 결정론적 저차원 벡터. 유사도의 의미는 없지만 색인/조회/캐시
    경로를 실제 Chroma에 태워 검증하기에는 충분하다."""

    model_id = "fake:test-embedding"

    def __init__(self):
        self.document_calls = 0
        self.query_calls = 0

    def _vector(self, text: str):
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [b / 255.0 for b in digest[:8]]

    def embed_documents(self, texts):
        self.document_calls += 1
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        self.query_calls += 1
        return self._vector(text)


# ── 색인 문서 ────────────────────────────────────────────────────────────
def test_카탈로그의_모든_노드가_문서와_별칭을_가진다():
    documents = {doc["metadata"]["node_type"] for doc in build_capability_documents()}
    catalog_types = set(known_node_types())
    assert documents == catalog_types
    # 별칭 테이블이 카탈로그와 어긋나면(오타/삭제된 노드) lexical 선별이 조용히 구멍난다.
    assert set(NODE_ALIASES) == catalog_types
    assert all(NODE_ALIASES[t] for t in NODE_ALIASES)


def test_문서_메타데이터와_해시가_안정적이다():
    first = {doc["id"]: doc for doc in build_capability_documents()}
    second = {doc["id"]: doc for doc in build_capability_documents()}
    assert first.keys() == second.keys()
    for doc_id, doc in first.items():
        assert doc["metadata"]["content_hash"] == second[doc_id]["metadata"]["content_hash"]
        assert doc["metadata"]["status"] == "active"
        assert doc["metadata"]["role"] in {"trigger", "action"}
    # 정의 파일이 있는 노드는 정의의 사실이 metadata로 온다.
    youtube = first["youtubeNode@1"]["metadata"]
    assert youtube["service"] == "YouTube"
    assert youtube["side_effect"] == "external-write"
    assert "google_oauth" in youtube["credential_providers"]
    trigger = first["youtubeTriggerNode@1"]["metadata"]
    assert trigger["role"] == "trigger"


# ── lexical 선별 ────────────────────────────────────────────────────────
def test_lexical_선별이_한국어_표현을_찾는다():
    hits = lexical_candidates("매일 아침 9시에 서울 날씨 API를 조회해서 슬랙으로 보내줘.")
    assert "scheduleNode" in hits
    assert "httpRequestNode" in hits
    assert "slackNode" in hits
    assert "kakaoNode" not in hits


def test_lexical_선별이_빈_요청에서_비어있다():
    assert lexical_candidates("안녕") == []


# ── 색인 동기화와 hybrid 선별 ───────────────────────────────────────────
def test_색인_동기화가_증분으로_동작한다(tmp_path):
    provider = FakeEmbeddingProvider()
    first = sync_node_index(provider=provider, db_dir=str(tmp_path))
    assert first["status"] == "synced"
    assert first["upserted"] == first["total"] > 0
    second = sync_node_index(provider=provider, db_dir=str(tmp_path))
    assert second["upserted"] == 0
    assert second["unchanged"] == second["total"]
    # 변경이 없으면 embedding을 다시 호출하지 않는다(비용 원칙: release 시 1회 색인).
    assert provider.document_calls == 1


def test_provider가_없으면_동기화는_건너뛴다(monkeypatch):
    monkeypatch.setenv("NODE_EMBEDDING_PROVIDER", "off")
    assert sync_node_index()["status"] == "skipped"


def test_hybrid_선별이_lexical과_vector를_합친다(tmp_path):
    provider = FakeEmbeddingProvider()
    sync_node_index(provider=provider, db_dir=str(tmp_path))
    result = hybrid_select_node_types(
        "새 영상이 올라오면 요약해서 슬랙으로 보내줘", provider=provider, db_dir=str(tmp_path),
    )
    assert result["source"] == "hybrid"
    assert result["error"] is None
    assert "youtubeTriggerNode" in result["selected_types"]
    assert "slackNode" in result["selected_types"]
    assert len(result["vector_types"]) <= result["top_k"]
    # lexical 후보가 vector 후보보다 앞에 온다(결정론 우선).
    assert result["selected_types"][: len(result["lexical_types"])] == result["lexical_types"]


def test_hybrid_선별이_provider_없이도_동작한다(monkeypatch):
    monkeypatch.setenv("NODE_EMBEDDING_PROVIDER", "off")
    result = hybrid_select_node_types("텔레그램 메시지가 오면 요약해서 답장해줘")
    assert result["source"] == "lexical-only"
    assert "telegramTriggerNode" in result["selected_types"]


def test_query_embedding이_캐시된다(tmp_path):
    provider = FakeEmbeddingProvider()
    sync_node_index(provider=provider, db_dir=str(tmp_path))
    for _ in range(3):
        hybrid_select_node_types("카카오톡으로 주문 알림 보내줘", provider=provider, db_dir=str(tmp_path))
    assert provider.query_calls == 1


# ── 선별 트레이스 수집기 (RAG Phase A) ──────────────────────────────────
def test_수집기가_없으면_기록은_무시된다():
    collect_selection_trace()  # 초기화
    record_selection_event({"stage": "generate_flow"})
    assert collect_selection_trace() is None


def test_수집기가_이벤트를_모으고_회수_후_비워진다():
    begin_selection_trace()
    record_selection_event({"stage": "generate_flow", "llm": {"selected_types": ["slackNode"]}})
    trace = collect_selection_trace()
    assert trace and len(trace["events"]) == 1
    assert collect_selection_trace() is None


def test_선별_요약이_누락과_불필요_타입을_계산한다():
    events = [{
        "stage": "generate_flow",
        "llm": {
            "selected_types": ["slackNode", "conditionNode"],
            "token_usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110},
        },
        "catalog": {
            "fallback_full_catalog": False,
            "offered_types": ["startNode", "promptNode", "llmNode", "outputNode", "slackNode", "conditionNode"],
            "trimmed_chars": 1000,
            "full_chars": 4000,
        },
        "shadow": {
            "selected_types": ["slackNode", "scheduleNode"],
            "source": "hybrid",
            "embedding_model": "fake:test-embedding",
        },
    }]
    summary = summarize_selection(events, ["startNode", "scheduleNode", "slackNode", "outputNode"])
    # LLM 쪽: scheduleNode가 카탈로그에 없었다(누락), conditionNode는 안 쓰였다(불필요).
    assert summary["llm_selector"]["missing_vs_final"] == ["scheduleNode"]
    assert "conditionNode" in summary["llm_selector"]["unused"]
    assert summary["llm_selector"]["token_usage"]["total_tokens"] == 110
    # hybrid 쪽: startNode/outputNode는 항상 포함이라 selector 몫이 아니지만, 요약은
    # 제공 후보 기준으로 비교한다 — 승격 판단은 recall 게이트(항상 포함 인정)가 한다.
    assert "scheduleNode" not in summary["hybrid_selector"]["missing_vs_final"]
    assert "conditionNode" in summary["agreement"]["llm_only"]
    assert summary["agreement"]["hybrid_only"] == ["scheduleNode"]
    assert summary["event_count"] == 1


def test_생성_트레이스에_node_selection이_실린다():
    from generation_trace import build_generation_trace

    trace = build_generation_trace(
        trace_id="t1", thread_id="th1", message="테스트", complexity_level="low",
        graph_data={"nodes": [], "edges": []}, outcome="chat", status="completed",
        latency_ms=1, node_selection={"schema_version": "node-selection-v1", "event_count": 0},
    )
    assert trace["node_selection"]["schema_version"] == "node-selection-v1"
    trace_without = build_generation_trace(
        trace_id="t2", thread_id="th1", message="테스트", complexity_level="low",
        graph_data={"nodes": [], "edges": []}, outcome="chat", status="completed", latency_ms=1,
    )
    assert trace_without["node_selection"] is None


# ── 평가 라벨 (RAG Phase A) ─────────────────────────────────────────────
def test_평가_케이스의_forbidden_라벨이_유효하다():
    from evaluation import TEST_CASES

    known = set(known_node_types())
    for case in TEST_CASES:
        forbidden = set(case.get("forbidden_nodes", []))
        assert forbidden <= known, f"case {case['id']}: 알 수 없는 forbidden 타입 {forbidden - known}"
        overlap = forbidden & set(case["expected_nodes"])
        assert not overlap, f"case {case['id']}: expected와 forbidden이 겹친다 {overlap}"


# ── dependency closure ──────────────────────────────────────────────────
def test_조건_어미가_conditionNode를_찾는다():
    assert "conditionNode" in lexical_candidates("서비스 상태를 확인해 장애면 슬랙으로 알려줘")
    assert "conditionNode" in lexical_candidates("입력이 비어 있으면 안내해줘")


def test_트리거가_없으면_dynamicInputNode를_보강한다():
    from node_knowledge import dependency_closure

    assert "dynamicInputNode" in dependency_closure(["llmNode", "outputNode"])
    # lexical에 트리거가 있으면 보강하지 않는다.
    assert "dynamicInputNode" not in dependency_closure(
        ["scheduleNode", "llmNode"], lexical=["scheduleNode"])
    # vector가 추측으로 고른 트리거는 보강을 억제하지 못한다(결정론적 근거 우선).
    assert "dynamicInputNode" in dependency_closure(
        ["scheduleNode", "googleCalendarNode"], lexical=["googleCalendarNode"])


def test_분기_노드가_있으면_mergeNode를_보강한다():
    from node_knowledge import dependency_closure

    assert "mergeNode" in dependency_closure(["conditionNode", "slackNode"], lexical=["scheduleNode"])
    assert "mergeNode" in dependency_closure(["humanApprovalNode"], lexical=["webhookNode"])
    assert "mergeNode" not in dependency_closure(["llmNode"], lexical=["scheduleNode"])
