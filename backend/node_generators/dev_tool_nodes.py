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
