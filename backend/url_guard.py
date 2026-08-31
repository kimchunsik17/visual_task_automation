"""url_guard.py — 워크플로우가 여는 바깥 URL의 안전 검사 (한국형 노드 계획 §6.5 선택지 A).

배경: `webCrawlerNode` 는 `requests.get(url)` 한 줄이었다. 검증이 placeholder 비교뿐이라

  1. `data.url` 이 비면 **직전 노드 출력을 그대로 URL 로 썼다.** LLM 이 만든 문자열이 곧 요청
     대상이 된다는 뜻이고, 그게 `http://169.254.169.254/...` 나 `http://localhost:8000/admin`
     이면 서버 내부를 긁어 사용자에게 돌려준다(SSRF).
  2. 응답 크기·시간 상한이 없어 큰 파일 하나로 워커를 오래 붙잡을 수 있었다.
  3. 커뮤니티 전용 Trigger 를 카탈로그에서 감춰도 이 노드로 같은 수집이 가능했다 —
     즉 "제휴 없는 커뮤니티 수집을 하지 않는다"는 비목표가 문서에만 있었다.

그래서 요청을 보내기 **전에** 여기서 한 번 거른다.

방어의 순서는 scheme → DNS 해석 → 해석된 IP → 리다이렉트 매 홉 재검증이다. 호스트 이름만 보고
막으면 `http://[내부IP]` 나 DNS 로 사설 IP 를 가리키는 공개 도메인을 놓친다. 그래서 **이름이 아니라
해석 결과**를 본다.

■ 안전 다음에는 예의다 (2026-08-30)

SSRF 를 막는 것과 "상대 서버에 폐를 끼치지 않는 것" 은 다른 문제다. 뒤쪽을 위해 세 가지를 더 한다.

  robots.txt   사이트가 "여기는 읽지 말라" 고 밝힌 경로를 존중한다. RFC 9309 를 따른다.
  최소 간격     같은 호스트에 연달아 때리지 않는다. robots 의 Crawl-delay 가 더 크면 그쪽을 쓴다.
  일일 상한     호스트당 하루 요청 수를 센다. 아카라이브 규정 8번의 "서버에 부하를 주는" 을
               우리가 먼저 막는 장치다(계획 §6.5).

일일 상한은 `rate_limit` 을 쓰므로 DB 에 남고 워커 수와 재시작에 영향받지 않는다. 최소 간격은
프로세스 안의 값이라 워커를 늘리면 그만큼 느슨해진다 — 둘 중 **총량을 지키는 쪽이 DB** 에 있다.

남는 한계 하나: 검사 시점과 접속 시점 사이에 DNS 응답이 바뀌는 rebinding 은 이 방식으로 완전히
막지 못한다. A/AAAA 레코드를 **전부** 확인해서(하나라도 사설이면 거부) 단순한 형태는 걸러내지만,
완전한 차단은 해석한 IP 로 직접 접속하고 Host 헤더를 붙이는 방식이 필요하다. 현재 위협 모델
(LLM·사용자가 만든 URL)에서는 과한 복잡도라 판단해 여기까지 한다.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
import urllib.robotparser
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_BYTES = 5 * 1024 * 1024      # 본문 5MB 상한
MAX_REDIRECTS = 5

# 상대 서버가 우리를 식별하고 차단할 수 있어야 한다. 브라우저인 척하지 않는다.
USER_AGENT = "WorkflowAI/1.0 (+https://wa-pnu.duckdns.org; workflow web crawler node)"

# 같은 호스트에 연달아 보내지 않는다. robots 의 Crawl-delay 가 더 크면 그 값을 쓴다.
MIN_HOST_INTERVAL = 1.0
MAX_HOST_INTERVAL = 30.0                 # Crawl-delay 가 터무니없이 크면 기다리지 말고 거부한다
ROBOTS_TTL = 3600.0                      # robots.txt 를 매번 받지 않는다
ROBOTS_MAX_BYTES = 512 * 1024

_last_request: Dict[str, float] = {}
_robots_cache: Dict[str, Tuple[float, Optional[urllib.robotparser.RobotFileParser], bool]] = {}
_lock = threading.Lock()

# 공식 feed/API 또는 서면 제휴가 확인되기 전에는 자동 수집하지 않기로 한 곳들.
# (한국형 서비스 노드 계획 §6.5, §11 비목표) 전용 Trigger 를 감추는 것만으로는 부족해서
# 범용 크롤러 경로에서도 같이 막는다. 제휴가 확정되면 이 목록에서 빼고 전용 connector 를 쓴다.
PARTNERSHIP_REQUIRED_HOSTS = {
    "dcinside.com",
    "fmkorea.com",
}


class UrlBlocked(ValueError):
    """요청을 보내지 않고 거부했다. 메시지는 사용자에게 그대로 보여도 되는 수준으로 쓴다."""

    def __init__(self, message: str, *, reason: str):
        super().__init__(message)
        self.reason = reason


def _registrable_suffixes(host: str) -> List[str]:
    """`gall.dcinside.com` → ['gall.dcinside.com', 'dcinside.com', 'com'] 순으로 돌려준다."""
    parts = host.split(".")
    return [".".join(parts[i:]) for i in range(len(parts))]


def requires_partnership(host: str) -> bool:
    """이 호스트가 서면 제휴/공식 경로 확인 대상인가.

    connector 정의 검증(`ConnectorSpec.validate_against_registry`)이 이 판정을 그대로 쓴다 —
    "크롤러에서는 막는데 전용 connector 로는 그냥 나간다" 가 되지 않게 한 곳에서 정한다.
    """
    return any(suffix in PARTNERSHIP_REQUIRED_HOSTS for suffix in _registrable_suffixes(host.lower()))


def _check_partnership(host: str) -> None:
    for suffix in _registrable_suffixes(host):
        if suffix in PARTNERSHIP_REQUIRED_HOSTS:
            raise UrlBlocked(
                f"'{suffix}' 는 공식 API·RSS 또는 서면 제휴가 확인되기 전까지 자동 수집하지 않습니다. "
                "공식 RSS 를 제공하는 사이트라면 RSS 트리거 노드를 사용해주세요.",
                reason="COMMUNITY_PARTNERSHIP_REQUIRED",
            )


def _resolve(host: str) -> List[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UrlBlocked(f"주소를 찾을 수 없습니다: {host}", reason="DNS_FAILED") from exc
    return sorted({info[4][0] for info in infos})


def _check_ip(ip_text: str, host: str) -> None:
    ip = ipaddress.ip_address(ip_text)
    # is_global 하나로 사설·루프백·링크로컬(169.254.169.254 메타데이터 포함)·멀티캐스트·예약
    # 대역이 모두 걸린다. 개별 대역을 나열하면 IPv6 매핑 주소 같은 걸 빠뜨리기 쉽다.
    if not ip.is_global or ip.is_multicast:
        raise UrlBlocked(
            f"내부 주소로는 요청할 수 없습니다: {host} → {ip_text}",
            reason="PRIVATE_ADDRESS",
        )


def check_url(url: str) -> Tuple[str, str]:
    """검사만 하고 (정규화된 url, host) 를 돌려준다. 막을 이유가 있으면 UrlBlocked."""
    url = (url or "").strip()
    if not url:
        raise UrlBlocked("주소가 비어 있습니다.", reason="EMPTY")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UrlBlocked(
            f"http/https 주소만 열 수 있습니다: {parsed.scheme or '(없음)'}",
            reason="BAD_SCHEME",
        )
    host = parsed.hostname
    if not host:
        raise UrlBlocked(f"주소에서 호스트를 찾을 수 없습니다: {url}", reason="NO_HOST")

    _check_partnership(host.lower())

    try:
        # 주소를 그대로 IP 로 쓴 경우(http://10.0.0.1/) 는 DNS 를 거치지 않으므로 먼저 본다.
        _check_ip(host, host)
    except ValueError as exc:
        if isinstance(exc, UrlBlocked):
            raise
        # 호스트 이름이라 IP 파싱에 실패한 것이다 — 해석해서 나온 주소를 전부 본다.
        for ip_text in _resolve(host):
            _check_ip(ip_text, host)

    return url, host


# ── 예의: robots.txt, 최소 간격, 일일 상한 ─────────────────────────────

def _robots_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))


def _fetch_robots(url: str, *, timeout: float):
    """robots.txt 를 받아 파서를 만든다. `(parser, allow_all)` 을 돌려준다.

    RFC 9309 를 따른다 — 4xx 는 "robots 가 없다"이므로 전부 허용, 5xx·네트워크 실패는
    "알 수 없다"이므로 전부 거부다. 뒤쪽을 허용으로 두면 사이트가 불안정할 때 우리가
    가장 세게 때리게 된다.
    """
    import requests

    try:
        resp = requests.get(_robots_url(url), timeout=timeout, allow_redirects=True,
                            headers={"User-Agent": USER_AGENT})
    except Exception:
        return None, False
    if 400 <= resp.status_code < 500 and resp.status_code != 429:
        return None, True
    if resp.status_code >= 500 or resp.status_code == 429:
        return None, False

    parser = urllib.robotparser.RobotFileParser()
    parser.parse(resp.text[:ROBOTS_MAX_BYTES].splitlines())
    return parser, False


def robots_policy(url: str, *, timeout: float = DEFAULT_TIMEOUT):
    """`(허용인가, 이 호스트에 둘 최소 간격)`. 결과는 호스트 단위로 캐시한다."""
    parsed = urlparse(url)
    key = f"{parsed.scheme}://{parsed.netloc}"
    now = time.monotonic()

    with _lock:
        cached = _robots_cache.get(key)
        if cached and now - cached[0] < ROBOTS_TTL:
            _stamp, parser, allow_all = cached
        else:
            parser, allow_all = None, None

    if parser is None and allow_all is None:
        parser, allow_all = _fetch_robots(url, timeout=timeout)
        with _lock:
            _robots_cache[key] = (now, parser, allow_all)

    if parser is None:
        return bool(allow_all), MIN_HOST_INTERVAL

    allowed = parser.can_fetch(USER_AGENT, url)
    delay = parser.crawl_delay(USER_AGENT)
    interval = MIN_HOST_INTERVAL
    if delay is not None:
        try:
            interval = max(MIN_HOST_INTERVAL, float(delay))
        except (TypeError, ValueError):
            pass
    return allowed, interval


def _wait_for_turn(host: str, interval: float) -> None:
    """같은 호스트에 연달아 보내지 않는다. 필요한 만큼만 잔다."""
    if interval > MAX_HOST_INTERVAL:
        raise UrlBlocked(
            f"이 사이트가 요청 간 {interval:.0f}초를 요구합니다 — 자동 수집 대상으로 적절하지 않습니다.",
            reason="CRAWL_DELAY_TOO_LONG",
        )
    while True:
        with _lock:
            now = time.monotonic()
            last = _last_request.get(host)
            if last is None or now - last >= interval:
                _last_request[host] = now
                return
            remaining = interval - (now - last)
        time.sleep(min(remaining, interval))


def _spend_budget(db, host: str) -> None:
    """호스트당 하루 요청 수를 센다. 주체는 사용자가 아니라 **호스트**다.

    지키려는 것이 "이 사용자가 과하게 쓰지 않는 것" 이 아니라 "우리가 저 사이트에 주는
    총 부하" 라서다. 사용자별로 세면 사용자가 늘어날수록 상대 서버가 받는 양이 늘어난다.
    """
    if db is None:
        return
    import rate_limit

    try:
        rate_limit.enforce(db, f"host:{host}", "crawl.fetch")
    except rate_limit.RateLimited as exc:
        raise UrlBlocked(
            f"'{host}' 에 오늘 보낼 수 있는 요청({exc.limit}회)을 모두 썼습니다. "
            "상대 서버에 부담을 주지 않기 위한 제한입니다.",
            reason="HOST_DAILY_LIMIT",
        ) from None


def fetch_text(url: str, *, timeout: float = DEFAULT_TIMEOUT,
               max_bytes: int = DEFAULT_MAX_BYTES, respect_robots: bool = True,
               db=None) -> str:
    """검사를 통과한 URL 만 GET 해서 본문 텍스트를 돌려준다.

    리다이렉트는 requests 에 맡기지 않고 직접 따라간다 — 자동으로 따라가면 최종 목적지가
    검사를 안 거친 채 열린다(공개 도메인 → 내부 주소로 302 하는 고전적인 우회).

    `db` 를 주면 호스트당 일일 상한을 센다. 노드 생성 코드는 항상 준다 — 안 주면 상한이
    조용히 없어지므로, 그 사실을 `test_url_guard_politeness.py` 가 붙들고 있다.
    """
    import requests

    current = url
    for _ in range(MAX_REDIRECTS + 1):
        current, host = check_url(current)

        interval = MIN_HOST_INTERVAL
        if respect_robots:
            allowed, interval = robots_policy(current, timeout=timeout)
            if not allowed:
                raise UrlBlocked(
                    f"이 사이트의 robots.txt 가 해당 경로 수집을 허용하지 않습니다: {current}",
                    reason="ROBOTS_DISALLOWED",
                )
        # 예산을 먼저 쓰고 나서 기다린다 — 반대로 하면 상한에 걸릴 요청 때문에 잠들게 된다.
        _spend_budget(db, host)
        _wait_for_turn(host, interval)

        resp = requests.get(
            current, timeout=timeout, allow_redirects=False, stream=True,
            headers={"User-Agent": USER_AGENT,
                     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                     "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"},
        )
        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                raise UrlBlocked("리다이렉트 응답에 목적지가 없습니다.", reason="BAD_REDIRECT")
            current = requests.compat.urljoin(current, location)
            continue

        # 429·503 은 "지금은 그만" 이라는 뜻이다. 재시도하지 않고 사유를 그대로 알린다 —
        # 부하를 줄이자는 장치가 재시도로 부하를 늘리면 앞뒤가 안 맞는다.
        if resp.status_code in (429, 503):
            resp.close()
            raise UrlBlocked(
                f"사이트가 잠시 요청을 받지 않습니다(HTTP {resp.status_code}). 나중에 다시 시도해주세요.",
                reason="SITE_THROTTLED",
            )

        # Content-Length 를 믿지 않고 실제로 읽은 바이트로 자른다.
        chunks, total = [], 0
        for chunk in resp.iter_content(8192):
            total += len(chunk)
            if total > max_bytes:
                resp.close()
                raise UrlBlocked(
                    f"응답이 너무 큽니다(상한 {max_bytes // (1024 * 1024)}MB).",
                    reason="TOO_LARGE",
                )
            chunks.append(chunk)
        resp.close()
        body = b"".join(chunks)
        encoding = resp.encoding or resp.apparent_encoding or "utf-8"
        return body.decode(encoding, errors="replace")

    raise UrlBlocked(f"리다이렉트가 {MAX_REDIRECTS}회를 넘었습니다.", reason="TOO_MANY_REDIRECTS")


def reset_politeness_state() -> None:
    """테스트 전용. 프로세스에 남은 마지막 요청 시각과 robots 캐시를 지운다."""
    with _lock:
        _last_request.clear()
        _robots_cache.clear()
