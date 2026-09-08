"""시연 플래그의 런타임 오버라이드 — .env 를 고치고 재기동하지 않아도 어드민 패널에서 바로 바꾼다.

저장은 `backend/demo_runtime_settings.json` 한 파일이다(서비스는 단일 프로세스). 키가 파일에 있으면 그 값,
없으면 환경변수(.env) 값을 쓴다 — 파일을 지우면 예전 동작으로 완전히 돌아간다. DB 표를 두지 않은 이유:
시연 전날에 마이그레이션을 얹지 않기 위해서다(AUTO_MIGRATE_ON_BOOT=0 이라 스키마가 어긋나면 기동을 거부한다).
시연 뒤 DB 로 옮기면 된다 — 읽는 쪽은 전부 이 모듈을 거치므로 저장소만 바꾸면 된다.

읽는 곳: /api/features(demo_ui·demo_guest), auth_guest(DEMO_GUEST·토큰·정원), hidden_nodes(HIDDEN_NODE_TYPES).
DEMO_SHARED_CREDENTIALS_*·DEMO_LOGIN_* 은 자주 바꿀 일이 없어 .env 그대로 둔다.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
from typing import Any, Dict, Optional

PATH = pathlib.Path(os.getenv("DEMO_RUNTIME_SETTINGS_PATH")
                    or (pathlib.Path(__file__).resolve().parent / "demo_runtime_settings.json"))

# key → (형, 기본값). 기본값은 .env 에도 없을 때 쓰인다(예전 호출부의 기본값과 같다).
KEYS: Dict[str, tuple] = {
    "DEMO_UI": ("bool", False),
    "DEMO_GUEST": ("bool", False),
    "DEMO_GUEST_TOKENS": ("int", 50000),
    "DEMO_GUEST_MAX": ("int", 300),
    "HIDDEN_NODE_TYPES": ("list", []),
}
LIMITS = {"DEMO_GUEST_TOKENS": (1000, 2_000_000), "DEMO_GUEST_MAX": (1, 5000)}
_lock = threading.Lock()


def _read() -> Dict[str, Any]:
    try:
        raw = json.loads(PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: Dict[str, Any]) -> None:
    tmp = PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, PATH)


def _normalize(key: str, value: Any) -> Any:
    kind, _default = KEYS[key]
    if kind == "bool":
        if isinstance(value, str):
            return value.strip().lower() not in {"", "0", "false", "off", "no"}
        return bool(value)
    if kind == "int":
        number = int(value)
        low, high = LIMITS[key]
        if not (low <= number <= high):
            raise ValueError(f"{key} 는 {low:,}~{high:,} 사이여야 합니다.")
        return number
    if isinstance(value, str):
        value = value.split(",")
    items = []
    for item in value or []:
        text = str(item).strip()
        if text and text not in items:
            items.append(text)
    return items


def env_value(key: str) -> Any:
    """환경변수만 본 값. 예전 호출부와 같은 해석 — bool 은 '값이 있으면 켜짐'(bool(os.getenv(...)))."""
    kind, default = KEYS[key]
    raw = os.getenv(key)
    if raw is None or (kind != "bool" and not raw.strip()):
        return default
    if kind == "bool":
        return bool(raw)
    try:
        return _normalize(key, raw)
    except ValueError:
        return default


def overrides() -> Dict[str, Any]:
    return {k: v for k, v in _read().items() if k in KEYS}


def effective(key: str) -> Any:
    ov = overrides()
    return ov[key] if key in ov else env_value(key)


def get_bool(key: str) -> bool:
    return bool(effective(key))


def get_int(key: str, default: Optional[int] = None) -> int:
    value = effective(key)
    return int(value if value is not None else (default if default is not None else KEYS[key][1]))


def get_list(key: str) -> list:
    return list(effective(key) or [])


def snapshot() -> Dict[str, Any]:
    return {
        "effective": {k: effective(k) for k in KEYS},
        "overrides": overrides(),
        "env": {k: env_value(k) for k in KEYS},
        "path": str(PATH),
    }


def update(patch: Dict[str, Any]) -> Dict[str, Any]:
    """patch 의 값이 None 이면 그 키의 오버라이드를 지운다(= .env 로 복귀). 모르는 키는 거부."""
    unknown = sorted(set(patch) - set(KEYS))
    if unknown:
        raise ValueError(f"모르는 설정: {', '.join(unknown)}")
    with _lock:
        data = _read()
        for key, value in patch.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = _normalize(key, value)
        _write(data)
    return snapshot()
