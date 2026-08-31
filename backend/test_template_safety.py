"""문서 서식 노드의 파일 안전 테스트 (한국형 서비스 노드 계획 "Phase 0 이전" 1·2번).

예전에 두 가지가 잘못돼 있었다.

1. **템플릿 덮어쓰기.** `templateAnalyzerNode`/`fileModifierNode` 는 기존 `{{key}}` 와 이번
   데이터 키의 겹침이 절반 미만이면 `generate_hwpx_template(...)` 을 불렀는데, 그 첫 인자가
   출력 경로가 아니라 **템플릿 경로 자체**였다. 사용자가 올린 서식이 빈칸만 있는 새 문서로
   교체되고 되돌릴 수 없었다.
2. **`mimetype` 규칙 파손.** 치환 후 전체를 `ZIP_DEFLATED` 로 다시 썼다. HWPX 는 OCF 계열이라
   `mimetype` 이 첫 entry 이면서 무압축(STORED)이어야 한다.
"""

import hashlib
import os
import zipfile

import pytest

from graph import run_workflow
from template_generator import generate_hwpx_template


def _node(node_id, node_type, data=None):
    return {"id": node_id, "type": node_type, "data": data or {}, "position": {"x": 0, "y": 0}}


def _edge(edge_id, source, target):
    return {"id": edge_id, "source": source, "target": target}


def _sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


@pytest.fixture
def template(tmp_path, monkeypatch):
    """partyName/amount 빈칸이 있는 서식. 사용자가 올린 파일이라고 본다.

    노드가 경로를 uploads/ 밑으로 정규화하므로 작업 디렉터리를 tmp 로 옮겨 실제 uploads 를
    건드리지 않는다.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uploads").mkdir()
    path = "uploads/contract.hwpx"
    generate_hwpx_template(path, ["partyName", "amount"], title="계약서")
    return path


def _fill(template_path, value_json, output_path):
    nodes = [_node("v1", "valueNode", {"value": value_json}),
             _node("f1", "fileModifierNode",
                   {"template_path": template_path, "output_path": output_path}),
             _node("o1", "outputNode")]
    edges = [_edge("e1", "v1", "f1"), _edge("e2", "f1", "o1")]
    result, _usage, _logs = run_workflow(nodes, edges)
    return str(result)


def test_정상_채움은_입력_서식을_건드리지_않는다(template):
    before = _sha256(template)
    _fill(template, '{"partyName": "주식회사 예시", "amount": "5,000,000원"}', "uploads/out.hwpx")
    assert _sha256(template) == before, "입력 서식이 실행 중에 변경됐다"


def test_키가_안_맞아도_입력_서식을_덮어쓰지_않는다(template):
    """예전에 데이터가 사라지던 바로 그 경로다."""
    before = _sha256(template)
    _fill(template, '{"완전히": "다른", "키": "들"}', "uploads/out.hwpx")
    assert _sha256(template) == before, "키 불일치 시 입력 서식이 새 문서로 교체됐다"


def test_키가_안_맞으면_조용히_넘어가지_않고_알린다(template):
    """공용 엔진 이관 뒤로는 '못 채운 빈칸을 이름으로' 짚는다 — 예전의 겹침 비율 추정보다 정확하다."""
    out = _fill(template, '{"완전히": "다른", "키": "들"}', "uploads/out.hwpx")
    assert "채우지 못한 빈칸" in out
    # 무엇이 남았고 무엇을 받았는지 둘 다 보여야 사용자가 고칠 수 있다
    assert "partyName" in out and "amount" in out
    assert "완전히" in out


def test_출력_hwpx_의_mimetype_이_첫_entry_이고_무압축이다(template):
    _fill(template, '{"partyName": "주식회사 예시", "amount": "5,000,000원"}', "uploads/out.hwpx")
    assert os.path.exists("uploads/out.hwpx")
    infos = zipfile.ZipFile("uploads/out.hwpx").infolist()
    assert infos[0].filename == "mimetype", "mimetype 이 첫 entry 가 아니다"
    assert infos[0].compress_type == zipfile.ZIP_STORED, "mimetype 이 압축됐다"


def test_출력_hwpx_의_나머지_entry_압축방식이_원본과_같다(template):
    original = {i.filename: i.compress_type for i in zipfile.ZipFile(template).infolist()}
    _fill(template, '{"partyName": "주식회사 예시", "amount": "5,000,000원"}', "uploads/out.hwpx")
    produced = {i.filename: i.compress_type for i in zipfile.ZipFile("uploads/out.hwpx").infolist()}
    assert produced == original


def test_값이_실제로_채워진다(template):
    _fill(template, '{"partyName": "주식회사 예시", "amount": "5,000,000원"}', "uploads/out.hwpx")
    section = zipfile.ZipFile("uploads/out.hwpx").read("Contents/section0.xml").decode("utf-8")
    assert "주식회사 예시" in section
    assert "{{partyName}}" not in section


def test_서식이_없으면_만들어_쓰는_동작은_그대로다(tmp_path, monkeypatch):
    """파일이 없을 때의 즉석 생성은 잃을 것이 없으므로 유지한다."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uploads").mkdir()
    out = _fill("uploads/없는서식.hwpx", '{"name": "홍길동"}', "uploads/out.hwpx")
    assert "Error" not in out
    section = zipfile.ZipFile("uploads/out.hwpx").read("Contents/section0.xml").decode("utf-8")
    assert "홍길동" in section
