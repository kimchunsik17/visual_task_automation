import datetime
import json
from node_bindings import bound_expr, is_bound
from node_registry import node_registry
from meta_agent import PLACEHOLDER_URL


def _emit_needs_input(node_id, node_type, indent, lines, forward_edges, generate_block_fn, active_llm_id, visited, out_var, field='url'):
    """url이 아직 PLACEHOLDER_URL(실제 값 미입력)인 경우 공통으로 쓰는 블록.
    진짜 요청을 시도하지 않고, 사용자에게 채팅창을 참고하라는 안내로 대체한 뒤 다음 노드로 넘어간다.
    실행 로그에는 VALIDATION_REQUIRED(field) 로 남아 Inspector 가 그 입력으로 바로 이동할 수 있다(ADR-0016)."""
    lines.append(f"{indent}{out_var} = '⚠️ 채워넣어야 하는 필드가 있습니다. AI와 대화하는 창을 참고해주세요. (노드: {node_id})'")
    lines.append(f"{indent}last_result = {out_var}")
    lines.append(
        f"{indent}log_step('{node_id}', '{node_type}', _start_{node_id}, result=last_result, "
        f"error=_make_node_error('VALIDATION_REQUIRED', field='{field}', "
        f"user_message='채워넣어야 하는 필드가 있습니다. AI와 대화하는 창을 참고해주세요.', "
        f"safe_details={{'field': '{field}'}}, node_type='{node_type}', node_id='{node_id}', "
        f"internal_message='{field} 가 아직 채워지지 않음(PLACEHOLDER_URL)'))"
    )
    for target_id, handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=out_var, visited=visited)


@node_registry.register('httpRequestNode')
def generate_http_request_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # 실행 로직은 connectors/services/http_request.py 에 있다(ADR-0009). 예전에는 여기서
    # requests 호출과 status_code 비교를 40여 줄로 조립했는데, 그러면 재시도도 없고 실패가
    # 한 줄 문자열로 뭉개지며 Mock 탭에서 갈아끼울 수도 없었다.
    lines.append(f"{indent}# --- HTTP Request Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    data = node.get('data', {})
    method = data.get('method', 'GET')
    url = data.get('url', '')
    headers_str = str(data.get('headers', '') or '')
    body_str = str(data.get('body', '') or '')

    if url == PLACEHOLDER_URL:
        _emit_needs_input(node_id, node['type'], indent, lines, forward_edges, generate_block_fn, active_llm_id, visited, f"req_out_{node_id}")
        return

    def literal(value):
        return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    lines.append(f"{indent}from connectors.services import http_request as _http")
    lines.append(f"{indent}from connectors.errors import ConnectorError as _ConnectorError")
    lines.append(f"{indent}from connectors import mock_runtime as _mock_runtime")
    lines.append(f"{indent}import node_definition as _node_definition")
    # URL 을 비워두면 직전 노드의 출력을 주소로 쓴다(예전과 동일한 규약).
    # 바인딩이 걸려 있으면 리터럴이 아니라 런타임 조회다(계획 §4).
    if url or is_bound(node, 'url'):
        lines.append(f"{indent}_http_url_{node_id} = {bound_expr(node, node_id, 'url')}")
    else:
        lines.append(f"{indent}_http_url_{node_id} = str({prev_res_var if prev_res_var else 'last_result'}).strip()")
    lines.append(f"{indent}_http_err_{node_id} = None")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node['type']}'):")
    lines.append(f"{indent}        req_out_{node_id} = _http.call(")
    lines.append(f"{indent}            _node_definition.get_definition('httpRequestNode'),")
    lines.append(f"{indent}            method=\"{literal(method)}\", url=_http_url_{node_id},")
    lines.append(f"{indent}            headers=\"{literal(headers_str)}\", body={bound_expr(node, node_id, 'body')})")
    lines.append(f"{indent}except _ConnectorError as _e:")
    lines.append(f"{indent}    print(f'[HTTP Request 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    req_out_{node_id} = f'HTTP Request Error: {{_e.user_message}}'")
    # 범용 HTTP 는 조회/발송을 구분할 수 없어 connector 맥락으로 승격한다(ADR-0016 ERROR-2).
    lines.append(f"{indent}    _http_err_{node_id} = _e.to_node_error(domain='connector', node_type='httpRequestNode', node_id='{node_id}')")
    lines.append(f"{indent}last_result = req_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result, error=_http_err_{node_id})")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"req_out_{node_id}", visited=visited)


@node_registry.register('webCrawlerNode')
def generate_web_crawler_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    """웹 페이지 한 장을 읽어 **구조화해서** 넘긴다 (계획 §6.5).

    예전에는 `soup.get_text(separator=' ')[:5000]` 이 전부여서 메뉴·광고·푸터가 본문과 한
    덩어리로 붙었다. 지금은 `web_extract` 가 제목·발행일·본문·링크를 갈라 준다.

    요청 자체는 `url_guard.fetch_text` 가 맡는다 — SSRF 검사에 더해 robots.txt, 호스트별
    최소 간격, 하루 요청 상한이 거기 있다. **`db` 를 넘겨야 상한이 실제로 센다.**
    """
    data = node.get('data', {})
    lines.append(f"{indent}# --- Web Crawler Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    url = data.get('url', '').replace('\\', '\\\\').replace('"', '\\"')

    if url == PLACEHOLDER_URL:
        _emit_needs_input(node_id, node['type'], indent, lines, forward_edges, generate_block_fn, active_llm_id, visited, f"crawl_res_{node_id}")
        return

    output = str(data.get('output') or 'text')
    if output not in ('text', 'structured', 'links'):
        output = 'text'
    try:
        max_chars = max(200, min(int(data.get('maxChars') or 5000), 50000))
    except (TypeError, ValueError):
        max_chars = 5000
    # robots.txt 는 기본으로 지킨다. 끄는 것은 명시적인 선택이어야 한다.
    respect_robots = data.get('respectRobots') is not False

    lines.append(f"{indent}import url_guard")
    lines.append(f"{indent}import web_extract")
    lines.append(f"{indent}import json as _json")
    lines.append(f"{indent}try:")
    if url or is_bound(node, 'url'):
        lines.append(f"{indent}    target_url_{node_id} = {bound_expr(node, node_id, 'url')}")
    elif prev_res_var:
        lines.append(f"{indent}    target_url_{node_id} = str({prev_res_var}).strip()")
    else:
        lines.append(f"{indent}    raise ValueError('No URL provided for Web Crawler')")
    lines.append(f"{indent}    _html_{node_id} = url_guard.fetch_text(")
    lines.append(f"{indent}        target_url_{node_id}, respect_robots={respect_robots!r}, db=db)")
    lines.append(f"{indent}    _page_{node_id} = web_extract.extract(")
    lines.append(f"{indent}        _html_{node_id}, url=target_url_{node_id}, max_chars={max_chars})")
    if output == 'structured':
        lines.append(f"{indent}    crawl_res_{node_id} = _json.dumps(_page_{node_id}, ensure_ascii=False)")
    elif output == 'links':
        lines.append(f"{indent}    crawl_res_{node_id} = _json.dumps(_page_{node_id}['links'], ensure_ascii=False)")
    else:
        lines.append(f"{indent}    crawl_res_{node_id} = web_extract.as_text(_page_{node_id})")
    # 막힌 이유는 사용자가 고칠 수 있는 것들이다(robots·상한·내부 주소). 문구를 그대로 보여준다.
    lines.append(f"{indent}except url_guard.UrlBlocked as e:")
    lines.append(f"{indent}    crawl_res_{node_id} = '수집하지 않았습니다: ' + str(e)")
    # 오류가 데이터로 위장하지 않도록 meta 채널에 남긴다(ADR-0025 §B). 하류 문자열은
    # 기존 관례("수집하지 않았습니다: ...")를 유지하되, LLM 입력 합성기가 이 meta 를 보고
    # "자료가 아니라 오류 안내문"이라는 힌트를 붙인다.
    lines.append(f"{indent}    _set_node_meta('{node_id}', status='error', error_code='URL_BLOCKED', error_message=str(e))")
    lines.append(f"{indent}except Exception as e:")
    lines.append(f"{indent}    crawl_res_{node_id} = 'Crawling failed: ' + str(e)")
    lines.append(f"{indent}    _set_node_meta('{node_id}', status='error', error_code='CRAWL_FAILED', error_message=str(e))")
    if prev_res_var:
        lines.append(f"{indent}last_result = str({prev_res_var}) + \"\\n\\n[Crawled Data]\\n\" + crawl_res_{node_id}")
    else:
        lines.append(f"{indent}last_result = crawl_res_{node_id}")

    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)


@node_registry.register('pythonNode')
def generate_python_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # 실행은 python_runtime.run_isolated 가 별도 프로세스에서 한다(§4.15 PYEXEC-1, ADR-0019).
    # 예전에는 사용자 코드를 이 생성 소스에 그대로 인라인했다. 허용 목록(workflow_security)이
    # 접근을 막고 있었지만 **자원 한도가 없어서** `10 ** 10 ** 10` 한 줄이면 워커가 멈췄고,
    # 코드가 db 세션이 있는 네임스페이스 바로 옆에서 돌아 방어가 한 겹뿐이었다.
    from python_runtime import isolation_enabled

    user_code = node.get('data', {}).get('code', '')
    upstream = prev_res_var if prev_res_var else 'last_result'
    lines.append(f"{indent}# --- Python Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}input_data = {upstream}")

    if isolation_enabled():
        # 코드는 **문자열 리터럴**로만 들어간다 — 생성 소스의 일부가 아니다.
        lines.append(f"{indent}from python_runtime import run_isolated as _run_isolated")
        lines.append(f"{indent}_py_res_{node_id} = _run_isolated({user_code!r}, input_data, node_id='{node_id}')")
        # 실패해도 흐름을 끊지 않는다 — 이 노드만 오류로 기록되고 하류는 표시 문자열을 받는다
        # (databaseNode·발송 노드와 같은 관례).
        lines.append(f"{indent}res_text_{node_id} = _py_res_{node_id}.data if _py_res_{node_id}.ok else str(_py_res_{node_id})")
        lines.append(f"{indent}last_result = res_text_{node_id}")
        lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_py_res_{node_id})")
    else:
        # 되돌리기 경로(PYTHON_NODE_ISOLATION=0). 허용 목록과 정적 상한은 여기서도 그대로 걸린다.
        lines.append(f"{indent}output_data = input_data # Default fallback")
        if user_code.strip():
            for line in user_code.split('\n'):
                lines.append(f"{indent}{line}")
        lines.append(f"{indent}res_text_{node_id} = output_data")
        lines.append(f"{indent}last_result = res_text_{node_id}")
        lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")

    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register('delayNode')
def generate_delay_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Delay Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    seconds = node.get('data', {}).get('seconds', 5)
    lines.append(f"{indent}import time")
    lines.append(f"{indent}print(f'Waiting for {seconds} seconds...')")
    lines.append(f"{indent}time.sleep(float({seconds}))")
    
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)


@node_registry.register('dynamicInputNode')
@node_registry.register('webhookNode')
def generate_webhook_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # webhookNode는 dynamicInputNode와 달리 "사람이 보는 라벨 붙은 값"이 아니라 외부 시스템이 보낸
    # 원본 요청 바디 그 자체다. 예전엔 이 함수를 dynamicInputNode와 공유해서 "[라벨]:\n원본내용"처럼
    # 접두사를 붙였는데, 그러면 바로 뒤에 jsonParserNode(parse)가 오는 아주 흔한 패턴(웹훅 JSON 바디
    # 파싱)에서 그 접두사 때문에 매번 파싱이 깨지고, "JSON Parser Error: ..."라는 에러 문자열이
    # 사용자 메시지인 것처럼 그대로 하류 LLM에게 새어나가는 문제가 있었다. 그래서 웹훅은 라벨 없이
    # 원본 페이로드를 그대로 넘긴다(파일 입력 모드도 웹훅에는 해당 없어 제거).
    lines.append(f"{indent}# --- Webhook Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    test_val = node.get('data', {}).get('testValue', '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    lines.append(f"{indent}dyn_input_{node_id} = kwargs.get('{node_id}')")
    lines.append(f"{indent}if dyn_input_{node_id} is None:")
    lines.append(f"{indent}    dyn_input_{node_id} = kwargs.get('default_input', \"{test_val}\" if \"{test_val}\" else '<<No input provided>>')")

    if prev_res_var:
        lines.append(f"{indent}last_result = f\"{{{prev_res_var}}}\\n\\n{{dyn_input_{node_id}}}\"")
    else:
        lines.append(f"{indent}last_result = str(dyn_input_{node_id})")

    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)


@node_registry.register('dynamicInputNode')
def generate_dynamic_input_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Dynamic Input Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    input_label = node.get('data', {}).get('inputLabel', 'Input').replace('\\', '\\\\').replace('"', '\\"')
    input_type = node.get('data', {}).get('inputType', 'text')
    test_val = node.get('data', {}).get('testValue', '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    lines.append(f"{indent}dyn_input_{node_id} = kwargs.get('{node_id}')")
    lines.append(f"{indent}if dyn_input_{node_id} is None:")
    lines.append(f"{indent}    dyn_input_{node_id} = kwargs.get('default_input', \"{test_val}\" if \"{test_val}\" else '<<No input provided>>')")

    if input_type == 'file':
        # 파일 경로는 업로드 루트 안이어야 한다(2026-08-31 적대적 리뷰: 확장자·경로 제한이 없어
        # 실행 payload 로 backend/.env 를 넘기면 그대로 읽혔다). _safe_user_path 가 밖이면 None.
        lines.append(f"{indent}file_content_{node_id} = ''")
        lines.append(f"{indent}_dyn_path_{node_id} = _safe_user_path(str(dyn_input_{node_id}))")
        lines.append(f"{indent}try:")
        lines.append(f"{indent}    if _dyn_path_{node_id} is not None and _dyn_path_{node_id}.is_file():")
        lines.append(f"{indent}        with open(_dyn_path_{node_id}, 'r', encoding='utf-8', errors='replace') as f:")
        lines.append(f"{indent}            file_content_{node_id} = f.read()")
        lines.append(f"{indent}        dyn_input_{node_id} = file_content_{node_id}")
        lines.append(f"{indent}    elif _dyn_path_{node_id} is None:")
        lines.append(f"{indent}        dyn_input_{node_id} = '허용되지 않은 파일 경로입니다(업로드한 파일만 읽을 수 있습니다)'")
        lines.append(f"{indent}except Exception as e:")
        lines.append(f"{indent}    dyn_input_{node_id} = f'Error reading file: {{str(e)}}'")

    if prev_res_var:
        lines.append(f"{indent}last_result = f\"{{{prev_res_var}}}\\n\\n[{input_label}]:\\n{{dyn_input_{node_id}}}\"")
    else:
        lines.append(f"{indent}last_result = f\"[{input_label}]:\\n{{dyn_input_{node_id}}}\"")

    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)
