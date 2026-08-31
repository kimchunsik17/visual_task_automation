"""documents/hwpx/placeholders.py — 여러 run 으로 쪼개진 `{{자리표시자}}` 를 찾아 채운다.

■ 왜 문자열 치환으로는 안 되는가

예전 구현은 section XML 문자열에 `xml_str.replace('{{name}}', value)` 를 했다. 사용자가 한/글에서
`{{name}}` 의 일부만 굵게 하거나, 입력 도중 서식이 바뀌면 그 한 낱말이 이렇게 쪼개진다.

    <hp:run charPrIDRef="0"><hp:t>{{cust</hp:t></hp:run>
    <hp:run charPrIDRef="3"><hp:t>omer}}</hp:t></hp:run>

문자열에는 `{{customer}}` 가 **없다.** 그래서 조용히 안 채워진 채로 결과가 나갔다. 라이브러리의
`replace_text_in_runs` 도 run 하나씩 보므로 같은 한계가 있다(실제로 확인함 — 쪼개진 경우 0건 치환).

■ 그래서 무엇을 하는가

문단 하나를 단위로, 그 안의 `<hp:t>` 들을 이어 붙여 **논리 문자열**을 만들고 거기서 찾는다.
찾은 범위가 여러 `<hp:t>` 에 걸치면 **첫 조각에 값을 넣고 나머지 조각에서는 지운다.** 값이
첫 조각의 서식을 따르는 것은 의도한 선택이다 — 자리표시자가 시작된 곳의 서식이 그 자리에
들어갈 값의 서식이라고 보는 편이 자연스럽다.

■ 건드리지 않는 것

`<hp:tab/>` 같은 제어 요소는 `<hp:t>` 의 형제로 들어간다. 논리 문자열을 만들 때 그 자리에
**경계 문자**를 넣어, 자리표시자가 제어 요소를 가로질러 매칭되지 않게 한다. 그러지 않으면
탭 하나가 값 한가운데에 남는다.

자식 요소가 있는 `<hp:t>`(드물지만 있다)는 안전하게 편집할 수 없으므로 건너뛰고 **미치환으로
보고한다.** 조용히 망가뜨리는 것보다 낫다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

# 제어 요소(`<hp:tab/>` 등) 자리를 메우는 경계 문자. 자리표시자가 이걸 가로지르면 안 된다.
_BARRIER = "\uffff"

# `{{key}}` — 앞뒤 여백은 허용하고(사람이 `{{ name }}` 이라고 쓴다), **이름 안에는 공백을 허용하지
# 않는다.** 허용하면 본문의 `{{` 와 한참 뒤 `}}` 가 우연히 이어져 문장 한 덩어리를 자리표시자로
# 오인한다. 경계 문자도 이름에 들어올 수 없다.
PLACEHOLDER_RE = re.compile(r"\{\{[ \t]*([^{}\s\uffff]+)[ \t]*\}\}")

_HP_T = "t"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


@dataclass
class _Slot:
    """논리 문자열의 한 구간을 담당하는 `<hp:t>` 노드."""

    node: ET.Element
    start: int
    text: str
    editable: bool

    @property
    def end(self) -> int:
        return self.start + len(self.text)


@dataclass
class FillResult:
    filled: Dict[str, int] = field(default_factory=dict)     # key → 채운 횟수
    unresolved: List[str] = field(default_factory=list)      # 문서에 남은 자리표시자
    unused: List[str] = field(default_factory=list)          # 값은 줬는데 자리가 없던 key
    skipped: List[str] = field(default_factory=list)         # 안전하게 편집할 수 없던 자리

    @property
    def ok(self) -> bool:
        return not self.unresolved and not self.skipped

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filled": dict(self.filled),
            "unresolved": sorted(set(self.unresolved)),
            "unused": sorted(set(self.unused)),
            "skipped": sorted(set(self.skipped)),
        }


def _paragraphs(root: ET.Element) -> List[ET.Element]:
    """표 안의 문단까지 포함해 모든 `<hp:p>`. 표는 셀 안에 문단을 품으므로 재귀로 자연히 걸린다."""
    return [el for el in root.iter() if _local(el.tag) == "p"]


def _slots_for(paragraph: ET.Element) -> Tuple[str, List[_Slot]]:
    """문단의 논리 문자열과, 그 문자열을 이루는 `<hp:t>` 조각들.

    `<hp:p>` 바로 아래가 아니라 `<hp:run>` 안에 있고, 표 안 문단은 별도로 처리되므로
    **자기 문단에 속한 run 들만** 본다(중첩 문단의 텍스트를 끌어오면 안 된다).
    """
    pieces: List[str] = []
    slots: List[_Slot] = []
    cursor = 0

    for run in list(paragraph):
        if _local(run.tag) != "run":
            continue
        for child in list(run):
            name = _local(child.tag)
            if name == _HP_T:
                editable = len(child) == 0        # 자식 요소가 있으면 손대지 않는다
                text = child.text or "" if editable else "".join(child.itertext())
                slots.append(_Slot(node=child, start=cursor, text=text, editable=editable))
                pieces.append(text)
                cursor += len(text)
            else:
                # 탭·줄바꿈·컨트롤 등. 자리표시자가 이걸 가로질러 매칭되면 안 된다.
                pieces.append(_BARRIER)
                cursor += 1
    return "".join(pieces), slots


def find_placeholders(root: ET.Element) -> List[str]:
    """문서에 있는 자리표시자 이름들(중복 제거 전, 등장 순)."""
    found: List[str] = []
    for paragraph in _paragraphs(root):
        logical, _slots = _slots_for(paragraph)
        found.extend(m.group(1) for m in PLACEHOLDER_RE.finditer(logical))
    return found


def _apply(slots: List[_Slot], start: int, end: int, value: str) -> bool:
    """[start, end) 범위를 value 로 바꾼다. 편집할 수 없으면 False."""
    touched = [s for s in slots if s.end > start and s.start < end and s.text]
    if not touched or any(not s.editable for s in touched):
        return False

    first = touched[0]
    # 첫 조각: 앞부분 + 값 + (이 조각이 범위 끝을 넘으면) 뒷부분
    head = first.text[: start - first.start]
    tail = first.text[end - first.start:] if first.end > end else ""
    first.node.text = head + value + tail
    first.text = first.node.text

    # 나머지 조각: 범위에 걸친 부분만 지운다
    for slot in touched[1:]:
        keep_head = slot.text[: max(0, start - slot.start)]
        keep_tail = slot.text[end - slot.start:] if slot.end > end else ""
        slot.node.text = keep_head + keep_tail
        slot.text = slot.node.text
    return True


def fill_placeholders(root: ET.Element, values: Dict[str, Any]) -> FillResult:
    """문단마다 논리 문자열에서 자리표시자를 찾아 값을 넣는다.

    값이 없는 자리표시자는 **그대로 두고** `unresolved` 로 보고한다 — 빈 문자열로 지우면
    사용자가 무엇이 안 채워졌는지 알 수 없다.
    """
    result = FillResult()
    seen_keys: set = set()

    for paragraph in _paragraphs(root):
        # 한 번 고치면 뒤쪽 offset 이 밀리므로, 매칭을 다시 계산하며 앞에서부터 하나씩 처리한다.
        guard = 0
        while True:
            guard += 1
            if guard > 1000:      # 병적인 입력에서 무한 루프를 막는다
                break
            logical, slots = _slots_for(paragraph)
            match = None
            for candidate in PLACEHOLDER_RE.finditer(logical):
                key = candidate.group(1)
                seen_keys.add(key)
                if key in values:
                    match = candidate
                    break
                result.unresolved.append(key)
            if match is None:
                break

            key = match.group(1)
            value = values[key]
            text = "" if value is None else str(value)
            if _apply(slots, match.start(), match.end(), text):
                result.filled[key] = result.filled.get(key, 0) + 1
            else:
                result.skipped.append(key)
                break     # 이 문단은 더 건드리지 않는다

    result.unused = [k for k in values if k not in seen_keys]
    # 같은 자리표시자가 여러 번 나오면 unresolved 에 중복이 쌓인다 — 채운 것은 빼고 정리한다.
    result.unresolved = [k for k in dict.fromkeys(result.unresolved) if k not in result.filled]
    return result
