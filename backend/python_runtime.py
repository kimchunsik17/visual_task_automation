"""python_runtime.py — pythonNode 의 격리 실행기 (§4.15 PYEXEC-1, 우선 백로그 25).

`workflow_security` 의 허용 목록은 사용자 코드가 **무엇에 닿는지**를 문법 수준에서 통제한다
(import·함수 정의·속성 접근 금지). 그러나 **얼마나 쓰는지**는 보지 않았고, 실행 경로 어디에도
시간·메모리 제한이 없었다 — `output_data = 10 ** 10 ** 10` 한 줄이면 워커가 멈췄다.

이 모듈이 그 자리를 채운다. 사용자 코드는 더 이상 생성 워크플로우 소스에 인라인되지 않고,
`python_sandbox.py` 자식 프로세스에서 rlimit 아래 돈다:

  - `RLIMIT_CPU` / `RLIMIT_AS`  커널이 강제하는 CPU·메모리 상한
  - wall timeout               응답하지 않는 자식을 부모가 끊는다
  - `env` 최소화, 빈 `cwd`      자격증명·경로가 자식에게 넘어가지 않는다

부수 효과가 하나 더 있다 — 예전에는 DB 세션이 있는 네임스페이스 바로 옆에서 사용자 코드가
실행됐다. 허용 목록 한 줄이 느슨해지면 방어가 없었다. 이제 방어가 두 겹이다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from node_errors import NodeResult, make_error

SANDBOX_PATH = Path(__file__).resolve().parent / "python_sandbox.py"

DEFAULT_CPU_SECONDS = 1
DEFAULT_ADDRESS_SPACE_BYTES = 256 * 1024 * 1024
DEFAULT_WALL_SECONDS = 2.0
DEFAULT_OUTPUT_BYTES = 256 * 1024

# 자식에게 넘기는 환경변수. 비밀은 하나도 없고, 없으면 곤란한 것만 남긴다 —
# 바이트코드 캐시를 끄지 않으면 __pycache__ 쓰기를 시도하고, 인코딩을 고정하지 않으면
# 한글 출력이 환경에 따라 깨진다.
SANDBOX_ENV = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}


def isolation_enabled() -> bool:
    """`PYTHON_NODE_ISOLATION`(기본 켜짐). 끄면 예전처럼 생성 코드 안에서 직접 실행한다 —
    되돌리기용이며, 정적 상한(PYEXEC-0)과 허용 목록은 어느 쪽에서도 유지된다."""
    return os.getenv("PYTHON_NODE_ISOLATION", "1").strip().lower() not in {"0", "false", "off", "no"}


def node_enabled() -> bool:
    """`PYTHON_NODE_ENABLED`(기본 켜짐). 끄면 pythonNode 가 아예 실행되지 않는다.

    격리 스위치(`PYTHON_NODE_ISOLATION`)와는 층이 다르다. 그쪽은 "어떻게 실행할지"를 고르는
    되돌리기용 스위치라, 0 으로 내리면 격리 없는 인라인 실행이라는 **더 약한** 경로가 열린다.
    이건 "실행할지 말지"라서, 끄면 두 경로가 모두 닫힌다.

    끄는 이유는 주로 플랫폼이다 — `python_sandbox.py` 는 POSIX 전용 `resource` 모듈로 rlimit 을
    건다. Windows 개발 머신에서는 자식이 ImportError 로 즉사하고, 부모는 그 종료 코드를
    메모리 한도 초과로 오해해 엉뚱한 오류를 보여준다. 격리를 못 거는 환경이라면 인라인으로
    낮춰 실행하는 것보다 노드를 닫는 편이 맞다.
    """
    return os.getenv("PYTHON_NODE_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}


def disabled_error(node_id: Optional[str] = None):
    """pythonNode 가 꺼진 환경에서 돌려줄 NodeError. 실행 경로 두 곳이 같은 것을 쓴다."""
    return make_error(
        "RUNTIME_NODE_DISABLED", effect_state="not_started",
        safe_details={"nodeType": "pythonNode"},
        node_type="pythonNode", node_id=node_id,
        internal_message="PYTHON_NODE_ENABLED=0",
    )


def _positive(name: str, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = type(default)(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class IsolationLimits:
    cpu_seconds: int = DEFAULT_CPU_SECONDS
    address_space_bytes: int = DEFAULT_ADDRESS_SPACE_BYTES
    wall_seconds: float = DEFAULT_WALL_SECONDS
    output_bytes: int = DEFAULT_OUTPUT_BYTES

    @classmethod
    def from_env(cls) -> "IsolationLimits":
        return cls(
            cpu_seconds=_positive("PYTHON_NODE_CPU_SECONDS", DEFAULT_CPU_SECONDS),
            address_space_bytes=_positive("PYTHON_NODE_MEMORY_BYTES", DEFAULT_ADDRESS_SPACE_BYTES),
            wall_seconds=_positive("PYTHON_NODE_WALL_SECONDS", DEFAULT_WALL_SECONDS),
            output_bytes=_positive("PYTHON_NODE_OUTPUT_BYTES", DEFAULT_OUTPUT_BYTES),
        )

    def to_payload(self) -> dict:
        return {"cpuSeconds": self.cpu_seconds, "addressSpaceBytes": self.address_space_bytes}


_LIMIT_LABEL = {"cpu": "실행 시간", "memory": "메모리", "wall": "응답 시간"}


def _resource_error(kind: str, limits: IsolationLimits, node_id, internal=None):
    limit_value = {
        "cpu": f"{limits.cpu_seconds}s",
        "memory": f"{limits.address_space_bytes // (1024 * 1024)}MB",
        "wall": f"{limits.wall_seconds}s",
    }.get(kind, "")
    return make_error(
        "RUNTIME_RESOURCE_EXCEEDED", effect_state="not_started", field="code",
        user_message=(f"코드가 허용된 {_LIMIT_LABEL.get(kind, '자원')}({limit_value})을 넘어 중단했습니다. "
                      "처리량을 줄이거나 반복 범위를 좁혀주세요."),
        safe_details={"limitKind": kind, "limit": limit_value, "nodeType": "pythonNode"},
        node_type="pythonNode", node_id=node_id, internal_message=internal,
    )


def _decode_output(raw: str, limits: IsolationLimits, node_id):
    if len(raw.encode("utf-8")) > limits.output_bytes:
        return None, make_error(
            "RUNTIME_OUTPUT_TOO_LARGE", effect_state="not_started",
            safe_details={"sizeBytes": len(raw.encode("utf-8")), "limitBytes": limits.output_bytes},
            node_type="pythonNode", node_id=node_id,
        )
    try:
        return json.loads(raw), None
    except ValueError as exc:
        return None, make_error(
            "RUNTIME_SERIALIZATION_FAILED", effect_state="not_started",
            safe_details={"phase": "decode"}, node_type="pythonNode", node_id=node_id,
            internal_message=str(exc)[:300],
        )


def run_isolated(
    code: str,
    input_data: Any,
    *,
    node_id: Optional[str] = None,
    limits: Optional[IsolationLimits] = None,
) -> NodeResult:
    """사용자 코드를 격리 프로세스에서 돌린다. 예외를 올리지 않고 항상 `NodeResult` 를 돌려준다.

    실패해도 워크플로우를 죽이지 않는다 — 이 노드만 오류로 끝나고 하류는 계속된다.
    """
    # 생성 시점에 이미 걸러지지만(action_nodes.generate_python_node), 저장돼 있던 워크플로우가
    # 예전 생성 코드로 실행될 수 있으므로 실행기에서도 다시 막는다.
    if not node_enabled():
        return NodeResult.failure(disabled_error(node_id))

    limits = limits or IsolationLimits.from_env()
    # 입력은 JSON 으로 건너간다. 직렬화할 수 없는 값이 상류에서 오면 여기서 걸린다 —
    # 그 자체가 "input_data 는 순수 데이터"라는 불변식의 실행 시점 확인이다.
    try:
        payload = json.dumps(
            {"code": code, "input_data": input_data, "limits": limits.to_payload()},
            ensure_ascii=False, default=str,
        )
    except (TypeError, ValueError) as exc:
        return NodeResult.failure(make_error(
            "RUNTIME_SERIALIZATION_FAILED", effect_state="not_started",
            safe_details={"phase": "encode"}, node_type="pythonNode", node_id=node_id,
            internal_message=str(exc)[:300],
        ))

    # encoding 을 못박는 이유: text=True 만 쓰면 파이썬이 로케일 인코딩을 고른다. systemd 서비스는
    # 사용자 로케일을 물려받지 않아 LANG 이 없으면 ASCII 가 되고, 그러면 한글이 든 코드나 입력이
    # UnicodeEncodeError 로 죽는다 — 노드가 한글 때문에 실패하는 종류의 사고다.
    with tempfile.TemporaryDirectory(prefix="pynode-") as workdir:
        try:
            completed = subprocess.run(
                [sys.executable, str(SANDBOX_PATH)],
                input=payload, capture_output=True, text=True, encoding="utf-8",
                timeout=limits.wall_seconds, env=dict(SANDBOX_ENV), cwd=workdir,
            )
        except subprocess.TimeoutExpired:
            # subprocess.run 은 timeout 에서 자식을 죽이고 거둔다(좀비가 남지 않는다).
            return NodeResult.failure(_resource_error("wall", limits, node_id))
        except OSError as exc:
            return NodeResult.failure(make_error(
                "INTERNAL_UNKNOWN", effect_state="not_started", safe_details={"phase": "sandbox_spawn"},
                node_type="pythonNode", node_id=node_id, cause=exc,
            ))

    if completed.returncode != 0 or not completed.stdout.strip():
        # 커널이 하드 한도로 죽인 경우다. SIGKILL(-9)은 OOM killer 나 CPU hard limit,
        # SIGXCPU(-24)는 우리 핸들러가 응답하지 못한 경우다.
        kind = "cpu" if completed.returncode in (-24, -9) else "memory"
        return NodeResult.failure(_resource_error(
            kind, limits, node_id, internal=f"rc={completed.returncode} stderr={completed.stderr[:300]}"
        ))

    try:
        result = json.loads(completed.stdout)
    except ValueError as exc:
        return NodeResult.failure(make_error(
            "INTERNAL_UNKNOWN", effect_state="not_started", safe_details={"phase": "sandbox_protocol"},
            node_type="pythonNode", node_id=node_id, cause=exc,
        ))

    if not result.get("ok"):
        kind = result.get("kind")
        if kind in ("cpu", "memory"):
            return NodeResult.failure(_resource_error(kind, limits, node_id, internal=result.get("detail")))
        if kind == "serialization":
            return NodeResult.failure(make_error(
                "RUNTIME_SERIALIZATION_FAILED", effect_state="not_started",
                safe_details={"phase": "output"}, node_type="pythonNode", node_id=node_id,
                internal_message=result.get("errorType"),
            ))
        # 사용자 코드 자체의 오류. 예외 **종류와 줄**만 공개하고 메시지는 내부 기록으로 보낸다 —
        # 메시지에는 처리 중이던 데이터가 그대로 섞여 있을 수 있다.
        return NodeResult.failure(make_error(
            "RUNTIME_USER_CODE_FAILED", effect_state="not_started", field="code",
            safe_details={"nodeType": "pythonNode", "errorType": result.get("errorType"),
                          "line": result.get("line")},
            node_type="pythonNode", node_id=node_id, internal_message=result.get("message"),
        ))

    output, error = _decode_output(result.get("output") or "null", limits, node_id)
    if error is not None:
        return NodeResult.failure(error)
    return NodeResult.success(output, metrics=result.get("metrics") or {})
