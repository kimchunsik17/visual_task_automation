"""`hwpxDocumentNode` — DocumentSpec 으로 문서를 만든다 (계획 §3.2, Phase 1).

이 파일이 지키는 문장:

  1. **지원하지 않는 것을 조용히 빠뜨리지 않는다.** 도형·수식이 든 스펙은 무시되는 게 아니라
     실패한다 — 조용히 빠뜨리면 사용자는 문서를 열어 보고서야 알게 된다.
  2. **이미지는 Artifact 로만 받는다.** 경로나 URL 을 받으면 서버 파일을 문서에 실어 보낼 수 있다.
  3. **LLM 이 준 JSON 을 받아낸다.** 코드펜스가 붙어 오는 것이 일상이다.
  4. **노드가 만든 파일은 uploads/ 안에 있다.** 서버 아무 곳에나 쓰지 않는다.
"""

from __future__ import annotations

import json
import os
import zipfile

import pytest

from documents import hwpx
from documents import hwpx_runtime as runtime


def _text(path):
    from hwpx.document import HwpxDocument

    return HwpxDocument.open(path).export_text()


SPEC = {
    "title": "회의 결과 보고",
    "page": {"size": "A4", "orientation": "portrait", "marginsMm": [20, 20, 18, 18]},
    "blocks": [
        {"type": "heading", "level": 2, "text": "결정 사항"},
        {"type": "paragraph", "text": "다음과 같이 정했다."},
        {"type": "table", "columns": ["담당", "기한"], "rows": [["개발팀", "2026-09-10"]]},
        {"type": "page_break"},
        {"type": "paragraph", "text": "다음 쪽"},
    ],
}


# ── 만들기 ──────────────────────────────────────────────────────────────

def test_스펙대로_문서를_만든다(tmp_path):
    out = str(tmp_path / "doc.hwpx")
    info = hwpx.build(SPEC, out)
    assert info["blockCount"] == 5
    assert info["blocks"] == {"heading": 1, "paragraph": 2, "table": 1, "page_break": 1}

    text = _text(out)
    for expected in ("회의 결과 보고", "결정 사항", "다음과 같이 정했다.", "개발팀", "2026-09-10", "다음 쪽"):
        assert expected in text


def test_표의_첫_줄이_열_이름이다(tmp_path):
    out = str(tmp_path / "doc.hwpx")
    hwpx.build({"blocks": [{"type": "table", "columns": ["담당", "기한"],
                            "rows": [["개발팀", "9/10"]]}]}, out)
    text = _text(out)
    assert text.index("담당") < text.index("개발팀")


def test_만든_문서의_패키지_모양이_규칙을_지킨다(tmp_path):
    out = str(tmp_path / "doc.hwpx")
    hwpx.build(SPEC, out)
    infos = zipfile.ZipFile(out).infolist()
    assert infos[0].filename == "mimetype"
    assert infos[0].compress_type == zipfile.ZIP_STORED


def test_만든_문서를_우리_엔진이_다시_연다(tmp_path):
    out = str(tmp_path / "doc.hwpx")
    hwpx.build(SPEC, out)
    package = hwpx.HwpxPackage.open(out)      # 안전 검사를 통과한다
    assert package.section_names()


def test_한컴_오피스_없이_만들어진다(tmp_path):
    """이 서버에는 한/글도 Windows COM 도 없다(§11 비목표). 그래도 만들어져야 한다."""
    import sys

    assert "win32com" not in sys.modules and "pyhwpx" not in sys.modules
    out = str(tmp_path / "doc.hwpx")
    hwpx.build(SPEC, out)
    assert os.path.exists(out)


# ── 지원하지 않는 것을 조용히 넘기지 않는다 ─────────────────────────────

@pytest.mark.parametrize("kind", ["shape", "equation", "chart", "macro", "textbox"])
def test_지원하지_않는_블록은_실패한다(tmp_path, kind):
    spec = {"blocks": [{"type": "paragraph", "text": "정상"}, {"type": kind}]}
    with pytest.raises(hwpx.UnsupportedFeature) as exc:
        hwpx.build(spec, str(tmp_path / "doc.hwpx"))
    assert kind in str(exc.value)
    assert exc.value.reason == "HWPX_UNSUPPORTED_FEATURE"


def test_지원하지_않는_블록이_있으면_파일을_만들지_않는다(tmp_path):
    """절반쯤 만들어진 문서를 내보내지 않는다 — 스펙을 먼저 검사한다."""
    out = str(tmp_path / "doc.hwpx")
    with pytest.raises(hwpx.UnsupportedFeature):
        hwpx.build({"blocks": [{"type": "paragraph", "text": "a"}, {"type": "chart"}]}, out)
    assert not os.path.exists(out)


def test_무엇을_지원하는지_알려준다(tmp_path):
    with pytest.raises(hwpx.UnsupportedFeature) as exc:
        hwpx.build({"blocks": [{"type": "chart"}]}, str(tmp_path / "doc.hwpx"))
    for supported in hwpx.builder.SUPPORTED_BLOCKS:
        assert supported in str(exc.value)


def test_어느_블록에서_멈췄는지_알려준다(tmp_path):
    spec = {"blocks": [{"type": "paragraph", "text": "a"},
                       {"type": "paragraph", "text": "b"},
                       {"type": "table", "columns": [], "rows": []}]}
    with pytest.raises(hwpx.SpecError) as exc:
        hwpx.build(spec, str(tmp_path / "doc.hwpx"))
    assert "blocks[2]" in str(exc.value)


# ── 스펙 검증 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("spec, fragment", [
    ({"blocks": "배열이 아님"}, "blocks"),
    ({"blocks": [{"type": "heading", "level": 9, "text": "x"}]}, "level"),
    ({"blocks": [{"type": "heading", "level": 1}]}, "text"),
    ({"blocks": [{"type": "table", "columns": ["a"], "rows": [["x", "y"]]}]}, "칸 수"),
    ({"blocks": [{"type": "table", "columns": [], "rows": []}]}, "columns"),
    ({"page": {"orientation": "대각선"}}, "orientation"),
    ({"page": {"marginsMm": [1, 2]}}, "marginsMm"),
])
def test_잘못된_스펙을_이유와_함께_거부한다(tmp_path, spec, fragment):
    with pytest.raises(hwpx.SpecError) as exc:
        hwpx.build(spec, str(tmp_path / "doc.hwpx"))
    assert fragment in str(exc.value)


def test_블록이_너무_많으면_거부한다(tmp_path):
    spec = {"blocks": [{"type": "paragraph", "text": "x"}] * (hwpx.builder.MAX_BLOCKS + 1)}
    with pytest.raises(hwpx.SpecError, match="너무 많"):
        hwpx.build(spec, str(tmp_path / "doc.hwpx"))


def test_표가_너무_크면_거부한다(tmp_path):
    spec = {"blocks": [{"type": "table", "columns": ["a", "b"],
                        "rows": [["x", "y"]] * 3000}]}
    with pytest.raises(hwpx.SpecError, match="너무 큽"):
        hwpx.build(spec, str(tmp_path / "doc.hwpx"))


def test_빈_스펙도_문서가_된다(tmp_path):
    out = str(tmp_path / "doc.hwpx")
    info = hwpx.build({"title": "제목만"}, out)
    assert info["blockCount"] == 0
    assert "제목만" in _text(out)


# ── 이미지는 Artifact 로만 ──────────────────────────────────────────────

def test_경로나_URL_로는_이미지를_넣을_수_없다(tmp_path):
    """받으면 서버 파일을 문서에 실어 보낼 수 있다(§3.3)."""
    for block in ({"type": "image", "path": "/etc/passwd"},
                  {"type": "image", "url": "https://example.com/a.png"},
                  {"type": "image"}):
        with pytest.raises(hwpx.SpecError, match="artifactId"):
            hwpx.build({"blocks": [block]}, str(tmp_path / "doc.hwpx"))


def test_해석기가_없으면_이미지를_넣지_않고_실패한다(tmp_path):
    with pytest.raises(hwpx.SpecError, match="Artifact"):
        hwpx.build({"blocks": [{"type": "image", "artifactId": "a1"}]},
                   str(tmp_path / "doc.hwpx"))


def test_Artifact_로_넘긴_이미지를_넣는다(tmp_path):
    png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
           b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
           b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
    out = str(tmp_path / "doc.hwpx")
    info = hwpx.build({"blocks": [{"type": "image", "artifactId": "a1", "widthMm": 40}]},
                      out, image_loader=lambda aid: (png, "png"))
    assert info["blocks"] == {"image": 1}
    assert os.path.exists(out)


def test_지원하지_않는_이미지_형식을_거부한다(tmp_path):
    with pytest.raises(hwpx.SpecError, match="이미지 형식"):
        hwpx.build({"blocks": [{"type": "image", "artifactId": "a1"}]},
                   str(tmp_path / "doc.hwpx"),
                   image_loader=lambda aid: (b"MZ", "exe"))


# ── 노드 런타임: LLM 출력 받아내기 ──────────────────────────────────────

def test_코드펜스로_감싼_JSON도_받아낸다(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("uploads")
    fenced = "```json\n" + json.dumps(SPEC, ensure_ascii=False) + "\n```"
    result = runtime.run("create", incoming=fenced)
    assert result["blockCount"] == 5


def test_dict를_그대로_줘도_받는다(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("uploads")
    assert runtime.run("create", incoming=SPEC)["blockCount"] == 5


def test_JSON이_아니면_고칠_수_있는_문구로_실패한다(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("uploads")
    with pytest.raises(runtime.HwpxNodeError) as exc:
        runtime.run("create", incoming="이건 그냥 문장입니다")
    assert exc.value.reason == "HWPX_SPEC_NOT_JSON"
    assert "JSON" in str(exc.value)


def test_앞_노드가_아무것도_안_주면_알려준다(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("uploads")
    with pytest.raises(runtime.HwpxNodeError) as exc:
        runtime.run("create", incoming="")
    assert exc.value.reason == "HWPX_NO_SPEC"


# ── 노드 런타임: 경로 ───────────────────────────────────────────────────

def test_파일은_uploads_안에만_쓴다(tmp_path, monkeypatch):
    """노드가 서버 아무 곳에나 파일을 쓰지 않게 한다."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("uploads")
    result = runtime.run("create", incoming=SPEC, output_path="/etc/cron.d/evil.hwpx")
    assert result["path"] == "uploads/evil.hwpx"
    assert os.path.exists("uploads/evil.hwpx")


def test_경로를_안_주면_제목을_따서_짓는다(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("uploads")
    result = runtime.run("create", incoming=SPEC)
    assert result["path"].startswith("uploads/회의 결과 보고_")
    assert result["path"].endswith(".hwpx")


def test_같은_스펙을_두_번_만들어도_덮어쓰지_않는다(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("uploads")
    first = runtime.run("create", incoming=SPEC)["path"]
    second = runtime.run("create", incoming=SPEC)["path"]
    assert first != second


# ── 노드 런타임: inspect · validate ─────────────────────────────────────

# 살펴볼 파일은 **경로가 아니라 artifact** 로 받는다 — 사용자가 서버 경로를 알 필요가 없고,
# artifacts.resolve 가 소유·만료·경로·해시를 검증한다(ADR-0018).

def _inspectable(tmp_path, spec, name="t.hwpx"):
    path = str(tmp_path / name)
    hwpx.build(spec, path)
    return path


def test_inspect가_빈칸과_구조를_알려준다(tmp_path):
    path = _inspectable(tmp_path, {"blocks": [{"type": "paragraph", "text": "고객 {{name}} / 금액 {{amount}}"}]})
    result = runtime.inspect(path)
    assert result["placeholders"] == ["name", "amount"]
    assert result["sections"] == 1 and result["entries"] > 0


def test_validate는_정상_문서를_통과시킨다(tmp_path):
    result = runtime.validate(_inspectable(tmp_path, {"title": "정상"}, "ok.hwpx"))
    assert result["ok"] is True and result["warnings"] == []


def test_validate는_거부_사유를_예외가_아니라_결과로_준다(tmp_path):
    """검사가 목적이므로 '열 수 없다'도 정상 출력이다."""
    bad = tmp_path / "bad.hwpx"
    bad.write_bytes("HWPX 아님".encode())
    result = runtime.validate(str(bad))
    assert result["ok"] is False and result["reason"] == "NOT_ZIP"


def test_없는_파일을_살펴보면_알려준다(tmp_path):
    with pytest.raises(runtime.HwpxNodeError) as exc:
        runtime.inspect(str(tmp_path / "없다.hwpx"))
    assert exc.value.reason == "HWPX_NOT_FOUND"


def test_모르는_동작은_거부한다():
    with pytest.raises(runtime.HwpxNodeError) as exc:
        runtime.run("삭제해줘")
    assert exc.value.reason == "HWPX_BAD_MODE"


def test_살펴볼_파일이_없으면_무엇을_해야_할지_알려준다():
    """경로를 물어보지 않는다 — 앞 노드를 연결하거나 파일을 고르라고 안내한다."""
    with pytest.raises(runtime.HwpxNodeError) as exc:
        runtime.run("inspect", source_artifact_id="")
    assert exc.value.reason == "HWPX_NO_SOURCE"
    assert "연결" in str(exc.value) or "골라" in str(exc.value)
    assert "경로" not in str(exc.value), "사용자에게 서버 경로를 묻지 않는다"


def test_파일은_artifact_로만_지정한다():
    """경로 문자열을 받는 인자가 남아 있으면 안 된다."""
    import inspect as _inspect

    params = _inspect.signature(runtime.run).parameters
    assert "source_artifact_id" in params
    assert "source_path" not in params


def test_artifact_해석은_소유_검증을_거친다(monkeypatch):
    """남의 파일을 열 수 없어야 한다 — artifacts.resolve 가 그 판정을 한다."""
    import artifacts

    calls = {}

    class _Resolved:
        path = "/tmp/x.hwpx"

    def fake_resolve(db, artifact_id, **kwargs):
        calls.update({"artifact_id": artifact_id, **kwargs})
        return _Resolved()

    monkeypatch.setattr(artifacts, "resolve", fake_resolve)
    runtime.resolve_source(object(), "a1", owner_user_id=7, project_id=3)
    assert calls["artifact_id"] == "a1"
    assert calls["owner_user_id"] == 7, "소유자를 넘기지 않으면 남의 파일이 열린다"


# ── 노드 정의와의 정합 ──────────────────────────────────────────────────

def test_정의가_선언한_mode와_런타임이_아는_mode가_같다():
    import node_definition

    definition = node_definition.get_definition("hwpxDocumentNode")
    declared = {option.value for option in definition.field("mode").options}
    assert declared == set(runtime.MODES)


def test_정의가_외부로_나가지_않는_노드로_선언돼_있다():
    import node_definition

    definition = node_definition.get_definition("hwpxDocumentNode")
    assert definition.sideEffect == "none"
    assert definition.connector is None
    assert "network" not in definition.capabilities


def test_정화_규칙이_자동으로_파생된다():
    import community_sanitize as sanitize

    assert sanitize.rule_for("hwpxDocumentNode") is not None


# ── 긴 표가 쪽을 넘어 이어진다 ──────────────────────────────────────────
# 2026-08-30 한/글 확인에서 40행 표가 20행쯤에서 잘려 보였다. 데이터는 41행이 다 들어 있었고
# **표시만** 잘렸다 — 라이브러리가 표를 `treatAsChar="1"`(글자처럼 취급)로 앵커해서 쪽을 넘어
# 나뉘지 못한 것이다.

def _table_xml(tmp_path, rows):
    import re
    import zipfile

    out = str(tmp_path / "t.hwpx")
    hwpx.build({"blocks": [{"type": "table", "columns": ["a", "b"],
                            "rows": [["1", "2"]] * rows}]}, out)
    with zipfile.ZipFile(out) as archive:
        xml = archive.read("Contents/section0.xml").decode("utf-8")
    return xml, re.search(r"<hp:tbl\b[^>]*>", xml).group(0), re.search(r"<hp:pos\b[^>]*>", xml).group(0)


def test_표가_글자처럼_취급되지_않는다(tmp_path):
    """`treatAsChar=1` 이면 표 전체가 한 글자처럼 다뤄져 쪽을 넘어 나뉘지 못한다."""
    _xml, _tbl, pos = _table_xml(tmp_path, 40)
    assert 'treatAsChar="0"' in pos


def test_표가_셀_경계에서_나뉜다(tmp_path):
    _xml, tbl, _pos = _table_xml(tmp_path, 40)
    assert 'pageBreak="CELL"' in tbl


def test_긴_표는_머리글을_쪽마다_반복한다(tmp_path):
    """둘째 쪽부터 무슨 열인지 알 수 없으면 잘린 것과 다를 바 없다."""
    _xml, tbl, _pos = _table_xml(tmp_path, 40)
    assert 'repeatHeader="1"' in tbl


def test_행이_하나도_빠지지_않는다(tmp_path):
    """표시 문제와 데이터 문제를 구분한다 — 데이터는 원래도 온전했다."""
    xml, tbl, _pos = _table_xml(tmp_path, 40)
    assert xml.count("<hp:tr") == 41, "머리글 + 40행"
    assert 'rowCnt="41"' in tbl
