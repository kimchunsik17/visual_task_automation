"""testdata/golden_hwpx.py — 한/글 호환성 확인용 대표 문서 10종 (계획 §3.4, §3.6).

■ 왜 스크립트인가

golden 문서를 한 번 만들어 저장소에 넣어 두면, 엔진을 고쳤을 때 **그 문서가 여전히 옳은지**
알 방법이 없다. 여기서는 스펙만 저장소에 두고 문서는 매번 만들어 낸다. 그러면

  - 엔진이 바뀌면 다시 만들어 한/글에서 열어 보면 되고,
  - 추출 결과가 달라지면 `test_golden_hwpx.py` 가 **바로 알려준다.**

■ 10종을 어떻게 골랐나

앞의 넷은 계획 §3.4 가 이름을 댄 실제 문서 종류(공문·계약서·표 중심 보고서·이미지 포함)다.
나머지 여섯은 **엔진에서 깨지기 쉬운 자리**를 하나씩 맡는다 — 쪽 나누기, 자리표시자,
XML 특수문자, 줄바꿈, 표 안 자리표시자, 그리고 분량.

■ 이 스크립트로 확인할 수 없는 것

한/글이 실제로 어떻게 그리는지는 여기서 알 수 없다(이 서버에 한/글이 없다). 그래서 결과물은
사람이 열어 볼 대상이고, 무엇을 봐야 하는지는 `CHECKLIST` 에 적었다.
"""

from __future__ import annotations

import base64
import json
import os
import zipfile
from typing import Any, Dict, List

# 1×1 이 아니라 눈에 보이는 크기의 PNG — "이미지가 들어갔는지" 를 사람이 봐야 하기 때문이다.
# 파란 바탕에 흰 사각형. 외부 파일에 의존하지 않도록 여기에 담아 둔다.
_SAMPLE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAIAAAD/gAIDAAAAWklEQVR4nO3QMQ0AAAgDsOHf9F0H"
    "SFrScNDZLQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAADgxwCPpAABAF2ZlQAAAABJRU5ErkJggg=="
)

_LOREM = (
    "이 문단은 본문 서체와 줄 간격을 확인하기 위한 것입니다. 한글과 영문(ASCII), "
    "숫자 1234567890 이 한 줄에 섞여 있을 때 자간이 어떻게 보이는지 봅니다."
)


def _rows(count: int) -> List[List[str]]:
    return [[f"항목 {i}", f"담당 {i % 5 + 1}팀", f"2026-09-{i % 28 + 1:02d}", f"{i * 1000:,}원"]
            for i in range(1, count + 1)]


#: (파일 이름, 무엇을 확인하는 문서인지, DocumentSpec)
GOLDEN: List[Dict[str, Any]] = [
    {
        "name": "01-공문",
        "checks": "제목·본문·서명란이 있는 가장 흔한 형태. 여백과 제목 크기를 본다.",
        "spec": {
            "title": "업무 협조 요청의 건",
            "page": {"size": "A4", "orientation": "portrait", "marginsMm": [20, 20, 20, 20]},
            "blocks": [
                {"type": "paragraph", "text": "수신: 각 부서장"},
                {"type": "paragraph", "text": "발신: 총무팀"},
                {"type": "paragraph", "text": ""},
                {"type": "heading", "level": 2, "text": "1. 협조 요청 사항"},
                {"type": "paragraph", "text": _LOREM},
                {"type": "heading", "level": 2, "text": "2. 조치 기한"},
                {"type": "paragraph", "text": "2026년 9월 10일(목)까지 회신 바랍니다."},
                {"type": "paragraph", "text": ""},
                {"type": "paragraph", "text": "총무팀장  (인)"},
            ],
        },
    },
    {
        "name": "02-계약서",
        "checks": "조항 번호가 붙은 긴 문서 + 금액 표. 조항 사이 간격을 본다.",
        "spec": {
            "title": "용역 계약서",
            "blocks": [
                {"type": "heading", "level": 2, "text": "제1조 (목적)"},
                {"type": "paragraph", "text": "본 계약은 갑과 을 사이의 용역 수행에 관한 사항을 정함을 목적으로 한다."},
                {"type": "heading", "level": 2, "text": "제2조 (계약 금액)"},
                {"type": "table", "columns": ["구분", "금액", "지급 시기"],
                 "rows": [["착수금", "2,000,000원", "계약 체결 후 7일 이내"],
                          ["중도금", "3,000,000원", "산출물 1차 인도 시"],
                          ["잔금", "5,000,000원", "검수 완료 후 30일 이내"]]},
                {"type": "heading", "level": 2, "text": "제3조 (계약 기간)"},
                {"type": "paragraph", "text": "2026년 9월 1일부터 2026년 12월 31일까지로 한다."},
                {"type": "paragraph", "text": ""},
                {"type": "paragraph", "text": "갑: 주식회사 예시            을: 홍길동"},
            ],
        },
    },
    {
        "name": "03-표중심보고서",
        "checks": "40행짜리 표가 쪽을 넘어갈 때 머리글 행과 셀 경계가 어떻게 되는지 본다.",
        "spec": {
            "title": "월간 진행 현황",
            "blocks": [
                {"type": "paragraph", "text": "2026년 8월 기준 진행 항목 40건."},
                {"type": "table", "columns": ["항목", "담당", "기한", "예산"], "rows": _rows(40)},
            ],
        },
    },
    {
        "name": "04-이미지포함",
        "checks": "이미지가 실제로 보이는지, 지정한 폭(80mm)이 지켜지는지 본다.",
        "spec": {
            "title": "구성도 첨부 보고",
            "blocks": [
                {"type": "paragraph", "text": "아래는 시스템 구성도입니다."},
                {"type": "image", "artifactId": "sample", "widthMm": 80, "alt": "구성도"},
                {"type": "paragraph", "text": "이미지 아래 문단입니다."},
            ],
        },
    },
    {
        "name": "05-쪽나누기",
        "checks": "쪽 나누기가 실제로 새 쪽을 만드는지. 3쪽짜리여야 한다.",
        "spec": {
            "title": "쪽 나누기 확인",
            "blocks": [
                {"type": "heading", "level": 2, "text": "첫째 쪽"},
                {"type": "paragraph", "text": _LOREM},
                {"type": "page_break"},
                {"type": "heading", "level": 2, "text": "둘째 쪽"},
                {"type": "paragraph", "text": _LOREM},
                {"type": "page_break"},
                {"type": "heading", "level": 2, "text": "셋째 쪽"},
                {"type": "paragraph", "text": "여기가 마지막 쪽입니다."},
            ],
        },
    },
    {
        "name": "06-서식_빈칸",
        "checks": "{{빈칸}} 이 그대로 보여야 한다. 이 파일은 07 을 만드는 재료다.",
        "spec": {
            "title": "근로계약서 (서식)",
            "blocks": [
                {"type": "paragraph", "text": "성명: {{name}}"},
                {"type": "paragraph", "text": "부서: {{department}}"},
                {"type": "table", "columns": ["항목", "내용"],
                 "rows": [["입사일", "{{startDate}}"], ["연봉", "{{salary}}"]]},
                {"type": "paragraph", "text": "특이사항: {{note}}"},
            ],
        },
    },
    {
        "name": "07-서식_채움",
        "checks": "06 을 채운 결과. {{ }} 가 하나도 남아 있지 않아야 하고 서식이 유지돼야 한다.",
        "fill_from": "06-서식_빈칸",
        "values": {
            "name": "홍길동",
            "department": "연구개발본부 플랫폼팀",
            "startDate": "2026-09-01",
            "salary": "48,000,000원",
            "note": "수습 3개월",
        },
    },
    {
        "name": "08-특수문자",
        "checks": "& < > \" 가 그대로 보여야 한다. &amp; 처럼 보이면 이중 이스케이프 버그다.",
        "spec": {
            "title": "특수문자 & 기호 <검증>",
            "blocks": [
                {"type": "paragraph", "text": "앰퍼샌드: A & B & C"},
                {"type": "paragraph", "text": "부등호: 1 < 2 그리고 3 > 2"},
                {"type": "paragraph", "text": '따옴표: 그는 "그렇다"고 말했다.'},
                {"type": "paragraph", "text": "중괄호: {단일} 은 자리표시자가 아니다"},
                {"type": "table", "columns": ["기호", "설명"],
                 "rows": [["&", "앰퍼샌드"], ["<>", "부등호"], ['"', "큰따옴표"]]},
                {"type": "paragraph", "text": "한자·기호: 大韓民國 ① ② ③ ※ ★ ℃ ㎡"},
            ],
        },
    },
    {
        "name": "09-줄바꿈",
        "checks": "⚠️ 가장 불확실한 문서. 한 문단 안의 줄바꿈이 실제로 줄을 바꾸는지 본다.",
        "spec": {
            "title": "줄바꿈 확인",
            "blocks": [
                {"type": "paragraph", "text": "주소:\n부산광역시 금정구\n부산대학로63번길 2"},
                {"type": "paragraph", "text": "단락 사이는 빈 문단으로 띄운다."},
                {"type": "paragraph", "text": ""},
                {"type": "paragraph", "text": "한 줄\n두 줄\n세 줄"},
                {"type": "table", "columns": ["항목", "여러 줄 값"],
                 "rows": [["메모", "첫째 줄\n둘째 줄"]]},
            ],
        },
    },
    {
        "name": "10-긴문서",
        "checks": "120개 블록. 열리는 데 걸리는 시간과 쪽 번호가 정상인지 본다.",
        "spec": {
            "title": "분량 확인용 긴 문서",
            "blocks": (
                [{"type": "heading", "level": 2, "text": f"제{i}절"} for i in range(1, 3)]
                + [{"type": "paragraph", "text": f"{i}. {_LOREM}"} for i in range(1, 100)]
                + [{"type": "table", "columns": ["항목", "담당", "기한", "예산"], "rows": _rows(10)}]
                + [{"type": "page_break"}]
                + [{"type": "paragraph", "text": "마지막 문단입니다."}]
            ),
        },
    },
]

CHECKLIST = """한/글에서 열어 확인할 것 (계획 §3.6 release gate)

모든 문서 공통
  1. 열 때 **복구 경고가 뜨지 않는다.** (이것 하나가 이 gate 의 핵심이다)
  2. 다른 이름으로 저장 → 다시 열기 가 된다.
  3. 제목이 본문보다 크고 굵게 보인다.

문서별
  01-공문         여백이 사방 20mm 로 보이는가
  02-계약서       표의 금액 열이 깨지지 않는가
  03-표중심보고서  40행 표가 다음 쪽으로 넘어갈 때 셀이 깨지지 않는가
  04-이미지포함    이미지가 보이는가 / 폭이 약 80mm 인가
  05-쪽나누기      정확히 3쪽인가
  06-서식_빈칸     {{name}} 등이 그대로 보이는가
  07-서식_채움     {{ }} 가 하나도 남아 있지 않은가 / 06 과 서식이 같은가
  08-특수문자      & < > " 가 그대로 보이는가 (&amp; 로 보이면 버그)
  09-줄바꿈       ⚠️ 문단 안 줄바꿈이 실제로 줄을 바꾸는가
                  → 한 줄로 이어져 보이면 <hp:lineBreak/> 로 바꿔야 한다
  10-긴문서       열리는 데 오래 걸리지 않는가 / 쪽 번호가 정상인가

하나라도 어긋나면 그 문서 이름과 증상을 알려주세요.
"""


def build_all(output_dir: str) -> List[Dict[str, Any]]:
    """10종을 만들어 (이름, 경로, 추출 텍스트, 패키지 구조) 목록을 돌려준다."""
    from documents import hwpx

    os.makedirs(output_dir, exist_ok=True)
    made: Dict[str, str] = {}
    report: List[Dict[str, Any]] = []

    for entry in GOLDEN:
        name = entry["name"]
        path = os.path.join(output_dir, f"{name}.hwpx")

        if entry.get("fill_from"):
            source = made[entry["fill_from"]]
            result = hwpx.fill_template(source, entry["values"], path)
            detail: Dict[str, Any] = {"filled": result.filled, "unresolved": result.unresolved}
        else:
            info = hwpx.build(entry["spec"], path,
                              image_loader=lambda _aid: (_SAMPLE_PNG, "png"))
            detail = {"blocks": info["blocks"]}

        made[name] = path
        report.append({
            "name": name,
            "path": path,
            "checks": entry["checks"],
            "detail": detail,
            **_describe(path),
        })
    return report


def _describe(path: str) -> Dict[str, Any]:
    """추출 텍스트와 패키지 구조 — 스냅샷 비교의 대상이다(§3.4 'golden 검증')."""
    from hwpx.document import HwpxDocument

    with zipfile.ZipFile(path) as archive:
        entries = [[info.filename, info.compress_type] for info in archive.infolist()]
    return {"text": HwpxDocument.open(path).export_text(), "entries": entries}


def snapshot(report: List[Dict[str, Any]]) -> Dict[str, Any]:
    """경로·크기처럼 실행마다 달라지는 것을 뺀 비교용 형태."""
    return {
        item["name"]: {"text": item["text"], "entries": item["entries"], "detail": item["detail"]}
        for item in report
    }


SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_hwpx_snapshot.json")


def write_snapshot(report: List[Dict[str, Any]]) -> None:
    """`--update` 로만 부른다. 갱신했으면 **한/글에서 다시 열어 봐야** 의미가 있다."""
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as handle:
        json.dump(snapshot(report), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    # 만들기:   python backend/testdata/golden_hwpx.py [출력 폴더]
    # 스냅샷:   python backend/testdata/golden_hwpx.py --update [출력 폴더]
    import pathlib
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

    args = [a for a in sys.argv[1:] if a != "--update"]
    target = args[0] if args else "uploads/golden"
    report = build_all(target)
    for item in report:
        print(f"{item['name']:16s} {len(item['text']):6,d}자  {len(item['entries']):2d} entry"
              f"  {item['checks']}")
    if "--update" in sys.argv:
        write_snapshot(report)
        print(f"\n스냅샷 갱신: {SNAPSHOT_PATH}")
    print("\n" + CHECKLIST)
