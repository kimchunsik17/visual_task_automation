"""documents/hwpx/package.py — HWPX 패키지를 안전하게 읽고, 원본 모양대로 다시 묶는다.

■ 왜 그냥 `zipfile` 을 쓰지 않는가

HWPX 는 OCF 계열 패키지라 `mimetype` 이 **첫 entry 이면서 무압축(STORED)** 이어야 한다. 예전
구현은 치환 후 전체를 `ZIP_DEFLATED` 로 다시 써서 그 규칙을 깼다(§2 불일치 4). 그래서 여기서는
원본의 `ZipInfo` 를 그대로 들고 다니며 순서·압축 방식·속성을 보존한다.

■ 입력 템플릿은 절대 건드리지 않는다

읽기는 읽기만 한다. 쓰기는 **항상 다른 경로**로 나간다. 예전에는 "필드 이름이 안 맞으면 다시
만든다"는 경로가 입력 템플릿 자체를 덮어써서 사용자가 올린 서식이 사라졌다(§2 불일치 3).
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from typing import Dict, List, Optional

from . import safety


class PackageWriteError(RuntimeError):
    pass


class HwpxPackage:
    """열린 HWPX 한 개. 내용은 메모리에 들고 있고, 저장은 새 경로로만 한다."""

    def __init__(self, entries: List[zipfile.ZipInfo], contents: Dict[str, bytes]):
        self._entries = entries
        self._contents = contents

    # ── 읽기 ────────────────────────────────────────────────────────────
    @classmethod
    def open(cls, path: str) -> "HwpxPackage":
        """검사를 통과한 패키지만 돌려준다. 통과 전에는 어떤 entry 도 읽지 않는다."""
        if not zipfile.is_zipfile(path):
            raise safety.PackageRejected(
                "HWPX 문서가 아닙니다(ZIP 형식이 아닙니다).", reason="NOT_ZIP")
        with zipfile.ZipFile(path, "r") as zf:
            safety.check_archive(zf)
            entries = list(zf.infolist())
            contents = {i.filename: zf.read(i.filename) for i in entries}
        safety.check_mimetype(contents["mimetype"])
        for name, raw in contents.items():
            if name.endswith(".xml") or name.endswith(".hpf") or name.endswith(".rdf"):
                safety.check_xml(raw, name=name)
        return cls(entries, contents)

    @property
    def names(self) -> List[str]:
        return [i.filename for i in self._entries]

    def read(self, name: str) -> bytes:
        return self._contents[name]

    def replace(self, name: str, raw: bytes) -> None:
        """entry 내용을 바꾼다. 새 entry 를 만들지는 않는다 — 패키지 구조는 그대로 둔다."""
        if name not in self._contents:
            raise KeyError(f"{name} 은 이 패키지에 없다")
        self._contents[name] = raw

    def section_names(self) -> List[str]:
        """본문 section XML 들. 이름 순이 아니라 **번호 순**이어야 문서 순서와 맞는다."""
        names = [n for n in self.names
                 if n.startswith("Contents/section") and n.endswith(".xml")]
        return sorted(names, key=_section_index)

    # ── 쓰기 ────────────────────────────────────────────────────────────
    def save_as(self, path: str) -> None:
        """새 경로로만 저장한다. 원본 entry 의 순서·압축 방식·속성을 그대로 보존한다."""
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)

        # 쓰다가 실패했을 때 반쯤 쓴 파일이 남으면 다음 실행이 그걸 정상 문서로 읽는다.
        handle, temp_path = tempfile.mkstemp(dir=directory, suffix=".hwpx.part")
        os.close(handle)
        try:
            with zipfile.ZipFile(temp_path, "w") as zout:
                for source in self._entries:
                    info = zipfile.ZipInfo(source.filename, date_time=source.date_time)
                    info.compress_type = source.compress_type
                    info.external_attr = source.external_attr
                    info.internal_attr = source.internal_attr
                    info.create_system = source.create_system
                    zout.writestr(info, self._contents[source.filename])
            _assert_mimetype_first_and_stored(temp_path)
            shutil.move(temp_path, path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise


def _section_index(name: str) -> int:
    digits = "".join(c for c in name.rsplit("/", 1)[-1] if c.isdigit())
    return int(digits) if digits else 0


def _assert_mimetype_first_and_stored(path: str) -> None:
    """저장 직후 스스로 확인한다 — 이 규칙이 깨진 파일을 내보내는 것이 예전의 버그였다."""
    with zipfile.ZipFile(path, "r") as zf:
        infos = zf.infolist()
    if not infos or infos[0].filename != "mimetype":
        raise PackageWriteError("mimetype 이 첫 항목이 아니다")
    if infos[0].compress_type != zipfile.ZIP_STORED:
        raise PackageWriteError("mimetype 이 압축됐다")
