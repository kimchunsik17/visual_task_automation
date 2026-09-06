"""httpRequestNode 의 headers 가 dict 일 때 생성 코드가 그것을 파이썬 리터럴로 넘기는지.

예전에는 str(dict) 로 문자열화해 홑따옴표 repr 이 됐고, 런타임 _parse_json_field 가 "유효한 JSON 이 아니다"
로 실행을 막았다(2026-09-06, 시연 WF2 의 X-Goog-Api-Key 헤더에서 발견 — dry_run 은 컴파일만 해서 못 잡는다).
자격증명 헤더는 {{API_CENTER:*}} 치환이 dict 값에만 되므로 dict 로 두어야 하고, 그 dict 가 그대로 살아야 한다.
"""
import ast

from graph import compile_workflow


def _graph(headers):
    nodes = [
        {"id": "s", "type": "startNode", "data": {}, "position": {"x": 0, "y": 0}},
        {"id": "h", "type": "httpRequestNode",
         "data": {"method": "GET", "url": "https://example.com/api", "headers": headers, "body": ""},
         "position": {"x": 0, "y": 0}},
        {"id": "o", "type": "outputNode", "data": {}, "position": {"x": 0, "y": 0}},
    ]
    edges = [{"id": "e1", "source": "s", "target": "h"}, {"id": "e2", "source": "h", "target": "o"}]
    return nodes, edges


def test_dict_headers_survive_as_python_literal():
    source = compile_workflow(*_graph({"X-Goog-Api-Key": "{{API_CENTER:youtube_data_api}}"}))
    ast.parse(source)                                            # 유효한 파이썬
    assert "headers={'X-Goog-Api-Key': '{{API_CENTER:youtube_data_api}}'}" in source
    assert '"{\'X-Goog-Api-Key\'' not in source                  # 문자열화된 repr 이 아니다


def test_string_headers_keep_the_old_shape():
    source = compile_workflow(*_graph('{"Accept": "application/json"}'))
    ast.parse(source)
    assert 'headers="{\\"Accept\\": \\"application/json\\"}"' in source
