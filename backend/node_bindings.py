"""node_bindings.py — 필드 데이터 바인딩(BindingSpec v1) 계약.

계획: Documents/plans/DATA_FLOW_SEPARATION_PLAN.md §3.

노드 사이 값은 여전히 문자열 하나(실행 엣지)로 흐른다. 그 위에 **필드 단위 바인딩**을 얹어,
하류 노드의 입력 필드가 상류 노드 출력의 특정 경로를 직접 가리키게 한다:

    "bindings": { "toEmail": { "source": "n_webhook", "path": "customer.email" } }

이 계약의 원형은 databaseNode.parameters 의 {source, path}(ADR-0017)이고, 그것을
"직전 노드"에서 "실행 경로상 임의 상류"로, 한 노드에서 여러 노드로 일반화한 것이다.

정본은 **엣지가 아니라 노드 data** 다 — 캔버스에 선을 상시 그리지 않기 위한 결정(§5).

■ 지원 범위를 명시한다

바인딩은 생성기가 그 필드를 **런타임 조회로 바꿔야** 동작한다(코드젠이 값을 컴파일 타임
리터럴로 굽기 때문 — §7 리스크 1). 그래서 지원 필드를 여기 정본으로 두고, 목록에 없는 필드에
바인딩이 걸리면 **조용히 무시하지 않고 검증에서 거부**한다. 목록과 생성기의 어긋남은
test_node_bindings.py 가 실제 컴파일 결과로 대조한다.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# 노드 타입 → 바인딩을 받을 수 있는 필드. 생성기를 런타임 조회로 전환한 것만 넣는다.
BINDABLE_FIELDS: Dict[str, Tuple[str, ...]] = {
    "emailNode": ("toEmail", "subject"),
    "discordNode": ("channelId",),
    "slackNode": ("channel", "message"),
    "telegramNode": ("chatId",),
    "kakaoNode": ("receiver",),
    "httpRequestNode": ("url", "body"),
    "formatNode": ("formatId", "values", "output_path"),
    "webCrawlerNode": ("url",),
    # 변수 허브(§5-5) — valueNode 가 상류 값을 한 번 받아 이름을 붙이고, 하류 여러 곳이 이 노드를
    # 바인딩한다. 같은 경로를 5곳에 복사하는 대신 허브 하나만 고치면 된다.
    "valueNode": ("value",),
}

# JSON 경로 문법: a.b[0].c — databaseNode.parameters 의 path 와 같은 규칙.
# 한글 등 유니코드 키를 허용한다 — 카카오·네이버·Notion 응답의 JSON 키가 한글인 경우가 흔하다.
# 구분자는 점과 대괄호뿐이고, 빈 세그먼트("a..b")는 거부된다.
#
# **최상위가 배열인 출력도 있다**: rssTriggerNode·gmailTriggerNode·naverSearchTriggerNode·
# youtubeTriggerNode 는 "새 항목 배열" 을 그대로 내보내므로 경로가 "[0].link" 로 시작한다.
# 처음 규칙은 키로만 시작할 수 있어서 이 경로를 거부했는데, 정작 가이드의 힌트와 에디터 픽커는
# 그 경로를 만들어 냈다(2026-08-31 템플릿 작성 중 발견 — RSS 템플릿이 검증에서 막혔다).
_PATH_TOKEN = re.compile(r"[^.\[\]]+|\[\d+\]")
_PATH_OK = re.compile(r"^((\[\d+\])+|[^.\[\]]+(\[\d+\])*)(\.[^.\[\]]+(\[\d+\])*)*$")


class BindingError(ValueError):
    """바인딩 선언이 잘못됐다. 메시지는 사용자에게 그대로 보여도 되는 수준으로 쓴다."""

    def __init__(self, message: str, *, reason: str = "BINDING_INVALID"):
        super().__init__(message)
        self.reason = reason


def bindings_of(node: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """노드의 bindings 를 정규화해 돌려준다. 값이 dict 가 아닌 항목은 무시한다."""
    raw = (node.get("data") or {}).get("bindings")
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for field, spec in raw.items():
        if not isinstance(field, str) or not isinstance(spec, dict):
            continue
        source = spec.get("source")
        if not isinstance(source, str) or not source:
            continue
        result[field] = {
            "source": source,
            "path": str(spec.get("path") or ""),
            "required": spec.get("required", True) is not False,
        }
    return result


def is_bound(node: Dict[str, Any], field: str) -> bool:
    return field in bindings_of(node)


def bindable_fields(node_type: str) -> Tuple[str, ...]:
    return BINDABLE_FIELDS.get(node_type, ())


def _upstream_ids(node_id: str, edges: List[Dict[str, Any]]) -> set:
    """node_id 로 오는 실행 경로의 모든 상류 노드 id (역방향 BFS)."""
    incoming: Dict[str, List[str]] = {}
    for edge in edges:
        target = str(edge.get("target"))
        incoming.setdefault(target, []).append(str(edge.get("source")))
    seen, queue = set(), list(incoming.get(str(node_id), []))
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(incoming.get(current, []))
    return seen


def validate_bindings(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[str]:
    """정적 검사 — 사람이 읽을 사유 목록(빈 목록이면 통과).

    1) 지원하지 않는 노드/필드에 걸린 바인딩          (조용한 무시 방지)
    2) 없는 소스 노드
    3) 실행 경로상 상류가 아닌 소스                  (실행 시점에 값이 없다)
    4) 자기 자신 참조
    5) 경로 문법 오류
    """
    issues: List[str] = []
    by_id = {str(n.get("id")): n for n in nodes}

    for node in nodes:
        node_id = str(node.get("id"))
        node_type = str(node.get("type"))
        bindings = bindings_of(node)
        if not bindings:
            continue
        allowed = bindable_fields(node_type)
        upstream = _upstream_ids(node_id, edges)
        for field, spec in bindings.items():
            if field not in allowed:
                issues.append(
                    f"{node_id}({node_type})의 '{field}' 필드는 데이터 바인딩을 지원하지 않는다"
                    f" (지원: {', '.join(allowed) if allowed else '없음'})"
                )
                continue
            source = spec["source"]
            if source == node_id:
                issues.append(f"{node_id}({node_type})의 '{field}' 바인딩이 자기 자신을 가리킨다")
                continue
            if source not in by_id:
                issues.append(
                    f"{node_id}({node_type})의 '{field}' 바인딩 소스 '{source}' 노드가 없다")
                continue
            if source not in upstream:
                issues.append(
                    f"{node_id}({node_type})의 '{field}' 바인딩 소스 '{source}' 가 실행 경로의 "
                    f"상류가 아니다 — 실행 시점에 그 노드의 결과가 없다")
            path = spec["path"]
            if path and not _PATH_OK.match(path):
                issues.append(
                    f"{node_id}({node_type})의 '{field}' 바인딩 경로 '{path}' 가 올바르지 않다"
                    f" (예: customer.email, items[0].name)")
    return issues


def runtime_map(nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """생성 코드에 심을 {node_id: {field: spec}} — 런타임 해석기가 읽는다.
    지원 필드만 담는다(검증에서 걸러졌더라도 실행이 조용히 다르게 동작하지 않게)."""
    result: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for node in nodes:
        node_id = str(node.get("id"))
        allowed = bindable_fields(str(node.get("type")))
        bound = {f: s for f, s in bindings_of(node).items() if f in allowed}
        if bound:
            result[node_id] = bound
    return result


def extract_path(value: Any, path: str) -> Tuple[bool, Any]:
    """JSON 경로 추출. (찾았는지, 값). 경로가 비면 값 전체."""
    if not path:
        return True, value
    current = value
    for token in _PATH_TOKEN.findall(path):
        if token.startswith("["):
            index = int(token[1:-1])
            if not isinstance(current, (list, tuple)) or index >= len(current):
                return False, None
            current = current[index]
        else:
            if not isinstance(current, dict) or token not in current:
                return False, None
            current = current[token]
    return True, current


def bound_expr(node: Dict[str, Any], node_id: str, field: str, default: Any = "") -> str:
    """생성기가 값 자리에 넣을 **파이썬 표현식 문자열**.

    바인딩이 있으면 런타임 해석 호출, 없으면 안전한 리터럴(repr — 이스케이프 걱정이 없다)이다.
    생성기는 이 함수의 반환값을 따옴표 없이 그대로 삽입한다:

        lines.append(f"    to_email={bound_expr(node, node_id, 'toEmail')},")
    """
    raw = (node.get("data") or {}).get(field, default)
    if raw is None:
        raw = default
    if is_bound(node, field) and field in bindable_fields(str(node.get("type"))):
        return f"_resolve_binding({node_id!r}, {field!r}, {str(raw)!r})"
    return repr(str(raw))


# ── 생성 프롬프트용 [데이터 바인딩] 블록 ────────────────────────────────────
# NODE_CATALOG 원문은 건드리지 않는다(스냅샷 드리프트 테스트와 무관하게 두기 위해) —
# workflow_patterns.PATTERN_CATALOG 와 같은 방식으로 뒤에 붙인다.
#
# 목록은 BINDABLE_FIELDS 에서 파생한다. 손으로 다시 적으면 지원 필드가 늘거나 줄 때
# 프롬프트만 옛 목록을 들고 있게 된다.

# path 를 써도 되는 소스 — 출력 JSON 의 형태가 카탈로그에 문서로 적혀 있는 노드만이다.
# 여기 없는 노드의 결과에 path 를 붙이면 그건 모델이 키 이름을 지어낸 것이다(계획 §6-1).
# 값은 "어떤 경로가 있는지" 힌트이고, test_node_bindings.py 가 카탈로그에 실제로
# 그 노드 항목이 있는지 대조한다.
PATH_DOCUMENTED_SOURCES: Dict[str, str] = {
    "naverSearchNode": "items[0].title, items[0].link, items[0].description",
    "naverSearchTriggerNode": "[0].title, [0].link (새 항목 배열)",
    "jusoNode": "items[0].roadAddress, items[0].jibunAddress",
    "youtubeTriggerNode": "[0].video_id, [0].title, [0].published_at",
    "rssTriggerNode": "[0].title, [0].link, [0].summary, [0].published_at",
    "databaseNode": "data.rows[0][0], data.rowCount (outputFormat='result' 일 때)",
}


def render_binding_guide() -> str:
    """생성 프롬프트에 붙일 [데이터 바인딩] 블록."""
    lines = [
        "[데이터 바인딩 — 앞 노드의 값을 필드에 직접 꽂는다. llmNode·jsonParserNode 로 "
        "값을 다시 성형하는 사슬을 대체한다]",
        '- 문법: 노드의 data 안에 "bindings": {"<필드>": {"source": "<앞 노드 id>", '
        '"path": "<JSON 경로>"}} 를 넣는다. path 는 a.b[0].c 형식이고, 비우면 그 노드의 출력 전체다.',
        "- 값을 옮기기 위해서만 llmNode 나 jsonParserNode 를 추가하지 마라. 바인딩으로 되는 "
        "일이면 노드도 토큰도 쓰지 않는다. LLM 은 판단·요약·작성처럼 실제로 생각이 필요한 자리에만 둔다.",
        "- source 는 **실행 경로상 앞선 노드**여야 한다(엣지를 따라 그 노드에서 이 노드로 올 수 있어야 한다). "
        "분기 반대편이나 뒤 노드를 가리키면 실행 시점에 값이 없다.",
        "- 바인딩을 걸 수 있는 필드는 아래뿐이다. 목록에 없는 필드에 걸면 검증에서 거부된다:",
    ]
    for node_type in sorted(BINDABLE_FIELDS):
        lines.append(f"  · {node_type}: {', '.join(BINDABLE_FIELDS[node_type])}")
    lines += [
        "- **path 를 지어내지 마라.** 아래 노드들만 출력 형식이 정해져 있어서 경로를 쓸 수 있다:",
    ]
    for node_type, hint in PATH_DOCUMENTED_SOURCES.items():
        lines.append(f"  · {node_type}: {hint}")
    lines += [
        "  그 외 노드(webhookNode 의 요청 본문, llmNode 의 출력 등)는 키 이름을 알 수 없다 — "
        "사용자가 요청에서 키 이름을 직접 말한 경우에만 그 이름을 쓰고, 아니면 path 를 빈 문자열로 "
        "둬라(출력 전체). 사용자는 에디터에서 실제 값을 보고 경로를 고를 수 있다.",
        "- 같은 값을 여러 노드가 쓴다면 valueNode 에 data.varName(변수 이름)을 붙여 한 번 받고, "
        "하류 노드들은 그 valueNode 를 source 로 바인딩한다 — 경로를 여러 곳에 복사하지 않는다.",
    ]
    return "\n".join(lines) + "\n"


BINDING_CATALOG = "\n" + render_binding_guide()
