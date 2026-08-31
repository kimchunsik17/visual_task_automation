"""golden 문서 10종 회귀 테스트 (계획 §3.4 'golden 검증', §3.6).

한/글에서 열어 보는 것은 사람이 해야 한다(이 서버에 한/글이 없다). 그 사이에 **엔진을 고쳤을 때
문서가 조용히 달라지는 것**은 여기서 잡는다 — 추출 텍스트와 패키지 구조를 스냅샷과 맞춰 본다.

스냅샷이 달라졌다면 둘 중 하나다.

  1. 버그를 만들었다 → 고친다.
  2. 의도한 개선이다 → `python backend/testdata/golden_hwpx.py` 로 다시 만들어 **한/글에서 다시
     열어 보고** 스냅샷을 갱신한다(`--update`). 열어 보지 않고 갱신하면 이 파일의 의미가 없다.
"""

from __future__ import annotations

import json
import pathlib
import zipfile

import pytest

from testdata import golden_hwpx

SNAPSHOT_PATH = pathlib.Path(__file__).resolve().parent / "testdata" / "golden_hwpx_snapshot.json"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return golden_hwpx.build_all(str(tmp_path_factory.mktemp("golden")))


@pytest.fixture(scope="module")
def by_name(built):
    return {item["name"]: item for item in built}


def test_열_종을_모두_만든다(built):
    assert len(built) == 10
    assert [item["name"] for item in built] == [entry["name"] for entry in golden_hwpx.GOLDEN]


def test_추출_결과와_패키지_구조가_스냅샷과_같다(built):
    """의도치 않게 문서가 달라지면 여기서 걸린다."""
    assert SNAPSHOT_PATH.exists(), (
        f"{SNAPSHOT_PATH} 가 없다 — python backend/testdata/golden_hwpx.py --update 로 만든다")
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    actual = golden_hwpx.snapshot(built)

    assert set(actual) == set(expected)
    for name in expected:
        assert actual[name]["text"] == expected[name]["text"], f"{name}: 문서 내용이 달라졌다"
        assert actual[name]["entries"] == expected[name]["entries"], f"{name}: 패키지 구조가 달라졌다"


@pytest.mark.parametrize("name", [entry["name"] for entry in golden_hwpx.GOLDEN])
def test_모든_문서가_mimetype_규칙을_지킨다(by_name, name):
    with zipfile.ZipFile(by_name[name]["path"]) as archive:
        infos = archive.infolist()
    assert infos[0].filename == "mimetype"
    assert infos[0].compress_type == zipfile.ZIP_STORED


@pytest.mark.parametrize("name", [entry["name"] for entry in golden_hwpx.GOLDEN])
def test_모든_문서를_우리_엔진이_다시_연다(by_name, name):
    """만들기만 하고 못 읽는 파일이면 안 된다 — 안전 검사도 함께 통과해야 한다."""
    from documents import hwpx

    package = hwpx.HwpxPackage.open(by_name[name]["path"])
    assert package.section_names()


@pytest.mark.parametrize("name", [entry["name"] for entry in golden_hwpx.GOLDEN])
def test_모든_문서를_표준_구현이_다시_연다(by_name, name):
    from hwpx.document import HwpxDocument

    assert HwpxDocument.open(by_name[name]["path"]) is not None


# ── 문서별로 '무엇을 확인하는 문서인지' 가 실제로 담겼는가 ──────────────

def test_공문에_수신과_발신이_있다(by_name):
    text = by_name["01-공문"]["text"]
    assert "수신:" in text and "발신:" in text and "업무 협조 요청의 건" in text


def test_계약서에_금액표가_있다(by_name):
    text = by_name["02-계약서"]["text"]
    assert "착수금" in text and "2,000,000원" in text and "제3조" in text


def test_표중심보고서에_40행이_다_들어간다(by_name):
    text = by_name["03-표중심보고서"]["text"]
    assert "항목 1" in text and "항목 40" in text
    assert "항목 41" not in text


def test_이미지문서에_그림이_실제로_들어간다(by_name):
    names = [entry[0] for entry in by_name["04-이미지포함"]["entries"]]
    assert any(n.startswith("BinData/") for n in names), "그림 데이터가 패키지에 없다"


def test_쪽나누기_문서가_세_구역을_갖는다(by_name):
    text = by_name["05-쪽나누기"]["text"]
    assert "첫째 쪽" in text and "둘째 쪽" in text and "셋째 쪽" in text


def test_서식에는_빈칸이_남아_있다(by_name):
    text = by_name["06-서식_빈칸"]["text"]
    for key in ("{{name}}", "{{department}}", "{{startDate}}", "{{salary}}", "{{note}}"):
        assert key in text


def test_채운_문서에는_빈칸이_하나도_없다(by_name):
    item = by_name["07-서식_채움"]
    assert "{{" not in item["text"], "채우지 못한 자리표시자가 남았다"
    assert item["detail"]["unresolved"] == []
    for value in ("홍길동", "연구개발본부 플랫폼팀", "2026-09-01", "48,000,000원", "수습 3개월"):
        assert value in item["text"]


def test_표_안의_빈칸도_채워진다(by_name):
    """표 셀은 문단을 품고 있어 별도 경로처럼 보이지만 같은 엔진이 처리해야 한다."""
    filled = by_name["07-서식_채움"]["detail"]["filled"]
    assert filled.get("startDate") == 1 and filled.get("salary") == 1


def test_특수문자가_이중_이스케이프되지_않는다(by_name):
    """`&amp;` 처럼 보이면 손으로 이스케이프하던 옛 버그가 돌아온 것이다."""
    text = by_name["08-특수문자"]["text"]
    assert "A & B & C" in text
    assert "1 < 2" in text and "3 > 2" in text
    assert '"그렇다"' in text
    assert "&amp;" not in text and "&lt;" not in text

    with zipfile.ZipFile(by_name["08-특수문자"]["path"]) as archive:
        raw = archive.read("Contents/section0.xml").decode("utf-8")
    assert "&amp;amp;" not in raw, "XML 안에서 두 번 이스케이프됐다"


def test_줄바꿈이_문서에_남아_있다(by_name):
    """한/글에서 실제로 줄이 바뀌는지는 사람이 봐야 한다 — 여기서는 값이 유실되지 않았는지만 본다."""
    text = by_name["09-줄바꿈"]["text"]
    assert "부산광역시 금정구" in text and "부산대학로63번길 2" in text
    assert "한 줄" in text and "두 줄" in text and "세 줄" in text


def test_긴_문서가_분량을_담는다(by_name):
    text = by_name["10-긴문서"]["text"]
    assert len(text) > 9000
    assert "마지막 문단입니다." in text


# ── 확인 체크리스트가 문서와 어긋나지 않는다 ───────────────────────────

def test_모든_문서에_무엇을_볼지가_적혀_있다():
    for entry in golden_hwpx.GOLDEN:
        assert entry.get("checks"), f"{entry['name']}: 확인할 내용이 없다"
        assert entry["name"] in golden_hwpx.CHECKLIST, \
            f"{entry['name']}: 체크리스트에 빠졌다 — 사람이 열어 볼 때 그냥 지나친다"
