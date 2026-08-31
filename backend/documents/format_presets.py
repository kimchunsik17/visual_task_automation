"""documents/format_presets.py — 프리셋 포맷 정본 로더.

정본은 저장소 루트 document_formats/*.json 이다(ADR-0005 방식 — workflow_patterns 과 동일).
로드 시점에 validate_format_spec 을 통과시킨다 — 프리셋이 스펙 규칙을 어기면 서버가
켜지지 않는 것이 맞다(조용히 깨진 프리셋을 노출하지 않는다).
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List

from .format_spec import validate_format_spec

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PRESETS_DIR = REPO_ROOT / "document_formats"


def _load() -> List[Dict[str, Any]]:
    presets = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        normalized = validate_format_spec(spec)
        if not normalized.get("id"):
            raise ValueError(f"프리셋 {path.name} 에 id 가 없습니다.")
        presets.append(normalized)
    return presets


PRESETS: List[Dict[str, Any]] = _load()
PRESETS_BY_ID: Dict[str, Dict[str, Any]] = {p["id"]: p for p in PRESETS}


def payload() -> Dict[str, Any]:
    """프론트엔드 번들(export_node_definitions.py)용."""
    return {"version": 1, "formats": PRESETS}
