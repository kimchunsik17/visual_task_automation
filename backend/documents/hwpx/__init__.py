"""backend/documents/hwpx — HWPX 문서 처리 공용 엔진 (한국형 노드 계획 Phase 1).

예전에는 HWPX 처리가 **생성 코드 문자열 안에** 있었다(`node_generators/template_nodes.py`).
그래서 두 노드(`templateAnalyzerNode`·`fileModifierNode`)가 각자 같은 일을 조금씩 다르게 했고,
포맷 버그를 고치면 두 군데를 고쳐야 했으며, 무엇보다 **테스트할 방법이 없었다.**

이 패키지가 정본이다. 노드는 여기를 부르기만 한다.

    builder      DocumentSpec(JSON) 으로 새 문서를 만든다
    safety       패키지를 열어도 되는지 (zip bomb·경로 탈출·XML 폭탄)
    placeholders 여러 run 으로 쪼개진 {{자리표시자}} 를 찾아 채운다
    package      원본의 entry 순서·압축 방식을 보존해 다시 묶는다
"""

from .builder import SpecError, UnsupportedFeature, build, validate_spec
from .package import HwpxPackage, PackageWriteError
from .placeholders import FillResult, find_placeholders, fill_placeholders
from .safety import PackageRejected, MAX_ENTRIES, MAX_TOTAL_BYTES

__all__ = [
    "build", "validate_spec", "SpecError", "UnsupportedFeature",
    "HwpxPackage", "PackageWriteError",
    "FillResult", "find_placeholders", "fill_placeholders",
    "PackageRejected", "MAX_ENTRIES", "MAX_TOTAL_BYTES",
]


def fill_template(template_path: str, values: dict, output_path: str) -> "FillResult":
    """서식의 `{{자리표시자}}` 를 채워 **새 파일**로 저장한다.

    입력 서식은 읽기만 한다 — 어떤 경우에도 덮어쓰지 않는다(§2 불일치 3 이 그 회귀였다).
    편집한 section 만 다시 직렬화하고 나머지 entry 는 원본 바이트를 그대로 옮긴다.
    """
    from . import xmlio

    package = HwpxPackage.open(template_path)
    merged = FillResult()
    for name in package.section_names():
        root, header = xmlio.parse(package.read(name), name=name)
        result = fill_placeholders(root, values)
        if result.filled:
            package.replace(name, xmlio.serialize(root, header))
        for key, count in result.filled.items():
            merged.filled[key] = merged.filled.get(key, 0) + count
        merged.unresolved.extend(result.unresolved)
        merged.skipped.extend(result.skipped)

    seen = set(merged.filled) | set(merged.unresolved) | set(merged.skipped)
    merged.unused = sorted(k for k in values if k not in seen)
    merged.unresolved = sorted({k for k in merged.unresolved if k not in merged.filled})
    merged.skipped = sorted(set(merged.skipped))
    package.save_as(output_path)
    return merged


def template_keys(template_path: str) -> list:
    """서식에 있는 자리표시자 이름들(등장 순, 중복 제거)."""
    from . import xmlio

    package = HwpxPackage.open(template_path)
    found = []
    for name in package.section_names():
        root, _header = xmlio.parse(package.read(name), name=name)
        found.extend(find_placeholders(root))
    return list(dict.fromkeys(found))


__all__ += ["fill_template", "template_keys"]
