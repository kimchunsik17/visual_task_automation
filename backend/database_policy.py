"""database_policy.py — Database Query 가 어디로, 어떻게 접속할 수 있는지 (ADR-0017, DB-1.4).

사용자가 API 센터에 넣은 접속 문자열을 서버가 그대로 열면 두 가지가 위험하다.

1. **로컬 파일**: `sqlite:////etc/passwd` 같은 URI 는 서버 파일을 읽는다. sqlite 는 로컬·테스트
   fixture 용이므로 `DATABASE_QUERY_ALLOW_SQLITE=1` 일 때만 연다.
2. **내부 네트워크**: `postgresql://…@169.254.169.254/` 나 `@localhost:5432/` 는 서버가 대신
   내부 주소에 접속하는 SSRF 다. loopback·link-local(클라우드 metadata 포함)·unspecified·multicast·
   reserved 주소는 항상 막고, private CIDR 은 self-host 운영자가 `DATABASE_QUERY_ALLOW_PRIVATE_HOSTS=1`
   로 명시적으로 허용할 때만 연다. DNS 를 먼저 풀어 그 주소를 검사하고, 접속은 검사한 주소
   (`hostaddr`)로 고정한다 — 검사 뒤 DNS 가 바뀌는 rebinding 을 막는다.

MVP 지원 DB 는 PostgreSQL 하나다. MySQL 은 드라이버·통합 테스트가 갖춰지기 전까지
DATABASE_DRIVER_MISSING 으로 끝난다(§4.9 범위 원칙).
"""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SUPPORTED_DIALECTS = ["postgresql"]
_POSTGRES_DRIVERS = {"postgresql", "postgresql+psycopg2", "postgresql+psycopg", "postgres"}
DEFAULT_SSLMODE = "require"


class PolicyViolation(Exception):
    """접속 정책 위반. code 는 catalog 의 오류 code, safe_details 는 그 code 의 허용 key 안에서."""

    def __init__(self, code: str, message: str, *, safe_details: Optional[Dict[str, Any]] = None, field: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.safe_details = safe_details or {}
        self.field = field


@dataclass
class ConnectSpec:
    url: str
    dialect: str
    connect_args: Dict[str, Any] = field(default_factory=dict)
    host: Optional[str] = None
    port: Optional[int] = None
    resolved_ip: Optional[str] = None
    database: Optional[str] = None


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def allow_sqlite() -> bool:
    return _flag("DATABASE_QUERY_ALLOW_SQLITE")


def allow_private_hosts() -> bool:
    return _flag("DATABASE_QUERY_ALLOW_PRIVATE_HOSTS")


def default_sslmode() -> str:
    return os.getenv("DATABASE_QUERY_DEFAULT_SSLMODE", DEFAULT_SSLMODE).strip() or DEFAULT_SSLMODE


def classify_address(ip_text: str) -> Optional[str]:
    """차단 사유 또는 None(허용). private 는 허용 플래그가 없을 때만 사유가 된다."""
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return "unresolvable"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"      # 169.254.169.254 클라우드 metadata 포함
    if ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return "reserved"
    if ip.is_private and not allow_private_hosts():
        return "private"
    return None


def resolve_host(host: str, port: int) -> List[str]:
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return []
    seen: List[str] = []
    for info in infos:
        address = info[4][0]
        if address not in seen:
            seen.append(address)
    return seen


def prepare_connection(connection_string: str, *, timeout_seconds: int = 10) -> ConnectSpec:
    """접속 문자열을 검사해 실제로 열 수 있는 사양을 돌려준다. 위반은 PolicyViolation."""
    from sqlalchemy.engine import make_url

    try:
        url = make_url(connection_string)
    except Exception:
        raise PolicyViolation("CREDENTIAL_INVALID", "접속 문자열 형식이 올바르지 않습니다. API 센터의 Database 자격증명을 확인해주세요.",
                              safe_details={"provider": "database", "service": "Database"})
    driver = (url.drivername or "").lower()
    backend = url.get_backend_name()

    if backend == "sqlite":
        if not allow_sqlite():
            raise PolicyViolation("DATABASE_DRIVER_MISSING",
                                  "SQLite 는 이 서버에서 조회 대상으로 허용되지 않습니다. PostgreSQL 접속 문자열을 등록해주세요.",
                                  safe_details={"dialect": "sqlite", "supportedDialects": SUPPORTED_DIALECTS})
        return ConnectSpec(url=connection_string, dialect="sqlite", connect_args={"timeout": timeout_seconds}, database=url.database)

    if driver not in _POSTGRES_DRIVERS:
        raise PolicyViolation("DATABASE_DRIVER_MISSING",
                              f"'{backend}' 데이터베이스는 아직 지원하지 않습니다. 현재는 PostgreSQL 만 조회할 수 있습니다.",
                              safe_details={"dialect": backend, "supportedDialects": SUPPORTED_DIALECTS})

    host = url.host
    port = int(url.port or 5432)
    if not host:
        raise PolicyViolation("CREDENTIAL_INVALID", "접속 문자열에 호스트가 없습니다. API 센터의 Database 자격증명을 확인해주세요.",
                              safe_details={"provider": "database", "service": "Database"})
    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise PolicyViolation("DATABASE_CONNECTION_FAILED", "서버 자신(localhost)으로의 접속은 허용되지 않습니다.",
                              safe_details={"dialect": "postgresql", "phase": "egress_policy"})

    addresses = resolve_host(host, port)
    if not addresses:
        raise PolicyViolation("DATABASE_CONNECTION_FAILED", "데이터베이스 호스트 이름을 해석하지 못했습니다. 호스트 주소를 확인해주세요.",
                              safe_details={"dialect": "postgresql", "phase": "dns"})
    chosen: Optional[str] = None
    blocked_reason: Optional[str] = None
    for address in addresses:
        reason = classify_address(address)
        if reason is None:
            chosen = address
            break
        blocked_reason = blocked_reason or reason
    if chosen is None:
        if blocked_reason == "private":
            message = "내부 네트워크 주소로의 접속은 이 서버에서 허용되지 않습니다. 공개 주소를 쓰거나 운영자에게 DATABASE_QUERY_ALLOW_PRIVATE_HOSTS 설정을 요청하세요."
        else:
            message = "해당 주소로의 접속은 보안 정책상 허용되지 않습니다(loopback·link-local·metadata 주소)."
        raise PolicyViolation("DATABASE_CONNECTION_FAILED", message,
                              safe_details={"dialect": "postgresql", "phase": "egress_policy"})

    connect_args: Dict[str, Any] = {"connect_timeout": timeout_seconds, "hostaddr": chosen}
    query = dict(url.query or {})
    if "sslmode" not in {k.lower() for k in query}:
        connect_args["sslmode"] = default_sslmode()
    return ConnectSpec(url=connection_string, dialect="postgresql", connect_args=connect_args,
                       host=host, port=port, resolved_ip=chosen, database=url.database)


def describe(connection_string: str) -> Dict[str, Any]:
    """비밀 없이 보여줄 수 있는 요약(dialect·host·database). 목록 UI 와 telemetry 용."""
    from sqlalchemy.engine import make_url

    try:
        url = make_url(connection_string)
    except Exception:
        return {"dialect": None, "host": None, "database": None, "valid": False}
    return {
        "dialect": url.get_backend_name(),
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "username": url.username,
        "valid": True,
    }
