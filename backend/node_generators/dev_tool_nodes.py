"""node_generators/dev_tool_nodes.py — 개발 편의 노드 4종의 실행 코드 생성 (백로그 34 DEV-2, ADR-0033).

regexExtractNode · textDiffNode · dataConvertNode · templateRenderNode. 전부 결정적이고 외부 호출이 없다. 생성 코드는
`text_tools` 의 함수를 한 번 부르는 것이 전부다 — 로직은 그 모듈에서 직접 테스트한다(ADR-0008 과 같은 원칙).

공통 규약
  - 대상 텍스트 필드(source·newText)를 비우면 직전 노드 출력을 쓴다. `{{last_result}}` 자리표시자도 같은 값으로 바뀐다.
  - 바인딩(⚡, ADR-0026)을 받는 필드는 `bound_expr` 로 런타임 조회가 된다 — node_bindings.BINDABLE_FIELDS 와 짝.
  - 실패는 text_tools.ToolError(reason = error_catalog 코드) → NodeError 로 승격해 로그에 싣고, 결과는 `[⚠️ …]` 로 흘려보낸다.
    error 갈래(ENGINE-3)가 이 오류를 받는다.
  - 정규식·치환 문자열·라벨은 repr() 리터럴로 굽는다 — 백슬래시가 많은 값이라 손으로 이스케이프하면 틀린다.
"""

from node_bindings import bound_expr
from node_registry import node_registry


def _flag(data, key, default=False):
    value = data.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "on", "yes"}
    return bool(value)


def _int(data, key, default):
    try:
        return int(data.get(key) or default)
    except (TypeError, ValueError):
        return default


def _emit_head(node_id, node, indent, lines, label, upstream):
    lines.append(f"{indent}# --- {label} ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}import text_tools as _text_tools")
    lines.append(f"{indent}_tt_in_{node_id} = str({upstream}) if {upstream} is not None else ''")
    lines.append(f"{indent}_tt_out_{node_id} = ''")


def _emit_field(node_id, node, indent, lines, field, *, fallback_upstream):
    """필드 값 표현식: 바인딩이면 런타임 조회, 아니면 리터럴. `{{last_result}}` 치환 → (선택) 비면 직전 출력."""
    var = f"_tt_{field}_{node_id}"
    lines.append(f"{indent}{var} = {bound_expr(node, node_id, field)}")
    lines.append(f"{indent}if isinstance({var}, str) and '{{{{last_result}}}}' in {var}:")
    lines.append(f"{indent}    {var} = {var}.replace('{{{{last_result}}}}', _tt_in_{node_id})")
    if fallback_upstream:
        lines.append(f"{indent}if not (str({var}).strip() if isinstance({var}, str) else {var}):")
        lines.append(f"{indent}    {var} = _tt_in_{node_id}")
    return var


def _emit_tail(node_id, node, indent, lines, label, forward_edges, generate_block_fn, active_llm_id, visited):
    node_type = node['type']
    out = f"_tt_out_{node_id}"
    lines.append(f"{indent}    log_step('{node_id}', '{node_type}', _start_{node_id}, result={out})")
    lines.append(f"{indent}except _text_tools.ToolError as _e:")
    lines.append(f"{indent}    _tt_err_{node_id} = _make_node_error(_e.reason, node_type='{node_type}', node_id='{node_id}', field=_e.field,")
    lines.append(f"{indent}        safe_details=_e.safe_details, user_message=str(_e))")
    lines.append(f"{indent}    {out} = f'[⚠️ {{_e}}]'")
    lines.append(f"{indent}    log_step('{node_id}', '{node_type}', _start_{node_id}, result={out}, error=_tt_err_{node_id})")
    # 바인딩 실패(BINDING_*)는 이미 NodeError 를 품고 온다 — generic except 로 문구만 남기면 원인 안내가 사라진다.
    lines.append(f"{indent}except _NodeErrorException as _e:")
    lines.append(f"{indent}    {out} = f'[⚠️ {{_e.error.user_message}}]'")
    lines.append(f"{indent}    log_step('{node_id}', '{node_type}', _start_{node_id}, result={out}, error=_e.error)")
    lines.append(f"{indent}except Exception as _e:")
    lines.append(f"{indent}    {out} = f'{label} 실패: {{_e}}'")
    lines.append(f"{indent}    log_step('{node_id}', '{node_type}', _start_{node_id}, result={out}, error=_e)")
    lines.append(f"{indent}last_result = {out}")
    for target_id, _handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=out, visited=visited)


@node_registry.register('regexExtractNode')
def generate_regex_extract_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict,
                                forward_edges, incoming_edges, lines, generate_block_fn):
    data = node.get('data', {})
    upstream = prev_res_var if prev_res_var else 'last_result'
    mode = str(data.get('mode') or 'first')
    _emit_head(node_id, node, indent, lines, '정규식 추출', upstream)
    source = _emit_field(node_id, node, indent, lines, 'source', fallback_upstream=True)
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _tt_result_{node_id} = _text_tools.regex_extract(")
    lines.append(f"{indent}        {source}, {str(data.get('pattern') or '')!r}, mode={mode!r}, group={str(data.get('group') or '')!r},")
    lines.append(f"{indent}        ignore_case={_flag(data, 'ignoreCase')!r}, multiline={_flag(data, 'multiline')!r}, dot_all={_flag(data, 'dotAll')!r},")
    lines.append(f"{indent}        replacement={str(data.get('replacement') or '')!r}, fail_if_no_match={_flag(data, 'failIfNoMatch')!r})")
    lines.append(f"{indent}    _tt_out_{node_id} = _text_tools.to_output(_tt_result_{node_id})")
    _emit_tail(node_id, node, indent, lines, '정규식 추출', forward_edges, generate_block_fn, active_llm_id, visited)


@node_registry.register('textDiffNode')
def generate_text_diff_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict,
                            forward_edges, incoming_edges, lines, generate_block_fn):
    data = node.get('data', {})
    upstream = prev_res_var if prev_res_var else 'last_result'
    _emit_head(node_id, node, indent, lines, '텍스트 비교', upstream)
    old_text = _emit_field(node_id, node, indent, lines, 'oldText', fallback_upstream=False)
    new_text = _emit_field(node_id, node, indent, lines, 'newText', fallback_upstream=True)
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _tt_result_{node_id} = _text_tools.text_diff(")
    lines.append(f"{indent}        {old_text}, {new_text}, old_label={str(data.get('oldLabel') or '이전')!r}, new_label={str(data.get('newLabel') or '이후')!r},")
    lines.append(f"{indent}        context_lines={_int(data, 'contextLines', 3)!r}, normalize_json={_flag(data, 'normalizeJson')!r},")
    lines.append(f"{indent}        ignore_whitespace={_flag(data, 'ignoreWhitespace')!r})")
    lines.append(f"{indent}    _tt_out_{node_id} = _text_tools.to_output(_tt_result_{node_id})")
    _emit_tail(node_id, node, indent, lines, '텍스트 비교', forward_edges, generate_block_fn, active_llm_id, visited)


@node_registry.register('dataConvertNode')
def generate_data_convert_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict,
                               forward_edges, incoming_edges, lines, generate_block_fn):
    data = node.get('data', {})
    upstream = prev_res_var if prev_res_var else 'last_result'
    _emit_head(node_id, node, indent, lines, '데이터 형식 변환', upstream)
    source = _emit_field(node_id, node, indent, lines, 'source', fallback_upstream=True)
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _tt_out_{node_id} = _text_tools.data_convert(")
    lines.append(f"{indent}        {source}, from_format={str(data.get('fromFormat') or 'auto')!r}, to_format={str(data.get('toFormat') or 'yaml')!r},")
    lines.append(f"{indent}        indent={_int(data, 'indent', 2)!r}, sort_keys={_flag(data, 'sortKeys')!r})")
    _emit_tail(node_id, node, indent, lines, '데이터 형식 변환', forward_edges, generate_block_fn, active_llm_id, visited)


@node_registry.register('templateRenderNode')
def generate_template_render_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict,
                                  forward_edges, incoming_edges, lines, generate_block_fn):
    data = node.get('data', {})
    upstream = prev_res_var if prev_res_var else 'last_result'
    _emit_head(node_id, node, indent, lines, '템플릿 렌더', upstream)
    template = _emit_field(node_id, node, indent, lines, 'template', fallback_upstream=False)
    # 변수는 바인딩으로 앞 노드 출력(dict)을 그대로 받을 수 있다 — 문자열이면 JSON 으로 읽는다(coerce_variables).
    variables = _emit_field(node_id, node, indent, lines, 'variables', fallback_upstream=False)
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _tt_out_{node_id} = _text_tools.render_template(")
    lines.append(f"{indent}        {template}, {variables}, upstream_text=_tt_in_{node_id}, missing={str(data.get('missing') or 'empty')!r})")
    _emit_tail(node_id, node, indent, lines, '템플릿 렌더', forward_edges, generate_block_fn, active_llm_id, visited)


# ── DEV-2 2차: 감시형 유틸(네트워크) — ADR-0034 ──────────────────────────────
# 점검 결과가 나쁜 것(503·키워드 없음·인증서 만료 임박·취약점 있음)은 노드 **실패가 아니라 결과**다. 뒤의 conditionNode 가 ok/vulnerable 을
# 본다. failOnProblem/failOnVulnerable 을 켠 경우에만 NodeError(HTTPCHECK_PROBLEM/OSV_VULNERABLE)로 승격해 error 갈래로 보낸다.

def _emit_network_tail(node_id, node, indent, lines, label, forward_edges, generate_block_fn, active_llm_id, visited):
    """try 블록 뒤 — 커넥터 오류(URL 차단·타임아웃)·ToolError(lockfile)·바인딩·기타를 순서대로 잡는다."""
    node_type = node['type']
    out = f"_tt_out_{node_id}"
    lines.append(f"{indent}except _text_tools.ToolError as _e:")
    lines.append(f"{indent}    _tt_err_{node_id} = _make_node_error(_e.reason, node_type='{node_type}', node_id='{node_id}', field=_e.field,")
    lines.append(f"{indent}        safe_details=_e.safe_details, user_message=str(_e))")
    lines.append(f"{indent}    {out} = f'[⚠️ {{_e}}]'")
    lines.append(f"{indent}    log_step('{node_id}', '{node_type}', _start_{node_id}, result={out}, error=_tt_err_{node_id})")
    lines.append(f"{indent}except _ConnectorError as _e:")
    lines.append(f"{indent}    print(f'[{label} 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    {out} = f'[⚠️ {{_e.user_message}}]'")
    lines.append(f"{indent}    log_step('{node_id}', '{node_type}', _start_{node_id}, result={out},")
    lines.append(f"{indent}             error=_e.to_node_error(domain='connector', node_type='{node_type}', node_id='{node_id}'))")
    lines.append(f"{indent}except _NodeErrorException as _e:")
    lines.append(f"{indent}    {out} = f'[⚠️ {{_e.error.user_message}}]'")
    lines.append(f"{indent}    log_step('{node_id}', '{node_type}', _start_{node_id}, result={out}, error=_e.error)")
    lines.append(f"{indent}except Exception as _e:")
    lines.append(f"{indent}    {out} = f'{label} 실패: {{_e}}'")
    lines.append(f"{indent}    log_step('{node_id}', '{node_type}', _start_{node_id}, result={out}, error=_e)")
    lines.append(f"{indent}last_result = {out}")
    for target_id, _handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=out, visited=visited)


def _emit_network_head(node_id, node, indent, lines, label, upstream, module):
    _emit_head(node_id, node, indent, lines, label, upstream)
    lines.append(f"{indent}import json as _json")
    lines.append(f"{indent}from connectors.services import {module} as _{module}")
    lines.append(f"{indent}from connectors.errors import ConnectorError as _ConnectorError")
    lines.append(f"{indent}import node_definition as _node_definition")
    lines.append(f"{indent}from connectors import mock_runtime as _mock_runtime")


@node_registry.register('httpCheckNode')
def generate_http_check_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict,
                             forward_edges, incoming_edges, lines, generate_block_fn):
    """웹사이트 점검. 지난 점검의 본문 해시·상태는 connector_cursors(_load/_save_node_cursor)에 남겨 changed 를 판정한다."""
    data = node.get('data', {})
    upstream = prev_res_var if prev_res_var else 'last_result'
    track = _flag(data, 'trackChanges', True)
    fail_on_problem = _flag(data, 'failOnProblem')
    _emit_network_head(node_id, node, indent, lines, '웹사이트 점검', upstream, 'http_check')
    url = _emit_field(node_id, node, indent, lines, 'url', fallback_upstream=False)
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _hc_def_{node_id} = _node_definition.get_definition('httpCheckNode')")
    if track:
        lines.append(f"{indent}    _hc_prev_{node_id} = _load_node_cursor('{node_id}', db, kwargs)")
    else:
        lines.append(f"{indent}    _hc_prev_{node_id} = {{}}")
    lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node['type']}'):")
    lines.append(f"{indent}        _hc_result_{node_id} = _http_check.check(")
    lines.append(f"{indent}            _hc_def_{node_id}, url={url}, mode={str(data.get('mode') or 'all')!r}, method={str(data.get('method') or 'GET')!r},")
    lines.append(f"{indent}            expect_status={str(data.get('expectStatus') or '200-399')!r}, keyword={str(data.get('keyword') or '')!r},")
    lines.append(f"{indent}            track_changes={track!r}, previous=_hc_prev_{node_id}, tls_warn_days={_int(data, 'tlsWarnDays', 14)!r},")
    lines.append(f"{indent}            dns_record={str(data.get('dnsRecord') or 'any')!r})")
    lines.append(f"{indent}    _hc_cursor_{node_id} = _hc_result_{node_id}.pop('cursor', None)")
    if track:
        lines.append(f"{indent}    if _hc_cursor_{node_id}:")
        lines.append(f"{indent}        _save_node_cursor('{node_id}', _hc_cursor_{node_id}, db, kwargs, provider='http_check')")
    lines.append(f"{indent}    _tt_out_{node_id} = _json.dumps(_hc_result_{node_id}, ensure_ascii=False, default=str)")
    lines.append(f"{indent}    print('[웹사이트 점검] ' + ('정상' if _hc_result_{node_id}['ok'] else '문제: ' + ', '.join(_hc_result_{node_id}['problems'])) + ' — ' + str({url}))")
    if fail_on_problem:
        lines.append(f"{indent}    if not _hc_result_{node_id}['ok']:")
        lines.append(f"{indent}        _hc_err_{node_id} = _make_node_error('HTTPCHECK_PROBLEM', node_type='{node['type']}', node_id='{node_id}',")
        lines.append(f"{indent}            safe_details={{'url': str({url}), 'problems': list(_hc_result_{node_id}['problems'])}},")
        lines.append(f"{indent}            user_message='점검에서 문제가 발견됐습니다: ' + ', '.join(_hc_result_{node_id}['problems']))")
        lines.append(f"{indent}        log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_tt_out_{node_id}, error=_hc_err_{node_id})")
        lines.append(f"{indent}    else:")
        lines.append(f"{indent}        log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_tt_out_{node_id})")
    else:
        lines.append(f"{indent}    log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_tt_out_{node_id})")
    _emit_network_tail(node_id, node, indent, lines, '웹사이트 점검', forward_edges, generate_block_fn, active_llm_id, visited)


@node_registry.register('osvScanNode')
def generate_osv_scan_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict,
                           forward_edges, incoming_edges, lines, generate_block_fn):
    """의존성 취약점 검사. lockfile 을 비우면 직전 노드 출력(보통 githubNode file.get 의 content 바인딩)."""
    data = node.get('data', {})
    upstream = prev_res_var if prev_res_var else 'last_result'
    fail_on_vulnerable = _flag(data, 'failOnVulnerable')
    _emit_network_head(node_id, node, indent, lines, '의존성 취약점 검사', upstream, 'osv')
    lockfile = _emit_field(node_id, node, indent, lines, 'lockfile', fallback_upstream=True)
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _osv_def_{node_id} = _node_definition.get_definition('osvScanNode')")
    lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node['type']}'):")
    lines.append(f"{indent}        _osv_result_{node_id} = _osv.scan(")
    lines.append(f"{indent}            _osv_def_{node_id}, {lockfile}, fmt={str(data.get('format') or 'auto')!r}, min_severity={str(data.get('minSeverity') or 'all')!r},")
    lines.append(f"{indent}            include_details={_flag(data, 'includeDetails', True)!r}, max_packages={_int(data, 'maxPackages', 1000)!r})")
    lines.append(f"{indent}    _tt_out_{node_id} = _json.dumps(_osv_result_{node_id}, ensure_ascii=False, default=str)")
    lines.append(f"{indent}    print(f\"[의존성 취약점 검사] 패키지 {{_osv_result_{node_id}['queried']}}개 중 {{_osv_result_{node_id}['vulnerable']}}개에 취약점 {{_osv_result_{node_id}['alertCount']}}건\")")
    if fail_on_vulnerable:
        lines.append(f"{indent}    if _osv_result_{node_id}['alertCount'] > 0:")
        lines.append(f"{indent}        _osv_err_{node_id} = _make_node_error('OSV_VULNERABLE', node_type='{node['type']}', node_id='{node_id}',")
        lines.append(f"{indent}            safe_details={{'vulnerable': _osv_result_{node_id}['vulnerable'], 'alertCount': _osv_result_{node_id}['alertCount'],")
        lines.append(f"{indent}                          'top': [a['id'] for a in _osv_result_{node_id}['alerts'][:5]]}},")
        lines.append(f"{indent}            user_message=f\"의존성에 알려진 취약점 {{_osv_result_{node_id}['alertCount']}}건이 있습니다.\")")
        lines.append(f"{indent}        log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_tt_out_{node_id}, error=_osv_err_{node_id})")
        lines.append(f"{indent}    else:")
        lines.append(f"{indent}        log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_tt_out_{node_id})")
    else:
        lines.append(f"{indent}    log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_tt_out_{node_id})")
    _emit_network_tail(node_id, node, indent, lines, '의존성 취약점 검사', forward_edges, generate_block_fn, active_llm_id, visited)
