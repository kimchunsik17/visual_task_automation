import datetime
from node_registry import node_registry
from meta_agent import PLACEHOLDER_URL
from .action_nodes import _emit_needs_input

@node_registry.register('jsonParserNode')
def generate_json_parser_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- JSON Parser Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    mode = node.get('data', {}).get('mode', 'parse')
    extract_key = node.get('data', {}).get('extractKey', '')
    
    lines.append(f"{indent}import json")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    parser_in = {prev_res_var if prev_res_var else 'last_result'}")
    
    if mode == 'parse':
        lines.append(f"{indent}    parser_out_{node_id} = json.loads(_strip_json_fence(parser_in))")
    elif mode == 'stringify':
        lines.append(f"{indent}    parser_out_{node_id} = json.dumps(parser_in, ensure_ascii=False, indent=2)")
    elif mode == 'extract':
        lines.append(f"{indent}    if isinstance(parser_in, str):")
        lines.append(f"{indent}        tmp_dict = json.loads(_strip_json_fence(parser_in))")
        lines.append(f"{indent}    else:")
        lines.append(f"{indent}        tmp_dict = parser_in")
        lines.append(f"{indent}    parser_out_{node_id} = tmp_dict.get('{extract_key}', '')")
    else:
        lines.append(f"{indent}    parser_out_{node_id} = parser_in")
    
    lines.append(f"{indent}except Exception as e:")
    lines.append(f"{indent}    parser_out_{node_id} = f'JSON Parser Error: {{str(e)}}'")
    
    lines.append(f"{indent}last_result = parser_out_{node_id}")
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"parser_out_{node_id}", visited=visited)


def _emit_db_guidance(node_id, node_type, indent, lines, forward_edges, generate_block_fn, active_llm_id, visited, out_var, message, error):
    """접속 정보가 실행 가능한 상태가 아닐 때: 접속을 시도하지 않고 안내 문구를 결과로 흘려보낸다
    (_emit_needs_input 과 같은 규약 — 워크플로우는 계속 진행된다)."""
    lines.append(f"{indent}{out_var} = {message!r}")
    lines.append(f"{indent}last_result = {out_var}")
    # 두 경우(평문 차단, reference 미해석) 모두 사용자 조치는 같다 — API 센터에 Database 자격증명 등록.
    # 안내 문구는 그대로 보여주고, 실행 로그에는 CREDENTIAL_MISSING 으로 구조화한다(ADR-0016).
    lines.append(
        f"{indent}log_step('{node_id}', '{node_type}', _start_{node_id}, result=last_result, "
        f"error=_make_node_error('CREDENTIAL_MISSING', field='connectionString', user_message={message!r}, "
        f"safe_details={{'provider': 'database', 'service': 'Database'}}, node_type='{node_type}', node_id='{node_id}', internal_message={error!r}))"
    )
    for target_id, handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=out_var, visited=visited)


@node_registry.register('databaseNode')
def generate_database_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # 실행 로직은 db_query_runtime.run_readonly_query 에 있다(P0, INCOMPLETE_NODE_STRUCTURE_REVIEW
    # §4.2). 예전에는 여기서 SQLAlchemy 호출을 문자열로 조립했는데, 그 구조에서는 read-only
    # 세션·timeout·행 제한을 넣을 수 없었고 결과 없는 쿼리를 commit 까지 했다.
    #
    # 접속 문자열은 API 센터 reference 만 허용한다. 이 시점(codegen)의 값은 세 가지뿐이다:
    #   - graph.run_workflow 가 API 센터에서 복호화해 치환한 실제 URI  → 실행
    #   - 치환되지 않고 남은 reference(자격증명 미등록)                → 등록 안내
    #   - LEGACY_PLAINTEXT_SENTINEL(노드에 평문으로 저장돼 있던 값)     → 지원 중단 안내
    # 평문 → sentinel 치환은 graph.run_workflow 가 실행 직전에 수행하므로, 어떤 실행 경로
    # (에디터/스케줄/웹훅/앱)로 와도 평문 접속 문자열은 여기 도달하지 않는다.
    from db_query_runtime import LEGACY_PLAINTEXT_SENTINEL

    lines.append(f"{indent}# --- Database Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    conn_str = node.get('data', {}).get('connectionString', '')
    query_raw = node.get('data', {}).get('query', '')

    if not conn_str or conn_str == PLACEHOLDER_URL:
        _emit_needs_input(node_id, node['type'], indent, lines, forward_edges, generate_block_fn, active_llm_id, visited, f"db_out_{node_id}", field='connectionString')
        return
    if conn_str == LEGACY_PLAINTEXT_SENTINEL:
        _emit_db_guidance(
            node_id, node['type'], indent, lines, forward_edges, generate_block_fn, active_llm_id, visited,
            f"db_out_{node_id}",
            "⚠️ 보안을 위해 노드에 직접 입력한 DB 접속 문자열은 더 이상 실행되지 않습니다. "
            "API 센터에 'Database' 자격증명(읽기 전용 계정 권장)을 등록하면 이 노드가 자동으로 사용합니다. "
            f"(노드: {node_id})",
            "노드에 평문으로 저장된 접속 문자열은 실행이 차단됨",
        )
        return
    def literal(value):
        return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    from db_query_runtime import v2_enabled, parse_allowed_schemas, DEFAULT_MAX_ROWS, DEFAULT_TIMEOUT_SECONDS
    data = node.get('data', {}) or {}

    if v2_enabled():
        # Database Query v2(ADR-0017): 생성 코드는 reference 만 갖는다. 실행기가 소유자(__owner_user_id__)
        # 기준으로 API 센터 자격증명을 해석·복호화하므로 접속 URI 는 생성 소스·로그 어디에도 없다.
        # 자격증명 미등록/중복도 실행기가 CREDENTIAL_MISSING / VALIDATION_REQUIRED 로 돌려준다.
        from database_credentials import is_reference
        from db_query_parameters import normalize_definitions
        if not is_reference(conn_str):
            _emit_db_guidance(
                node_id, node['type'], indent, lines, forward_edges, generate_block_fn, active_llm_id, visited,
                f"db_out_{node_id}",
                "⚠️ 이 노드의 DB 연결 값이 API 센터 자격증명 reference 가 아닙니다. "
                f"노드에서 'API 센터 자격증명 사용'을 선택해주세요. (노드: {node_id})",
                "connectionString 이 reference 형식이 아님",
            )
            return
        params = normalize_definitions(data.get('parameters'))
        try:
            max_rows = int(data.get('maxRows') or DEFAULT_MAX_ROWS)
        except (TypeError, ValueError):
            max_rows = DEFAULT_MAX_ROWS
        try:
            timeout_seconds = int(data.get('timeoutSeconds') or DEFAULT_TIMEOUT_SECONDS)
        except (TypeError, ValueError):
            timeout_seconds = DEFAULT_TIMEOUT_SECONDS
        schemas = parse_allowed_schemas(data.get('allowedSchemas'))
        output_format = 'result' if data.get('outputFormat') == 'result' else 'rows'
        upstream = prev_res_var if prev_res_var else 'last_result'
        lines.append(f"{indent}from db_query_runtime import run_readonly_query_result")
        lines.append(f"{indent}_db_res_{node_id} = run_readonly_query_result(")
        lines.append(f"{indent}    credential_ref=\"{literal(conn_str)}\", owner_user_id=__owner_user_id__, db=db,")
        lines.append(f"{indent}    query=\"{literal(query_raw)}\", parameters={params!r},")
        lines.append(f"{indent}    upstream=(str({upstream}) if {upstream} is not None else ''),")
        lines.append(f"{indent}    max_rows={max_rows}, timeout_seconds={timeout_seconds}, allowed_schemas={schemas!r},")
        lines.append(f"{indent}    output_format='{output_format}', node_id='{node_id}')")
    else:
        # v1 경로(되돌리기용): graph.run_workflow 가 치환한 URI literal 을 그대로 넘긴다.
        if conn_str.startswith('{{API_CENTER:'):
            _emit_db_guidance(
                node_id, node['type'], indent, lines, forward_edges, generate_block_fn, active_llm_id, visited,
                f"db_out_{node_id}",
                "⚠️ API 센터에 'Database' 자격증명이 아직 등록되지 않았습니다. "
                f"API 센터에서 읽기 전용 접속 문자열을 등록해주세요. (노드: {node_id})",
                "database credential 미등록",
            )
            return
        lines.append(f"{indent}from db_query_runtime import run_readonly_query_result")
        lines.append(f"{indent}_db_res_{node_id} = run_readonly_query_result(\"{literal(conn_str)}\", \"{literal(query_raw)}\", node_id='{node_id}')")

    # 실행기는 NodeResult 를 돌려준다(ADR-0016). 노드 사이 값은 아직 문자열이라 하류에는 str() 표시
    # 문자열(outputFormat 에 따라 행 배열 또는 ok/data/error JSON)을 넘기고, 실행 로그에는 NodeResult 를
    # 실어 status/error 가 구조화되게 한다.
    lines.append(f"{indent}db_out_{node_id} = str(_db_res_{node_id})")
    lines.append(f"{indent}last_result = db_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_db_res_{node_id})")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"db_out_{node_id}", visited=visited)
