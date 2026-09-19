"""connectors/services/http_check.py — httpCheckNode 실행부 (백로그 34 DEV-2 2차, ADR-0034).

웹사이트·API·인증서·DNS 를 **점검**하는 감시형 유틸이다. 점검 결과가 나쁜 것(503, 키워드 없음, 인증서 만료 임박)은 이 노드의
**실패가 아니라 결과**다 — 뒤의 조건 노드가 `ok`/`problems` 를 보고 알림을 보낸다. 노드 실패는 URL 이 막혔거나(SSRF 검사) 입력이
잘못된 경우뿐이고, `failOnProblem` 을 켠 경우에만 문제가 error 갈래로 간다(생성기가 HTTPCHECK_PROBLEM 으로 승격).

■ 상태는 connector_cursors 에
  "본문이 바뀌었나" 를 알려면 지난 값이 필요하다. 트리거 cursor 표(0017)를 그대로 쓴다 — 프로젝트·노드 단위로 격리되고 workspace 소유가
  따라온다. cursor = {version, contentHash, status, checkedAt, tlsDaysLeft}.

■ 인증서는 ssl 소켓으로
  외부 API 없이 `ssl.create_default_context()` 로 핸드셰이크만 하고 `getpeercert()` 를 읽는다 — 폐쇄망에서도 동작한다. DNS 는 표준
  라이브러리 `socket.getaddrinfo`(A/AAAA). CNAME·MX·TXT 는 dnspython 이 필요해 이번 범위 밖이다.

■ 목업
  HTTP 부분은 정의의 mock 시나리오가 재생한다. TLS·DNS 는 소켓을 열어야 해서 목업에서는 고정값(`mock: true`)을 돌려준다 — 흐름은
  끝까지 돌되 진짜 점검이 아니었다는 표시를 남긴다.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import socket
import ssl
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from ..errors import INVALID_REQUEST, NETWORK, SERVER_ERROR, TIMEOUT, ConnectorError
from ..session import ConnectorSession

SERVICE = "HTTP 점검"
MODES = ("all", "http", "tls", "dns")
METHODS = ("GET", "HEAD")
USER_AGENT = "Mozilla/5.0 (compatible; WorkflowAI-HttpCheck/1.0)"
CURSOR_VERSION = 1
DEFAULT_EXPECT = "200-399"
DEFAULT_TLS_WARN_DAYS = 14
MAX_BODY_HASH_CHARS = 5_000_000
ANY_STATUS = frozenset(range(100, 600))
# 소켓 점검(TLS·DNS)에 쓰는 시간. HTTP 는 정의의 timeoutSeconds 가 세션에 들어간다.
SOCKET_TIMEOUT = 10.0


def _guard(url: str) -> Tuple[str, str]:
    """SSRF 검사. 목업(네트워크를 타지 않음)에서는 건너뛴다 — http_request 와 같은 규칙."""
    from .. import mock_runtime

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if mock_runtime.current() is not None:
        return url, host
    import url_guard

    try:
        checked, host = url_guard.check_url(url)
    except url_guard.UrlBlocked as exc:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=str(exc)) from exc
    return checked, host.lower()


def _redirect_guard(response, *args: Any, **kwargs: Any):
    if response.is_redirect or response.is_permanent_redirect:
        location = response.headers.get("Location")
        if location:
            from urllib.parse import urljoin

            _guard(urljoin(response.url, location))
    return response


def parse_expect_status(spec: Any) -> frozenset:
    """'200' · '200-299' · '200,204,301' · '2xx' 를 상태 집합으로. 비면 기본(200-399)."""
    text = str(spec or "").strip() or DEFAULT_EXPECT
    allowed: set = set()
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        lowered = part.lower()
        if len(lowered) == 3 and lowered[0].isdigit() and lowered[1:] == "xx":
            hundred = int(lowered[0]) * 100
            allowed.update(range(hundred, hundred + 100))
        elif "-" in part:
            lo, _, hi = part.partition("-")
            if not (lo.isdigit() and hi.isdigit()):
                raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"기대 상태 코드 형식이 잘못됐다: {part!r}")
            allowed.update(range(int(lo), int(hi) + 1))
        elif part.isdigit():
            allowed.add(int(part))
        else:
            raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"기대 상태 코드 형식이 잘못됐다: {part!r}")
    if not allowed:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="기대 상태 코드가 비어 있다")
    return frozenset(allowed)


def _body_text(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, str):
        return body
    return json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)


def content_hash(text: str) -> str:
    return hashlib.sha256(text[:MAX_BODY_HASH_CHARS].encode("utf-8", "replace")).hexdigest()[:16]


def check_http(session: ConnectorSession, url: str, *, method: str = "GET", expect: frozenset = ANY_STATUS,
               keyword: str = "", guard_redirects: bool = True) -> Dict[str, Any]:
    """한 번 요청하고 상태·응답시간·본문 해시·키워드 여부를 돌려준다. 타임아웃·연결 실패는 결과(ok=false)다."""
    method = str(method or "GET").upper()
    if method not in METHODS:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"점검 메서드는 GET 또는 HEAD 여야 한다: {method!r}")
    kwargs: Dict[str, Any] = {"headers": {"User-Agent": USER_AGENT, "Accept": "*/*"}, "expected_status": set(ANY_STATUS)}
    if guard_redirects:
        kwargs["hooks"] = {"response": _redirect_guard}
    started = time.monotonic()
    try:
        response = session.request(method, url, **kwargs)
    except ConnectorError as exc:
        if exc.code in (TIMEOUT, NETWORK, SERVER_ERROR):
            return {"ok": False, "status": exc.status, "error": exc.code, "responseMs": int((time.monotonic() - started) * 1000),
                    "bytes": 0, "contentHash": "", "keywordFound": None}
        raise
    elapsed_ms = int((time.monotonic() - started) * 1000)
    text = _body_text(response.body)
    status_ok = response.status in expect
    keyword_found: Optional[bool] = (keyword in text) if keyword else None
    return {
        "ok": bool(status_ok and (keyword_found is not False)),
        "status": response.status,
        "statusOk": status_ok,
        "responseMs": elapsed_ms,
        "bytes": len(text.encode("utf-8", "replace")),
        "contentHash": content_hash(text),
        "keywordFound": keyword_found,
        "contentType": str((response.headers or {}).get("Content-Type") or (response.headers or {}).get("content-type") or ""),
    }


def _name_field(rdns: Any, key: str) -> str:
    for group in rdns or ():
        for pair in group:
            if isinstance(pair, (tuple, list)) and len(pair) == 2 and pair[0] == key:
                return str(pair[1])
    return ""


def tls_summary(cert: Dict[str, Any], *, now: Optional[datetime.datetime] = None, warn_days: int = DEFAULT_TLS_WARN_DAYS) -> Dict[str, Any]:
    """ssl.getpeercert() dict → 만료일·남은 일수·발급자. 소켓 없이 테스트할 수 있게 분리했다."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    not_after = str(cert.get("notAfter") or "")
    expires_at: Optional[datetime.datetime] = None
    if not_after:
        try:
            expires_at = datetime.datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), tz=datetime.timezone.utc)
        except (ValueError, TypeError):
            expires_at = None
    days_left: Optional[int] = None
    if expires_at is not None:
        days_left = int((expires_at - now).total_seconds() // 86400)
    sans = [value for kind, value in (cert.get("subjectAltName") or ()) if kind == "DNS"]
    ok = days_left is not None and days_left > int(warn_days)
    return {
        "ok": ok,
        "expiresAt": expires_at.isoformat() if expires_at else "",
        "daysLeft": days_left,
        "warnDays": int(warn_days),
        "issuer": _name_field(cert.get("issuer"), "organizationName") or _name_field(cert.get("issuer"), "commonName"),
        "subject": _name_field(cert.get("subject"), "commonName"),
        "altNames": sans[:20],
    }


def check_tls(host: str, *, port: int = 443, warn_days: int = DEFAULT_TLS_WARN_DAYS, timeout: float = SOCKET_TIMEOUT,
              now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """핸드셰이크만 하고 인증서를 읽는다. 검증 실패(만료·이름 불일치·자체 서명)도 결과로 남긴다 — 그것이 곧 점검 대상이다."""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert()
    except ssl.SSLCertVerificationError as exc:
        return {"ok": False, "error": "tls_verify_failed", "detail": str(exc.verify_message or exc)[:200], "daysLeft": None, "expiresAt": ""}
    except (ssl.SSLError, socket.timeout, OSError) as exc:
        return {"ok": False, "error": "tls_unreachable", "detail": str(exc)[:200], "daysLeft": None, "expiresAt": ""}
    summary = tls_summary(cert or {}, now=now, warn_days=warn_days)
    if summary["daysLeft"] is not None and summary["daysLeft"] < 0:
        summary["error"] = "tls_expired"
    elif not summary["ok"]:
        summary["error"] = "tls_expiring"
    return summary


def check_dns(host: str, *, record: str = "any") -> Dict[str, Any]:
    """A/AAAA 해석 결과. 표준 라이브러리만 쓴다(CNAME·MX·TXT 는 범위 밖)."""
    record = str(record or "any").upper()
    if record not in ("ANY", "A", "AAAA"):
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"DNS 레코드 종류는 any/A/AAAA 중 하나여야 한다: {record!r}")
    families = {"A": (socket.AF_INET,), "AAAA": (socket.AF_INET6,), "ANY": (socket.AF_INET, socket.AF_INET6)}[record]
    records: List[str] = []
    try:
        for family, _type, _proto, _canon, sockaddr in socket.getaddrinfo(host, None):
            if family in families and sockaddr and sockaddr[0] not in records:
                records.append(str(sockaddr[0]))
    except (socket.gaierror, UnicodeError) as exc:
        return {"ok": False, "record": record, "records": [], "error": "dns_unresolved", "detail": str(exc)[:200]}
    return {"ok": bool(records), "record": record, "records": records, **({} if records else {"error": "dns_unresolved"})}


def _mock_tls(warn_days: int) -> Dict[str, Any]:
    return {"ok": True, "mock": True, "expiresAt": "2027-12-31T00:00:00+00:00", "daysLeft": 400, "warnDays": int(warn_days),
            "issuer": "Mock CA", "subject": "example.com", "altNames": ["example.com"]}


def _mock_dns(record: str) -> Dict[str, Any]:
    return {"ok": True, "mock": True, "record": str(record or "any").upper(), "records": ["93.184.216.34"]}


def check(definition, *, url: str, mode: str = "all", method: str = "GET", expect_status: Any = DEFAULT_EXPECT, keyword: str = "",
          track_changes: bool = True, previous: Optional[Dict[str, Any]] = None, tls_warn_days: int = DEFAULT_TLS_WARN_DAYS,
          dns_record: str = "any", session: Optional[ConnectorSession] = None, now: Optional[datetime.datetime] = None,
          tls_checker=None, dns_checker=None) -> Dict[str, Any]:
    """점검 한 번. (결과 dict, 다음 cursor) 를 `result`·`result["cursor"]` 로 돌려준다.

    `tls_checker`/`dns_checker` 는 테스트용 주입점 — 기본은 실제 소켓, 목업 모드는 고정값.
    """
    from .. import mock_runtime

    mode = str(mode or "all").strip().lower()
    if mode not in MODES:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"점검 종류는 {', '.join(MODES)} 중 하나여야 한다: {mode!r}")
    url = str(url or "").strip()
    if not url:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="점검할 주소(url)가 비어 있다")
    if "://" not in url:
        url = "https://" + url
    url, host = _guard(url)
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    expect = parse_expect_status(expect_status)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    previous = dict(previous or {})
    mocking = mock_runtime.current() is not None
    try:
        warn_days = int(tls_warn_days) if tls_warn_days not in (None, "") else DEFAULT_TLS_WARN_DAYS
    except (TypeError, ValueError):
        warn_days = DEFAULT_TLS_WARN_DAYS

    result: Dict[str, Any] = {"url": url, "host": host, "mode": mode, "checkedAt": now.isoformat(), "problems": []}

    if mode in ("all", "http"):
        session = session or definition.new_session()
        http = check_http(session, url, method=method, expect=expect, keyword=keyword, guard_redirects=not mocking)
        result["http"] = http
        if http.get("error"):
            result["problems"].append("http_unreachable")
        else:
            if not http.get("statusOk"):
                result["problems"].append("http_status")
            if http.get("keywordFound") is False:
                result["problems"].append("http_keyword")
        current_hash = http.get("contentHash") or ""
        previous_hash = str(previous.get("contentHash") or "")
        result["previous"] = {k: previous.get(k) for k in ("contentHash", "status", "checkedAt") if k in previous}
        result["changed"] = bool(track_changes and previous_hash and current_hash and previous_hash != current_hash)
        result["statusChanged"] = bool(previous.get("status") is not None and http.get("status") is not None
                                       and previous.get("status") != http.get("status"))
        if track_changes:
            result["firstRun"] = not previous_hash
    if mode in ("all", "tls"):
        if parsed.scheme != "https" and mode == "all":
            result["tls"] = {"ok": True, "skipped": True, "reason": "http 주소는 인증서가 없다"}
        elif mocking:
            result["tls"] = _mock_tls(warn_days)
        else:
            checker = tls_checker or check_tls
            result["tls"] = checker(host, port=port if parsed.scheme == "https" else 443, warn_days=warn_days, now=now)
        if result["tls"].get("error"):
            result["problems"].append(result["tls"]["error"])
    if mode in ("all", "dns"):
        if mocking:
            result["dns"] = _mock_dns(dns_record)
        else:
            checker = dns_checker or check_dns
            result["dns"] = checker(host, record=dns_record)
        if result["dns"].get("error"):
            result["problems"].append(result["dns"]["error"])

    result["ok"] = not result["problems"]
    cursor: Dict[str, Any] = {"version": CURSOR_VERSION, "checkedAt": now.isoformat()}
    http_part = result.get("http") or {}
    if http_part.get("contentHash"):
        cursor["contentHash"] = http_part["contentHash"]
    elif previous.get("contentHash") and http_part.get("error"):
        cursor["contentHash"] = previous["contentHash"]     # 연결 실패 한 번으로 기준 해시를 잃지 않는다
    if http_part.get("status") is not None:
        cursor["status"] = http_part["status"]
    if (result.get("tls") or {}).get("daysLeft") is not None:
        cursor["tlsDaysLeft"] = result["tls"]["daysLeft"]
    result["cursor"] = cursor
    return result
