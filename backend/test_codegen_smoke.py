"""코드젠 스모크 — 노드 생성기가 컴파일되는 파이썬을 만드는지 (3단계).

`compile_workflow` 는 노드별 생성기를 모아 하나의 파이썬 소스를 만들고 그 소스를 `exec` 한다.
그래서 **한 노드의 생성기가 만든 문법 오류는 워크플로우 전체를 실행 불가로 만든다** — 그
노드만 실패하는 것이 아니다. 여기서 지키는 문장 둘:

  1. 등록된 모든 노드 타입이 최소 그래프에서 컴파일된다.
  2. 사용자가 넣을 수 있는 값(따옴표·역슬래시·경로)을 **경로 필드**에 넣어도 컴파일된다.

②가 실제 회귀를 잡았다: templateAnalyzer·fileModifier·posterGenerator 의 경로 필드가
이스케이프를 한 뒤 `\\→/` 치환으로 되풀어서(`\\"` → `/"`), 따옴표가 든 경로가 생성 코드를
통째로 깨뜨렸다 — 한 노드의 잘못된 경로가 워크플로우 전체 컴파일을 실패시킨 것이다.

※ 모든 노드의 **모든** 필드에 악성값을 넣는 전수 스모크는 여기 없다. 노드마다 필드 형태가
   달라(list 는 dict 목록, jsonSchema 는 JSON 문자열 …) 타당한 값을 형태별로 만들어줘야 하고,
   그건 3단계의 별도 작업이다. 그 과정에서 이스케이프 후보가 더 나오면 그때 넓힌다.
"""

from __future__ import annotations

import ast

import pytest
from dotenv import load_dotenv

load_dotenv()

import graph  # noqa: E402
import node_generators  # noqa: E402,F401  (등록 부작용)
from node_registry import node_registry  # noqa: E402

ALL_TYPES = sorted(node_registry._generators.keys())

# 사람이 실제로 쓸 수 있고, 옛 이스케이프면 반드시 깨지는 경로 값.
NASTY_PATH = 'q"인용" C:\\temp\\a.hwpx'

# 경로를 문자열로 받아 생성 코드에 박는 노드·필드. 이번에 고친 회귀 지점이다.
PATH_FIELDS = [
    ("templateAnalyzerNode", "template_path"),
    ("fileModifierNode", "template_path"),
    ("fileModifierNode", "output_path"),
    ("posterGeneratorNode", "output_path"),
    ("hwpxDocumentNode", "output_path"),
]


def _compile(node_type: str, data: dict) -> str:
    nodes = [
        {"id": "s", "type": "startNode", "data": {}, "position": {"x": 0, "y": 0}},
        {"id": "n", "type": node_type, "data": data, "position": {"x": 1, "y": 0}},
        {"id": "o", "type": "outputNode", "data": {}, "position": {"x": 2, "y": 0}},
    ]
    edges = [{"id": "e1", "source": "s", "target": "n"},
             {"id": "e2", "source": "n", "target": "o"}]
    return graph.compile_workflow(nodes, edges)


def test_the_registry_has_the_expected_breadth():
    """개수가 크게 줄면 등록이 깨진 것이다(import 부작용에 의존하므로)."""
    assert len(ALL_TYPES) >= 45, f"등록된 노드가 {len(ALL_TYPES)}종뿐 — 등록이 깨졌다"


@pytest.mark.parametrize("node_type", ALL_TYPES)
def test_every_node_compiles_in_a_minimal_graph(node_type):
    """start → node → output. 데이터 없이도 생성기가 문법에 맞는 소스를 내야 한다."""
    src = _compile(node_type, {})
    ast.parse(src)


@pytest.mark.parametrize("node_type,field", PATH_FIELDS)
def test_path_fields_survive_quotes_and_backslashes(node_type, field):
    """따옴표·역슬래시가 든 경로로도 컴파일돼야 한다(이스케이프 회귀). 되돌리면 여기서 잡힌다."""
    src = _compile(node_type, {field: NASTY_PATH})
    try:
        compile(src, "<generated>", "exec")
    except SyntaxError as exc:
        pytest.fail(f"{node_type}.{field}: 경로 이스케이프가 생성 코드를 깨뜨렸다 — {exc.msg}")
