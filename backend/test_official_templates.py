"""공식 템플릿이 실제로 게시 가능한 상태인지 (2026-08-30 · i묶음 2026-08-31).

이 파일이 지키는 문장:

  1. **깨진 템플릿을 '공식' 으로 내보내지 않는다.** 게시 게이트가 보는 것과 같은 검사를 여기서 돈다.
  2. **142개와 겹치지 않는다.** 새로 만든 이유가 "그때는 없던 노드를 쓴다" 이므로,
     그 노드를 실제로 쓰는지 확인한다.
  3. **분류·태그가 갤러리 규칙 안에 있다.** publish 시점이 아니라 여기서 걸린다.
"""

from __future__ import annotations

import json

import pytest

import community_sanitize
import community_templates
import official_templates
import python_runtime
from dry_run import dry_run_workflow
from meta_agent import FlowGraph, validate_flow

TEMPLATES = official_templates.TEMPLATES
IDS = [t["title"] for t in TEMPLATES]

# 142개(2026-08-28)가 쓰던 노드. 새 묶음은 이것 말고 다른 것도 써야 의미가 있다.
NODES_IN_2026_08_28 = {
    "promptNode", "llmNode", "outputNode", "httpRequestNode", "startNode", "dynamicInputNode",
    "mergeNode", "conditionNode", "valueNode", "webhookNode", "slackNode", "jsonParserNode",
    "distributorNode", "scheduleNode", "humanApprovalNode", "emailNode", "tokenizerNode",
    "kakaoNode", "pythonNode", "templateAnalyzerNode", "fileModifierNode", "databaseNode",
    "discordNode", "webCrawlerNode",
}


def _graph(t):
    return FlowGraph.model_validate(t["graph"])


def test_묶음_개수가_유지된다():
    # 100(a~h, 2026-08-30) + 7(i묶음 — 데이터 바인딩, 2026-08-31)
    assert len(TEMPLATES) == 107


def test_제목이_겹치지_않는다():
    titles = [t["title"] for t in TEMPLATES]
    assert len(set(titles)) == len(titles), "같은 제목이 둘 이상 있다"


# ── 게시 게이트가 보는 것과 같은 검사 ───────────────────────────────────

@pytest.mark.parametrize("t", TEMPLATES, ids=IDS)
def test_스키마와_구조가_유효하다(t):
    ok, errors = validate_flow(_graph(t))
    assert ok, "; ".join(errors[:3])


@pytest.mark.parametrize("t", TEMPLATES, ids=IDS)
def test_정화를_통과한다(t):
    snapshot, _report = community_sanitize.sanitize_graph(json.loads(_graph(t).model_dump_json()))
    assert snapshot["nodes"], "정화 뒤 내용이 비었다"


@pytest.mark.parametrize("t", TEMPLATES, ids=IDS)
def test_dry_run을_통과한다(t):
    snapshot, _r = community_sanitize.sanitize_graph(json.loads(_graph(t).model_dump_json()))
    checked = dry_run_workflow(snapshot)
    assert checked.structural_passed and checked.compile_passed, "; ".join(checked.issues[:3])


@pytest.mark.parametrize("t", TEMPLATES, ids=IDS)
def test_분류가_갤러리_규칙_안이다(t):
    assert t["category"] in community_templates.CATEGORIES


@pytest.mark.parametrize("t", TEMPLATES, ids=IDS)
def test_설명과_태그가_있다(t):
    assert t["description"].strip(), "설명이 비었다 — 갤러리에서 무엇인지 알 수 없다"
    assert t["tags"], "태그가 없다"


# ── 새로 만든 이유가 유지되는가 ─────────────────────────────────────────

def test_그때는_없던_노드를_실제로_쓴다():
    """142개와 겹치기만 하는 묶음이면 새로 만들 이유가 없었다."""
    used = {n["type"] for t in TEMPLATES for n in t["graph"]["nodes"]}
    fresh = used - NODES_IN_2026_08_28
    assert len(fresh) >= 10, f"새 노드를 거의 안 쓴다: {sorted(fresh)}"


def test_한국형_노드가_들어있다():
    used = {n["type"] for t in TEMPLATES for n in t["graph"]["nodes"]}
    for node_type in ("naverSearchNode", "hwpxDocumentNode", "jusoNode"):
        assert node_type in used, f"{node_type} 를 쓰는 템플릿이 없다"


# 받은 것에 **반응해서** 나가는 메일과, 정해진 시각에 나가는 보고는 위험이 다르다.
#
#   gmailTriggerNode → llm → gmailNode   남이 보낸 메일에 자동 회신한다. 내용을 예측할 수 없다.
#   scheduleNode     → llm → gmailNode   정해진 수신자에게 정기 보고를 보낸다.
#
# 앞쪽만 사람 확인을 요구한다. 뒤쪽에 승인을 걸면 금요일 저녁 보고서를 아무도 승인하지 않아
# 영영 안 나간다 — 안전장치가 기능을 죽이는 자리다.
_INBOUND_TRIGGERS = {"gmailTriggerNode", "webhookNode", "discordTriggerNode",
                     "telegramTriggerNode", "naverSearchTriggerNode", "rssTriggerNode",
                     "youtubeTriggerNode"}


@pytest.mark.parametrize("t", TEMPLATES, ids=IDS)
def test_분배_노드_앞에는_목록을_만드는_노드가_있다(t):
    """`distributorNode` 는 앞이 리스트가 아니면 **한 번만 돈다.**

        if not isinstance(dist_list, list):
            dist_list = [dist_list]        # 문자열 하나 → 항목 하나

    앞이 dynamicInputNode(텍스트 한 칸)나 startNode 면 반복하는 것처럼 보이지만 통짜 텍스트가
    그대로 흘러간다. 항목마다 API 를 부르는 노드가 뒤에 있으면 통짜 텍스트를 받아 실패한다
    (2026-08-31 실제로 겪음 — 템플릿 5개가 그랬다).
    """
    import drop_pointless_distributors as checker

    graph = t["graph"]
    types = {n["id"]: n.get("type") for n in graph["nodes"]}
    inc = checker._sources(graph["edges"])
    pointless = [nid for nid, ty in types.items()
                 if ty == "distributorNode" and not checker.receives_a_list(nid, types, inc)]
    assert not pointless, (
        f"{t['title']}: 분배 노드 {pointless} 앞에 목록을 만드는 노드가 없다 — 한 번만 돌아 "
        "반복이 의미가 없다. 목록을 만드는 노드를 앞에 두거나 분배 노드를 빼라"
    )


def test_받은_메일에_자동_회신하지_않는다():
    """외부에서 온 것에 반응해 메일이 나가면 반드시 사람이 한 번 본다."""
    for t in TEMPLATES:
        nodes = t["graph"]["nodes"]
        types = {n["type"] for n in nodes}
        sends = [n for n in nodes
                 if n["type"] == "gmailNode" and n["data"].get("mode") in ("send_email", "reply_email")]
        if not sends or not (types & _INBOUND_TRIGGERS):
            continue
        assert "humanApprovalNode" in types, (
            f"'{t['title']}' 가 외부 입력에 반응해 승인 없이 메일을 보낸다")


def test_정기_보고_메일은_수신자를_비워_둔다():
    """승인을 면제하는 대신, 설치한 사람이 수신자를 직접 채우게 한다 —
    템플릿에 남의 주소가 박혀 나가지 않도록."""
    for t in TEMPLATES:
        for n in t["graph"]["nodes"]:
            if n["type"] == "gmailNode" and n["data"].get("mode") == "send_email":
                assert not n["data"].get("to"), (
                    f"'{t['title']}' 에 받는 사람이 박혀 있다: {n['data'].get('to')}")


def test_카페_게시는_기본이_미리보기다():
    for t in TEMPLATES:
        for n in t["graph"]["nodes"]:
            if n["type"] == "naverCafeNode":
                assert n["data"].get("confirm") is not True, (
                    f"'{t['title']}' 가 확인 없이 카페에 글을 올린다")


def test_코드_노드는_격리가_켜져야_쓴다():
    uses_python = any(n["type"] == "pythonNode"
                      for t in TEMPLATES for n in t["graph"]["nodes"])
    if uses_python:
        assert python_runtime.isolation_enabled(), "격리가 꺼졌는데 코드 노드를 쓰는 템플릿이 있다"
