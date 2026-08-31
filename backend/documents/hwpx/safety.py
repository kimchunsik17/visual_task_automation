"""documents/hwpx/safety.py — 남이 준 HWPX 를 열어도 되는지 (한국형 노드 계획 §3.3).

HWPX 는 ZIP 안에 XML 이 든 포맷이다. 즉 **사용자가 올린 파일이 곧 압축 폭탄이자 XML 폭탄이
될 수 있고**, entry 이름은 경로 탈출 수단이 될 수 있다. 예전 구현에는 이 방어가 하나도 없었다 —
`zipfile.ZipFile(path)` 를 그냥 열고 `zf.read(name)` 을 했다.

여기서 막는 것과 그 이유:

  entry 수·해제 크기·압축비   1KB 짜리 파일이 수 GB 로 풀리면 워커가 죽는다
  절대경로·`..`·중복 이름     압축을 푸는 코드가 생기면 그대로 경로 탈출이 된다
  symlink                    푸는 순간 서버 파일을 가리키는 링크가 생긴다
  DOCTYPE/ENTITY             중첩 entity 하나로 파서가 메모리를 다 쓴다(billion laughs)
  필수 entry                  mimetype 이 없으면 애초에 HWPX 가 아니다

**압축을 풀지 않아도 검사한다.** 이 계층을 지나기 전에는 어떤 entry 도 읽지 않는다.
"""

from __future__ import annotations

import re
import zipfile
from typing import List, Optional

# 실제 문서 기준으로 넉넉히 잡되, 워커를 죽일 수 없는 선.
MAX_ENTRIES = 512
MAX_ENTRY_BYTES = 64 * 1024 * 1024        # 개별 entry 해제 크기
MAX_TOTAL_BYTES = 256 * 1024 * 1024       # 전체 해제 크기
MAX_COMPRESSION_RATIO = 200               # 해제/압축 비율
MAX_XML_BYTES = 32 * 1024 * 1024

# HWPX 는 OCF 계열이라 mimetype 이 반드시 있다. 없으면 확장자만 .hwpx 인 다른 파일이다.
REQUIRED_ENTRIES = ("mimetype",)
EXPECTED_MIMETYPE = b"application/hwp+zip"

_DOCTYPE_RE = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


class PackageRejected(ValueError):
    """열지 않기로 했다. 메시지는 사용자에게 그대로 보여도 되는 수준으로 쓴다."""

    def __init__(self, message: str, *, reason: str):
        super().__init__(message)
        self.reason = reason


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    # 상위 16비트가 유닉스 모드. S_IFLNK == 0xA000.
    return (info.external_attr >> 16) & 0xF000 == 0xA000


def check_archive(zf: zipfile.ZipFile) -> None:
    """entry 목록만 보고 판단한다. 여기서 통과해야 read() 를 부를 수 있다."""
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise PackageRejected(
            f"문서 안의 항목이 너무 많습니다({len(infos)}개, 상한 {MAX_ENTRIES}개).",
            reason="TOO_MANY_ENTRIES",
        )

    seen: set = set()
    total = 0
    for info in infos:
        name = info.filename

        if name in seen:
            raise PackageRejected(f"같은 이름의 항목이 두 번 있습니다: {name}", reason="DUPLICATE_ENTRY")
        seen.add(name)

        if name.startswith("/") or name.startswith("\\") or ":" in name.split("/")[0][1:2]:
            raise PackageRejected(f"절대 경로 항목은 열지 않습니다: {name}", reason="ABSOLUTE_PATH")
        if ".." in name.replace("\\", "/").split("/"):
            raise PackageRejected(f"상위 경로를 가리키는 항목은 열지 않습니다: {name}", reason="PATH_TRAVERSAL")
        if _is_symlink(info):
            raise PackageRejected(f"링크 항목은 열지 않습니다: {name}", reason="SYMLINK")

        if info.file_size > MAX_ENTRY_BYTES:
            raise PackageRejected(
                f"문서 안의 항목이 너무 큽니다: {name}", reason="ENTRY_TOO_LARGE")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise PackageRejected("문서를 풀었을 때의 크기가 너무 큽니다.", reason="TOTAL_TOO_LARGE")

        # 압축비는 개별 entry 로 본다 — 전체 평균으로 보면 큰 정상 파일 하나에 폭탄이 숨는다.
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise PackageRejected(
                f"비정상적으로 높은 압축률의 항목이 있습니다: {name}", reason="COMPRESSION_BOMB")

    missing = [n for n in REQUIRED_ENTRIES if n not in seen]
    if missing:
        raise PackageRejected(
            f"HWPX 문서가 아닙니다. 필수 항목이 없습니다: {', '.join(missing)}",
            reason="NOT_HWPX",
        )


def check_mimetype(raw: bytes) -> None:
    """mimetype entry 의 내용. 확장자만 바꾼 다른 ZIP 을 걸러낸다."""
    if raw.strip() != EXPECTED_MIMETYPE:
        raise PackageRejected(
            "HWPX 문서가 아닙니다(mimetype 이 다릅니다).", reason="BAD_MIMETYPE")


def check_xml(raw: bytes, *, name: str) -> None:
    """XML 을 파싱하기 **전에** 본다. 파싱을 시작하면 이미 늦는다."""
    if len(raw) > MAX_XML_BYTES:
        raise PackageRejected(f"문서의 XML 이 너무 큽니다: {name}", reason="XML_TOO_LARGE")
    if _DOCTYPE_RE.search(raw):
        # 외부 entity 로 서버 파일을 읽거나, 중첩 entity 로 메모리를 태울 수 있다.
        raise PackageRejected(
            f"허용하지 않는 XML 선언이 있습니다: {name}", reason="XML_DOCTYPE")


def safe_entry_names(zf: zipfile.ZipFile, *, prefix: str = "", suffix: str = "") -> List[str]:
    """검사를 통과한 아카이브에서 조건에 맞는 entry 이름들. 순서는 원본 그대로."""
    return [i.filename for i in zf.infolist()
            if i.filename.startswith(prefix) and i.filename.endswith(suffix)]
