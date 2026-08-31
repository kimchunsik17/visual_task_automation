"""HWPX 공용 엔진 계약 테스트 (한국형 노드 계획 Phase 1, §3.6).

이 파일이 지키는 문장:

  1. **run 이 쪼개져도 채운다.** 사용자가 한/글에서 `{{name}}` 의 일부만 굵게 하면 그 한 낱말이
     여러 `<hp:t>` 로 갈라진다. 예전 문자열 치환과 라이브러리의 `replace_text_in_runs` 는 둘 다
     이 경우 **0건 치환**이었다 — 조용히 안 채워진 채 결과가 나갔다.
  2. **입력 서식은 읽기만 한다.** 실행 전후로 byte 가 같아야 한다.
  3. **못 채운 것을 조용히 넘기지 않는다.** 무엇이 남았는지 이름으로 알려준다.
  4. **남이 준 파일을 열기 전에 검사한다.** 압축 폭탄·경로 탈출·XML 폭탄을 거부한다.
  5. **패키지 모양을 보존한다.** `mimetype` 은 첫 entry·무압축이어야 한다.
"""

from __future__ import annotations

import hashlib
import zipfile
from xml.etree import ElementTree as ET

import pytest

from documents import hwpx
from documents.hwpx import safety, xmlio


# ── fixture 만들기 ──────────────────────────────────────────────────────

def _doc(tmp_path, paragraphs, *, name="tpl.hwpx"):
    from hwpx.document import HwpxDocument

    document = HwpxDocument.new()
    for text in paragraphs:
        document.add_paragraph(text)
    path = str(tmp_path / name)
    document.save_to_path(path)
    return path


def _split_run(path, whole, first, second):
    """`whole` 를 두 run 으로 쪼갠다 — 한/글에서 글자 일부의 서식을 바꾸면 실제로 이렇게 된다."""
    with zipfile.ZipFile(path) as zin:
        infos = list(zin.infolist())
        data = {i.filename: zin.read(i.filename) for i in infos}
    xml = data["Contents/section0.xml"].decode()
    before = f"<hp:t>{whole}</hp:t>"
    assert before in xml, f"예상한 run 구조가 아니다: {before!r}"
    data["Contents/section0.xml"] = xml.replace(
        before, f"<hp:t>{first}</hp:t></hp:run><hp:run charPrIDRef=\"0\"><hp:t>{second}</hp:t>"
    ).encode()
    with zipfile.ZipFile(path, "w") as zout:
        for info in infos:
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zout.writestr(zi, data[info.filename])
    return path


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _text(path):
    from hwpx.document import HwpxDocument

    return HwpxDocument.open(path).export_text()


# ── 1. run 이 쪼개져도 채운다 ───────────────────────────────────────────

def test_한_run_안의_자리표시자를_채운다(tmp_path):
    tpl = _doc(tmp_path, ["고객: {{name}}"])
    result = hwpx.fill_template(tpl, {"name": "홍길동"}, str(tmp_path / "out.hwpx"))
    assert result.filled == {"name": 1} and result.ok
    assert "고객: 홍길동" in _text(str(tmp_path / "out.hwpx"))


def test_여러_run_으로_쪼개진_자리표시자를_채운다(tmp_path):
    """이게 이 엔진을 만든 이유다 — 예전 구현과 라이브러리가 둘 다 실패하는 경우."""
    tpl = _doc(tmp_path, ["고객: {{name}}"])
    _split_run(tpl, "고객: {{name}}", "고객: {{na", "me}}")

    result = hwpx.fill_template(tpl, {"name": "홍길동"}, str(tmp_path / "out.hwpx"))
    assert result.filled == {"name": 1}, "쪼개진 자리표시자를 못 채웠다"
    assert "고객: 홍길동" in _text(str(tmp_path / "out.hwpx"))
    assert "{{" not in _text(str(tmp_path / "out.hwpx"))


def test_라이브러리는_쪼개진_자리표시자를_못_채운다(tmp_path):
    """우리 엔진이 필요한 근거를 고정한다 — 라이브러리가 고쳐지면 이 테스트가 알려준다."""
    from hwpx.document import HwpxDocument

    tpl = _doc(tmp_path, ["고객: {{name}}"])
    _split_run(tpl, "고객: {{name}}", "고객: {{na", "me}}")
    document = HwpxDocument.open(tpl)
    assert document.replace_text_in_runs("{{name}}", "홍길동") == 0


def test_세_조각으로_쪼개져도_채운다(tmp_path):
    tpl = _doc(tmp_path, ["금액: {{amount}}"])
    _split_run(tpl, "금액: {{amount}}", "금액: {{amo", "unt}}")
    _split_run(tpl, "금액: {{amo", "금액: {{", "amo")
    result = hwpx.fill_template(tpl, {"amount": "5,000원"}, str(tmp_path / "out.hwpx"))
    assert result.filled == {"amount": 1}
    assert "금액: 5,000원" in _text(str(tmp_path / "out.hwpx"))


def test_읽기도_쪼개진_자리표시자를_찾는다(tmp_path):
    tpl = _doc(tmp_path, ["고객: {{name}}"])
    _split_run(tpl, "고객: {{name}}", "고객: {{na", "me}}")
    assert hwpx.template_keys(tpl) == ["name"]


def test_한_문단에_여러_자리표시자가_있어도_각각_채운다(tmp_path):
    tpl = _doc(tmp_path, ["{{a}}와 {{b}}와 {{c}}"])
    result = hwpx.fill_template(tpl, {"a": "하나", "b": "둘", "c": "셋"},
                                str(tmp_path / "out.hwpx"))
    assert result.filled == {"a": 1, "b": 1, "c": 1}
    assert "하나와 둘와 셋" in _text(str(tmp_path / "out.hwpx"))


def test_같은_자리표시자가_여러_번_나오면_모두_채운다(tmp_path):
    tpl = _doc(tmp_path, ["{{name}} 님, {{name}} 님께"])
    result = hwpx.fill_template(tpl, {"name": "홍길동"}, str(tmp_path / "out.hwpx"))
    assert result.filled == {"name": 2}
    assert "홍길동 님, 홍길동 님께" in _text(str(tmp_path / "out.hwpx"))


def test_공백을_넣어_쓴_자리표시자도_인식한다(tmp_path):
    tpl = _doc(tmp_path, ["고객: {{ name }}"])
    assert hwpx.template_keys(tpl) == ["name"]
    result = hwpx.fill_template(tpl, {"name": "홍길동"}, str(tmp_path / "out.hwpx"))
    assert result.filled == {"name": 1}


def test_표_안의_자리표시자도_채운다(tmp_path):
    from hwpx.document import HwpxDocument

    document = HwpxDocument.new()
    document.add_paragraph("계약 정보")
    table = document.add_table(rows=2, cols=2)
    table.set_cell_text(0, 0, "상대방")
    table.set_cell_text(0, 1, "{{party}}")
    table.set_cell_text(1, 0, "금액")
    table.set_cell_text(1, 1, "{{amount}}")
    tpl = str(tmp_path / "tbl.hwpx")
    document.save_to_path(tpl)

    assert set(hwpx.template_keys(tpl)) == {"party", "amount"}
    result = hwpx.fill_template(tpl, {"party": "주식회사 예시", "amount": "5,000,000원"},
                                str(tmp_path / "out.hwpx"))
    assert result.filled == {"party": 1, "amount": 1}
    filled = _text(str(tmp_path / "out.hwpx"))
    assert "주식회사 예시" in filled and "5,000,000원" in filled


# ── 2. 특수문자와 줄바꿈 ────────────────────────────────────────────────

@pytest.mark.parametrize("value", [
    "A & B",                    # XML 에서 그대로 쓰면 문서가 깨진다
    "<태그>",
    'a "인용" b',
    "1 < 2 && 3 > 2",
    "재무 & 회계 <부서>",
])
def test_XML_특수문자를_그대로_담는다(tmp_path, value):
    """이스케이프는 직렬화에 맡긴다 — 손으로 &amp; 를 만들다 이중 이스케이프가 났었다."""
    tpl = _doc(tmp_path, ["값: {{v}}"])
    out = str(tmp_path / "out.hwpx")
    result = hwpx.fill_template(tpl, {"v": value}, out)
    assert result.filled == {"v": 1}
    assert f"값: {value}" in _text(out)


def test_줄바꿈이_든_값을_채운다(tmp_path):
    tpl = _doc(tmp_path, ["주소: {{addr}}"])
    out = str(tmp_path / "out.hwpx")
    result = hwpx.fill_template(tpl, {"addr": "부산광역시\n금정구"}, out)
    assert result.filled == {"addr": 1}
    assert "부산광역시\n금정구" in _text(out)


def test_숫자와_None_도_문자열로_담는다(tmp_path):
    tpl = _doc(tmp_path, ["{{n}}/{{z}}"])
    out = str(tmp_path / "out.hwpx")
    result = hwpx.fill_template(tpl, {"n": 42, "z": None}, out)
    assert result.filled == {"n": 1, "z": 1}
    assert "42/" in _text(out)


def test_탭을_가로질러_매칭되지_않는다(tmp_path):
    """탭은 `<hp:t>` 의 형제 요소라, 가로질러 치환하면 탭이 값 한가운데 남는다."""
    tpl = _doc(tmp_path, ["{{a\tb}}"])
    assert hwpx.template_keys(tpl) == []


# ── 3. 못 채운 것을 알려준다 ────────────────────────────────────────────

def test_값이_없는_자리표시자는_남기고_이름으로_알린다(tmp_path):
    tpl = _doc(tmp_path, ["{{have}} / {{missing}}"])
    out = str(tmp_path / "out.hwpx")
    result = hwpx.fill_template(tpl, {"have": "채움"}, out)
    assert result.filled == {"have": 1}
    assert result.unresolved == ["missing"]
    assert result.ok is False
    # 빈칸으로 지우지 않는다 — 무엇이 안 채워졌는지 사용자가 봐야 한다
    assert "{{missing}}" in _text(out)


def test_쓰이지_않은_값도_알려준다(tmp_path):
    tpl = _doc(tmp_path, ["{{a}}"])
    result = hwpx.fill_template(tpl, {"a": "1", "없는키": "2"}, str(tmp_path / "out.hwpx"))
    assert result.unused == ["없는키"]


def test_자리표시자가_없는_서식은_그대로_복사된다(tmp_path):
    tpl = _doc(tmp_path, ["자리표시자 없음"])
    out = str(tmp_path / "out.hwpx")
    result = hwpx.fill_template(tpl, {"a": "1"}, out)
    assert result.filled == {} and result.unresolved == []
    assert "자리표시자 없음" in _text(out)


# ── 4. 입력 서식을 건드리지 않는다 ──────────────────────────────────────

def test_실행_전후로_입력_서식이_byte_동일하다(tmp_path):
    tpl = _doc(tmp_path, ["{{a}} {{b}}"])
    before = _sha(tpl)
    hwpx.fill_template(tpl, {"a": "1", "b": "2"}, str(tmp_path / "out.hwpx"))
    assert _sha(tpl) == before


def test_키가_하나도_안_맞아도_입력_서식은_그대로다(tmp_path):
    tpl = _doc(tmp_path, ["{{a}}"])
    before = _sha(tpl)
    hwpx.fill_template(tpl, {"완전히": "다른"}, str(tmp_path / "out.hwpx"))
    assert _sha(tpl) == before


# ── 5. 패키지 모양 보존 ─────────────────────────────────────────────────

def test_출력의_mimetype이_첫_entry이고_무압축이다(tmp_path):
    tpl = _doc(tmp_path, ["{{a}}"])
    out = str(tmp_path / "out.hwpx")
    hwpx.fill_template(tpl, {"a": "1"}, out)
    infos = zipfile.ZipFile(out).infolist()
    assert infos[0].filename == "mimetype"
    assert infos[0].compress_type == zipfile.ZIP_STORED


def test_entry_순서와_압축방식이_원본과_같다(tmp_path):
    tpl = _doc(tmp_path, ["{{a}}"])
    out = str(tmp_path / "out.hwpx")
    original = [(i.filename, i.compress_type) for i in zipfile.ZipFile(tpl).infolist()]
    hwpx.fill_template(tpl, {"a": "1"}, out)
    assert [(i.filename, i.compress_type) for i in zipfile.ZipFile(out).infolist()] == original


def test_건드리지_않은_entry는_바이트가_그대로다(tmp_path):
    """편집한 section 만 다시 직렬화한다 — 나머지를 재직렬화하면 형식이 미세하게 달라진다."""
    tpl = _doc(tmp_path, ["{{a}}"])
    out = str(tmp_path / "out.hwpx")
    hwpx.fill_template(tpl, {"a": "1"}, out)
    src, dst = zipfile.ZipFile(tpl), zipfile.ZipFile(out)
    for name in src.namelist():
        if name == "Contents/section0.xml":
            continue
        assert src.read(name) == dst.read(name), name


def test_XML_선언과_namespace_선언이_보존된다(tmp_path):
    tpl = _doc(tmp_path, ["{{a}}"])
    out = str(tmp_path / "out.hwpx")
    hwpx.fill_template(tpl, {"a": "1"}, out)
    before = zipfile.ZipFile(tpl).read("Contents/section0.xml")
    after = zipfile.ZipFile(out).read("Contents/section0.xml")
    assert after.startswith(b"<?xml")
    assert set(xmlio.namespaces(before)) == set(xmlio.namespaces(after)), \
        "ET 가 쓰지 않는 namespace 선언을 버리면 파일이 크게 달라진다"


def test_채운_문서를_라이브러리가_다시_연다(tmp_path):
    """우리가 만든 파일을 표준 구현이 읽을 수 있어야 한다."""
    tpl = _doc(tmp_path, ["{{a}}"])
    out = str(tmp_path / "out.hwpx")
    hwpx.fill_template(tpl, {"a": "값"}, out)
    assert "값" in _text(out)
    assert hwpx.template_keys(out) == []


# ── 6. 남이 준 파일을 열기 전에 검사한다 ────────────────────────────────

def _zip_with(tmp_path, entries, name="bad.hwpx", **kwargs):
    path = str(tmp_path / name)
    with zipfile.ZipFile(path, "w") as z:
        for entry_name, raw in entries:
            info = zipfile.ZipInfo(entry_name)
            info.compress_type = zipfile.ZIP_STORED
            for key, value in kwargs.items():
                setattr(info, key, value)
            z.writestr(info, raw)
    return path


def test_ZIP이_아니면_거부한다(tmp_path):
    path = tmp_path / "x.hwpx"
    path.write_bytes("이건 그냥 텍스트".encode())
    with pytest.raises(safety.PackageRejected) as exc:
        hwpx.HwpxPackage.open(str(path))
    assert exc.value.reason == "NOT_ZIP"


def test_mimetype이_없으면_거부한다(tmp_path):
    path = _zip_with(tmp_path, [("Contents/section0.xml", b"<a/>")])
    with pytest.raises(safety.PackageRejected) as exc:
        hwpx.HwpxPackage.open(path)
    assert exc.value.reason == "NOT_HWPX"


def test_확장자만_바꾼_다른_ZIP을_거부한다(tmp_path):
    path = _zip_with(tmp_path, [("mimetype", b"application/zip")])
    with pytest.raises(safety.PackageRejected) as exc:
        hwpx.HwpxPackage.open(path)
    assert exc.value.reason == "BAD_MIMETYPE"


def test_경로_탈출_항목을_거부한다(tmp_path):
    path = _zip_with(tmp_path, [("mimetype", b"application/hwp+zip"),
                                ("../../etc/passwd", b"x")])
    with pytest.raises(safety.PackageRejected) as exc:
        hwpx.HwpxPackage.open(path)
    assert exc.value.reason == "PATH_TRAVERSAL"


def test_절대경로_항목을_거부한다(tmp_path):
    path = _zip_with(tmp_path, [("mimetype", b"application/hwp+zip"), ("/etc/passwd", b"x")])
    with pytest.raises(safety.PackageRejected) as exc:
        hwpx.HwpxPackage.open(path)
    assert exc.value.reason == "ABSOLUTE_PATH"


def test_symlink_항목을_거부한다(tmp_path):
    path = _zip_with(tmp_path, [("mimetype", b"application/hwp+zip"), ("link", b"/etc/passwd")],
                     external_attr=(0xA1FF << 16))
    with pytest.raises(safety.PackageRejected) as exc:
        hwpx.HwpxPackage.open(path)
    assert exc.value.reason == "SYMLINK"


def test_항목이_너무_많으면_거부한다(tmp_path):
    entries = [("mimetype", b"application/hwp+zip")]
    entries += [(f"f{i}", b"x") for i in range(safety.MAX_ENTRIES + 1)]
    path = _zip_with(tmp_path, entries)
    with pytest.raises(safety.PackageRejected) as exc:
        hwpx.HwpxPackage.open(path)
    assert exc.value.reason == "TOO_MANY_ENTRIES"


def test_압축폭탄을_거부한다(tmp_path):
    """1KB 가 수십 MB 로 풀리는 항목. 읽기 전에 목록만 보고 판단한다."""
    path = str(tmp_path / "bomb.hwpx")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", b"application/hwp+zip")
        z.writestr("Contents/section0.xml", b"\0" * (40 * 1024 * 1024))
    with pytest.raises(safety.PackageRejected) as exc:
        hwpx.HwpxPackage.open(path)
    assert exc.value.reason == "COMPRESSION_BOMB"


def test_XML_폭탄_선언을_거부한다(tmp_path):
    """중첩 entity 하나로 파서가 메모리를 다 쓴다 — 파싱을 시작하기 전에 막는다."""
    evil = (b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "haha">]>'
            b'<hs:sec xmlns:hs="x">&lol;</hs:sec>')
    path = _zip_with(tmp_path, [("mimetype", b"application/hwp+zip"),
                                ("Contents/section0.xml", evil)])
    with pytest.raises(safety.PackageRejected) as exc:
        hwpx.HwpxPackage.open(path)
    assert exc.value.reason == "XML_DOCTYPE"


def test_외부_entity_선언도_거부한다(tmp_path):
    """서버 파일을 읽어 문서에 실어 보내는 고전적인 XXE."""
    evil = (b'<?xml version="1.0"?>'
            b'<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            b'<hs:sec xmlns:hs="x">&x;</hs:sec>')
    path = _zip_with(tmp_path, [("mimetype", b"application/hwp+zip"),
                                ("Contents/section0.xml", evil)])
    with pytest.raises(safety.PackageRejected):
        hwpx.HwpxPackage.open(path)


def test_같은_이름의_항목이_두_번_있으면_거부한다(tmp_path):
    path = str(tmp_path / "dup.hwpx")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", b"application/hwp+zip")
        z.writestr("Contents/section0.xml", b"<a/>")
        z.writestr("Contents/section0.xml", b"<b/>")
    with pytest.raises(safety.PackageRejected) as exc:
        hwpx.HwpxPackage.open(path)
    assert exc.value.reason == "DUPLICATE_ENTRY"


def test_거부_메시지가_사용자에게_보여도_되는_수준이다(tmp_path):
    path = _zip_with(tmp_path, [("mimetype", b"application/zip")])
    with pytest.raises(safety.PackageRejected) as exc:
        hwpx.HwpxPackage.open(path)
    message = str(exc.value)
    assert "Traceback" not in message and "/home/" not in message


# ── 7. 자리표시자 찾기 단위 ─────────────────────────────────────────────

def _root(xml: str) -> ET.Element:
    return ET.fromstring(
        '<hs:sec xmlns:hs="s" xmlns:hp="p">' + xml + "</hs:sec>")


def test_이름_안에_공백이_있으면_자리표시자가_아니다():
    """허용하면 본문의 `{{` 와 한참 뒤 `}}` 가 이어져 문장 한 덩어리를 자리표시자로 오인한다."""
    root = _root('<hp:p><hp:run><hp:t>{{열림 과 }}닫힘</hp:t></hp:run></hp:p>')
    assert hwpx.find_placeholders(root) == []


def test_짝이_맞지_않는_중괄호는_자리표시자가_아니다():
    root = _root('<hp:p><hp:run><hp:t>{{하나 만 열림</hp:t></hp:run></hp:p>')
    assert hwpx.find_placeholders(root) == []


def test_빈_자리표시자는_인식하지_않는다():
    root = _root('<hp:p><hp:run><hp:t>{{}} {{ }}</hp:t></hp:run></hp:p>')
    assert hwpx.find_placeholders(root) == []


def test_문단을_가로질러_매칭되지_않는다():
    root = _root('<hp:p><hp:run><hp:t>{{a</hp:t></hp:run></hp:p>'
                 '<hp:p><hp:run><hp:t>b}}</hp:t></hp:run></hp:p>')
    assert hwpx.find_placeholders(root) == []
