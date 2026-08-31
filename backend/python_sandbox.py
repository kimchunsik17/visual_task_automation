"""python_sandbox.py — pythonNode 본문을 실행하는 자식 프로세스 (§4.15 PYEXEC-1).

**이 파일은 서버 프로세스에서 import 하지 않는다.** 부모(`python_runtime.run_isolated`)가
별도 프로세스로 띄우고 stdin/stdout 으로 JSON 만 주고받는다. 그래야 자원 한도를 걸 수 있고,
사용자 코드가 DB 세션·자격증명이 있는 네임스페이스에서 완전히 분리된다.

■ 왜 프로세스를 나누는가
  `workflow_security` 의 허용 목록이 이미 import·함수 정의·속성 접근을 막아서 사용자 코드는
  `input_data` 를 받아 `output_data` 를 내는 **순수 함수**다. 공유 상태가 없으니 프로세스 밖으로
  옮기는 비용이 거의 없고, 대신 시간·메모리 한도를 커널에 맡길 수 있다.

■ 한도를 언제 거는가
  import 를 마친 **뒤에** 건다. 먼저 걸면 인터프리터 자기 초기화가 한도에 걸려 죽는다.
"""

from __future__ import annotations

import json
import resource
import signal
import sys


class CpuLimitReached(Exception):
    """RLIMIT_CPU 의 soft limit 에서 오는 SIGXCPU. 하드 한도로 죽기 전에 깔끔히 보고한다."""


def _on_sigxcpu(signum, frame):
    raise CpuLimitReached()


def _apply_limits(limits: dict) -> None:
    cpu_seconds = int(limits["cpuSeconds"])
    address_space = int(limits["addressSpaceBytes"])
    # soft 는 CPU 초, hard 는 +1 초 — soft 에서 SIGXCPU 를 받아 스스로 보고하고, 그 사이 응답하지
    # 못하면(C 레벨 타이트 루프) hard 에서 커널이 죽인다. 그때는 부모가 종료 코드로 판단한다.
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))
    signal.signal(signal.SIGXCPU, _on_sigxcpu)


def _safe_builtins() -> dict:
    """허용 목록과 **같은** 이름만 남긴다. 검증기와 두 벌이 되면 한쪽만 느슨해진다."""
    from workflow_security import SAFE_BUILTINS

    import builtins

    return {name: getattr(builtins, name) for name in sorted(SAFE_BUILTINS) if hasattr(builtins, name)}


def _jsonable(value):
    """JSON 으로 낼 수 있는 모양으로 정규화한다. set 은 순서가 없어 정렬한다."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=repr)]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    raise TypeError(f"{type(value).__name__} is not serializable")


def _fail(kind: str, **extra) -> int:
    json.dump({"ok": False, "kind": kind, **extra}, sys.stdout)
    return 0


def main() -> int:
    payload = json.load(sys.stdin)
    code = payload["code"]
    namespace = {
        "__builtins__": _safe_builtins(),
        "input_data": payload.get("input_data"),
        "output_data": payload.get("input_data"),   # 기본값 — 코드가 안 바꾸면 그대로 흘린다
    }
    _apply_limits(payload["limits"])

    try:
        exec(compile(code, "<pythonNode>", "exec"), namespace)
    except CpuLimitReached:
        return _fail("cpu")
    except MemoryError:
        return _fail("memory")
    except RecursionError:
        return _fail("memory", detail="recursion")
    except BaseException as exc:  # 사용자 코드의 오류 — 종류와 줄만 보고한다
        line = None
        traceback = exc.__traceback__
        while traceback is not None:
            if traceback.tb_frame.f_code.co_filename == "<pythonNode>":
                line = traceback.tb_lineno
            traceback = traceback.tb_next
        return _fail("user_code", errorType=type(exc).__name__, line=line, message=str(exc)[:500])

    try:
        output = json.dumps(_jsonable(namespace.get("output_data")), ensure_ascii=False)
    except (TypeError, ValueError, RecursionError) as exc:
        return _fail("serialization", errorType=type(exc).__name__)

    usage = resource.getrusage(resource.RUSAGE_SELF)
    json.dump({
        "ok": True,
        "output": output,
        "metrics": {
            "cpuMs": int((usage.ru_utime + usage.ru_stime) * 1000),
            # ru_maxrss 는 리눅스에서 KB 단위다.
            "peakRssBytes": int(usage.ru_maxrss) * 1024,
        },
    }, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
