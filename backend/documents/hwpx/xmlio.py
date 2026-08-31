"""documents/hwpx/xmlio.py — section XML 을 파싱하고 **원래 모양대로** 다시 쓴다.

`ElementTree` 는 파싱할 때 namespace 접두사를 버리고 URI 만 남긴다. 그대로 직렬화하면
`<hp:t>` 가 `<ns0:t>` 로 바뀐다 — XML 로서는 같지만, 한/글이 이걸 어떻게 받아들일지는
확인된 바 없고 파일 diff 도 전부 뒤집힌다. 그래서 원본에 선언된 접두사를 그대로 등록한 뒤
직렬화한다.

XML 선언(`<?xml ... ?>`)도 ET 가 만드는 것이 원본과 다르므로(따옴표 종류·standalone) 원본
첫 줄을 그대로 다시 붙인다.
"""

from __future__ import annotations

import re
from typing import Dict, Tuple
from xml.etree import ElementTree as ET

from . import safety

_XMLNS_RE = re.compile(rb'xmlns:([A-Za-z0-9_.-]+)\s*=\s*"([^"]+)"')
_DEFAULT_NS_RE = re.compile(rb'xmlns\s*=\s*"([^"]+)"')
_DECL_RE = re.compile(rb"^\s*<\?xml[^>]*\?>")


def namespaces(raw: bytes) -> Dict[str, str]:
    """원본에 선언된 접두사 → URI."""
    return {m.group(1).decode(): m.group(2).decode() for m in _XMLNS_RE.finditer(raw)}


_ROOT_OPEN_RE = re.compile(rb"<([A-Za-z_][\w.:-]*)((?:\s[^<>]*?)?)/?>", re.S)


def _root_namespace_declarations(raw: bytes) -> bytes:
    """루트 여는 태그에 선언된 xmlns 들을 그대로 뽑는다.

    ET 는 **실제로 쓰인** 접두사만 다시 쓴다. HWPX 루트는 14개를 선언하는데 본문이 두세 개만
    쓰므로, 그대로 두면 나머지가 사라져 파일이 크게 달라진다. 한/글이 그걸 어떻게 받아들일지
    확인된 바 없으므로 **원본 선언을 그대로 되돌린다.**
    """
    body = raw[raw.find(b"<", raw.find(b"?>") + 2 if b"?>" in raw else 0):]
    match = _ROOT_OPEN_RE.search(body)
    if not match:
        return b""
    declarations = re.findall(rb'\sxmlns(?::[A-Za-z0-9_.-]+)?\s*=\s*"[^"]*"', match.group(2))
    return b"".join(declarations)


def parse(raw: bytes, *, name: str = "section") -> Tuple[ET.Element, bytes]:
    """(root, 원본 XML 선언) 을 돌려준다. 파싱 전에 안전 검사를 거친다."""
    safety.check_xml(raw, name=name)
    for prefix, uri in namespaces(raw).items():
        # 전역 등록이라 같은 접두사를 다른 URI 로 쓰는 문서가 섞이면 뒤엉킬 수 있다. HWPX 는
        # 접두사와 URI 가 스펙으로 고정돼 있어(hp/hs/hc/hh…) 실제로는 항상 같은 짝이다.
        ET.register_namespace(prefix, uri)
    default = _DEFAULT_NS_RE.search(raw)
    if default:
        ET.register_namespace("", default.group(1).decode())

    declaration = b""
    found = _DECL_RE.match(raw)
    if found:
        declaration = found.group(0)
    # 선언 뒤에 원본 루트의 xmlns 목록을 덧붙여 함께 들고 다닌다(serialize 가 되돌린다).
    header = declaration + b"\x00" + _root_namespace_declarations(raw)
    return ET.fromstring(raw.decode("utf-8")), header


def serialize(root: ET.Element, header: bytes) -> bytes:
    """편집한 트리를 원본 선언·namespace 선언과 함께 바이트로."""
    declaration, _, original_ns = header.partition(b"\x00")
    body = ET.tostring(root, encoding="utf-8", xml_declaration=False)

    if original_ns:
        match = _ROOT_OPEN_RE.search(body)
        if match:
            present = set(re.findall(rb'xmlns(?::[A-Za-z0-9_.-]+)?\s*=', match.group(2)))
            missing = b"".join(
                d for d in re.findall(rb'\sxmlns(?::[A-Za-z0-9_.-]+)?\s*=\s*"[^"]*"', original_ns)
                if re.match(rb'\s(xmlns(?::[A-Za-z0-9_.-]+)?\s*=)', d).group(1) not in present
            )
            if missing:
                insert_at = match.start(2)
                body = body[:insert_at] + missing + body[insert_at:]

    # 선언 뒤에 개행을 넣지 않는다 — 원본이 그렇고, 안 건드린 entry 와 모양을 맞춘다.
    return declaration + body if declaration else body
