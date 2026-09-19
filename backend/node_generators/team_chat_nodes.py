"""node_generators/team_chat_nodes.py — 국내 협업 메신저 발송 노드 3종의 실행 코드 생성 (백로그 34 DEV-3, ADR-0035).

doorayNode · jandiNode · kakaoWorkNode. 생성 코드는 `connectors/services/team_chat` 의 함수를 한 번 부르는 것이 전부다.
Slack 발송(integration_nodes.generate_slack_node)과 같은 규약을 지킨다 —
  - message 를 비우면 직전 노드 출력을 보내고, 채우면 그 뒤에 직전 출력을 덧붙인다(`{{last_result}}` 로 자리를 정할 수 있다).
  - **결과는 실제로 보낸 메시지 텍스트**다(discordNode·emailNode·kakaoNode 와 같은 이유 — 상태 문구로 덮으면 평가가 내용을 못 본다).
  - 실패해도 보내려던 내용은 버리지 않는다(`본문 + [⚠️ 안내]`). 오류 도메인은 delivery(ADR-0016) — 발송은 되돌릴 수 없다.
비밀(웹훅 URL·App Key)은 실행 시점에 API 센터에서 읽는다(`_oauth.require_token`) — graph_data 에 담기지 않는다.
"""

from node_bindings import bound_expr
from node_registry import node_registry

# 서비스별 (provider, 서비스 이름, 함수, 문자열 필드, 라벨)
_SERVICES = {
    'doorayNode': dict(provider='dooray_webhook', service='Dooray', func='send_dooray', label='Dooray 발송',
                       fields=('title', 'link', 'botName'), kwargs={'title': 'title', 'link': 'link', 'botName': 'bot_name'}),
    'jandiNode': dict(provider='jandi_webhook', service='잔디', func='send_jandi', label='잔디 발송',
                      fields=('title', 'description', 'link'), kwargs={'title': 'title', 'description': 'description', 'link': 'link'}),
    'kakaoWorkNode': dict(provider='kakaowork', service='카카오워크', func='send_kakaowork', label='카카오워크 발송',
                          fields=('conversationId', 'email'), kwargs={'conversationId': 'conversation_id', 'email': 'email'}),
}


def _literal(value):
    return str('' if value is None else value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def _emit_team_chat(node_type, node_id, node, indent, active_llm_id, prev_res_var, visited, forward_edges, lines, generate_block_fn):
    spec = _SERVICES[node_type]
    data = node.get('data', {})
    upstream = prev_res_var if prev_res_var else 'last_result'
    label = spec['label']

    lines.append(f"{indent}# --- {label} ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}_cx_err_{node_id} = None")
    lines.append(f"{indent}from connectors.services import team_chat as _team_chat")
    lines.append(f"{indent}from connectors import oauth as _oauth")
    lines.append(f"{indent}from connectors.errors import ConnectorError as _ConnectorError")
    lines.append(f"{indent}import node_definition as _node_definition")
    lines.append(f"{indent}from connectors import mock_runtime as _mock_runtime")
    lines.append(f"{indent}_tc_upstream_{node_id} = str({upstream}) if {upstream} is not None else ''")
    # 메시지·부속 필드는 바인딩(⚡)을 받는다 — 앞 노드 값을 그대로 꽂는 것이 정상 사용법이다.
    lines.append(f"{indent}_tc_text_{node_id} = _team_chat.compose_message({bound_expr(node, node_id, 'message')}, _tc_upstream_{node_id})")
    call_kwargs = []
    for field in spec['fields']:
        var = f"_tc_{field}_{node_id}"
        lines.append(f"{indent}{var} = str({bound_expr(node, node_id, field)})")
        lines.append(f"{indent}if '{{{{last_result}}}}' in {var}:")
        lines.append(f"{indent}    {var} = {var}.replace('{{{{last_result}}}}', _tc_upstream_{node_id})")
        call_kwargs.append(f"{spec['kwargs'][field]}={var}")
    if node_type == 'kakaoWorkNode':
        call_kwargs.append(f"mode=\"{_literal(data.get('mode') or 'send')}\"")
    else:
        call_kwargs.append(f"color=\"{_literal(data.get('color') or '')}\"")
    lines.append(f"{indent}_tc_out_{node_id} = _tc_text_{node_id}")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _tc_secret_{node_id} = _oauth.require_token('{spec['provider']}', __owner_user_id__, db, service='{spec['service']}')")
    lines.append(f"{indent}    _tc_def_{node_id} = _node_definition.get_definition('{node_type}')")
    lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node_type}'):")
    lines.append(f"{indent}        _tc_result_{node_id} = _team_chat.{spec['func']}(_tc_def_{node_id}, _tc_secret_{node_id}, text=_tc_text_{node_id}, {', '.join(call_kwargs)})")
    lines.append(f"{indent}    _tc_out_{node_id} = _tc_result_{node_id}['text']")
    lines.append(f"{indent}    print(f\"[{label}] 발송 완료 ({{_tc_result_{node_id}['chars']}}자)\")")
    lines.append(f"{indent}except _ConnectorError as _e:")
    lines.append(f"{indent}    print(f'[{label} 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    _tc_out_{node_id} = _tc_text_{node_id} + f'\\n\\n[⚠️ {{_e.user_message}}]'")
    lines.append(f"{indent}    _cx_err_{node_id} = _e.to_node_error(domain='delivery', node_type='{node_type}', node_id='{node_id}')")
    lines.append(f"{indent}except _NodeErrorException as _e:")
    lines.append(f"{indent}    _tc_out_{node_id} = _tc_text_{node_id} + f'\\n\\n[⚠️ {{_e.error.user_message}}]'")
    lines.append(f"{indent}    _cx_err_{node_id} = _e.error")
    lines.append(f"{indent}last_result = _tc_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node_type}', _start_{node_id}, result=last_result, error=_cx_err_{node_id})")

    for target_id, _handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"_tc_out_{node_id}", visited=visited)


@node_registry.register('doorayNode')
def generate_dooray_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    _emit_team_chat('doorayNode', node_id, node, indent, active_llm_id, prev_res_var, visited, forward_edges, lines, generate_block_fn)


@node_registry.register('jandiNode')
def generate_jandi_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    _emit_team_chat('jandiNode', node_id, node, indent, active_llm_id, prev_res_var, visited, forward_edges, lines, generate_block_fn)


@node_registry.register('kakaoWorkNode')
def generate_kakaowork_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    _emit_team_chat('kakaoWorkNode', node_id, node, indent, active_llm_id, prev_res_var, visited, forward_edges, lines, generate_block_fn)
