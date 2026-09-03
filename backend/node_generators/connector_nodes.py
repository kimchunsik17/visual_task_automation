"""node_generators/connector_nodes.py — 공식 연동 노드의 실행 코드 생성 (ADR-0008).

기존 연동 노드는 `requests.post(...)` 부터 status_code 비교까지 40여 줄을 문자열로 조립했다.
그러면 타임아웃·재시도·오류 분류가 노드마다 갈라지고, 생성된 코드는 단위 테스트도 못 한다.

여기서는 정반대로 간다 — 생성되는 코드는 서비스 모듈 함수를 한 번 부르는 것이 전부이고,
실제 로직은 `connectors/services/` 의 평범한 파이썬 모듈에 있어 직접 테스트할 수 있다.
"""

from node_registry import node_registry


def _error_domain(node_type, mode):
    """이 모드가 외부 상태를 바꾸면 'delivery', 아니면 'connector' — 같은 429 라도 발송 맥락에서는
    DELIVERY_RATE_LIMITED 가 되고 timeout 의 effectState 가 unknown 으로 잡힌다(ADR-0016 ERROR-2).
    판단 근거는 정의 파일의 connector.sideEffectByMode 하나다(ADR-0007) — 여기서 따로 목록을 두지 않는다."""
    import node_definition
    definition = node_definition.get_definition(node_type)
    spec = getattr(definition, 'connector', None) if definition is not None else None
    if spec is None:
        return 'connector'
    return 'delivery' if spec.writes_externally(mode) else 'connector'


def _emit_common_prelude(node_id, indent, lines):
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}_cx_err_{node_id} = None")
    lines.append(f"{indent}import json as _json")
    lines.append(f"{indent}from connectors.services import youtube as _youtube")
    lines.append(f"{indent}from connectors import oauth as _oauth")
    lines.append(f"{indent}from connectors.errors import ConnectorError as _ConnectorError")
    lines.append(f"{indent}import node_definition as _node_definition")
    lines.append(f"{indent}from connectors import mock_runtime as _mock_runtime")


@node_registry.register('youtubeTriggerNode')
def generate_youtube_trigger_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    data = node.get('data', {})
    channel_id = str(data.get('channelId', '')).replace('\\', '\\\\').replace('"', '\\"')
    max_results = int(data.get('maxResults') or 10)

    lines.append(f"{indent}# --- YouTube Trigger Node ({node_id}) ---")
    _emit_common_prelude(node_id, indent, lines)
    lines.append(f"{indent}_yt_out_{node_id} = ''")
    lines.append(f"{indent}try:")
    # 토큰은 실행 시점에 API 센터에서 가져온다 — graph_data 에 절대 담기지 않으므로
    # revision/템플릿/로그로 새어 나가지 않는다.
    lines.append(f"{indent}    _yt_token_{node_id} = _oauth.require_token('google_oauth', __owner_user_id__, db, service='YouTube')")
    lines.append(f"{indent}    _yt_def_{node_id} = _node_definition.get_definition('youtubeTriggerNode')")
    # cursor 는 노드 메모리에 남긴다 — 같은 영상을 두 번 통지하지 않기 위해서다.
    lines.append(f"{indent}    _yt_cursor_{node_id} = _load_node_cursor('{node_id}', db, kwargs)")
    # 목업 실행에서 요청 기록이 어느 노드에서 나왔는지 알리기 위한 표시(ADR-0009).
    lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node['type']}'):")
    lines.append(f"{indent}        _yt_result_{node_id} = _youtube.poll_new_videos(")
    lines.append(f"{indent}            _yt_def_{node_id}, _yt_token_{node_id},")
    lines.append(f"{indent}            channel_id=\"{channel_id}\", cursor=_yt_cursor_{node_id}, max_results={max_results})")
    lines.append(f"{indent}    _save_node_cursor('{node_id}', _yt_result_{node_id}['cursor'], db, kwargs, provider='youtube')")
    lines.append(f"{indent}    _yt_out_{node_id} = _json.dumps(_yt_result_{node_id}['videos'], ensure_ascii=False)")
    lines.append(f"{indent}    if _yt_result_{node_id}['first_run']:")
    lines.append(f"{indent}        print('[YouTube Trigger] 첫 실행이라 기준점만 기록했습니다. 다음 새 영상부터 알립니다.')")
    lines.append(f"{indent}except _ConnectorError as _e:")
    lines.append(f"{indent}    print(f'[YouTube Trigger 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    _yt_out_{node_id} = f'[⚠️ {{_e.user_message}}]'")
    lines.append(f"{indent}    _cx_err_{node_id} = _e.to_node_error(domain='connector', node_type='youtubeTriggerNode', node_id='{node_id}')")
    lines.append(f"{indent}last_result = _yt_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result, error=_cx_err_{node_id})")

    for target_id, handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"_yt_out_{node_id}", visited=visited)


@node_registry.register('youtubeNode')
def generate_youtube_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    data = node.get('data', {})
    mode = str(data.get('mode') or 'upload_video')
    upstream = prev_res_var if prev_res_var else 'last_result'

    def literal(key):
        return str(data.get(key, '') or '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    lines.append(f"{indent}# --- YouTube Node ({node_id}, {mode}) ---")
    _emit_common_prelude(node_id, indent, lines)
    lines.append(f"{indent}_yt_params_{node_id} = {{")
    for key in ('filePath', 'videoId', 'playlistId', 'title', 'description', 'privacyStatus', 'commentText'):
        lines.append(f"{indent}    '{key}': \"{literal(key)}\",")
    lines.append(f"{indent}}}")
    # 비워둔 칸은 직전 노드의 출력으로 채운다 — "요약 → 댓글" 처럼 앞 노드 결과를 그대로
    # 쓰는 흐름이 가장 흔하다. {{last_result}} 자리표시자도 같은 값으로 바꾼다.
    lines.append(f"{indent}_yt_upstream_{node_id} = str({upstream}) if {upstream} is not None else ''")
    lines.append(f"{indent}for _k, _v in list(_yt_params_{node_id}.items()):")
    lines.append(f"{indent}    if isinstance(_v, str) and '{{{{last_result}}}}' in _v:")
    lines.append(f"{indent}        _yt_params_{node_id}[_k] = _v.replace('{{{{last_result}}}}', _yt_upstream_{node_id})")
    if mode == 'upload_video':
        lines.append(f"{indent}if not _yt_params_{node_id}['filePath']:")
        lines.append(f"{indent}    _yt_params_{node_id}['filePath'] = _yt_upstream_{node_id}.strip()")
        # 공개 문자열(uploads/<이름>)을 물리 경로로 풀고 소유권 검사를 태운다(_safe_user_path) —
        # per-user 이동 후 파일은 uploads/u<id>/ 에 있고, 커넥터 쪽 검증(resolve_stored_path)은
        # 절대 경로를 받으면 루트 가둠만 다시 확인한다.
        lines.append(f"{indent}if _yt_params_{node_id}['filePath']:")
        lines.append(f"{indent}    _yt_fp_{node_id} = _safe_user_path(_yt_params_{node_id}['filePath'])")
        lines.append(f"{indent}    _yt_params_{node_id}['filePath'] = str(_yt_fp_{node_id}) if _yt_fp_{node_id} is not None else ''")
    elif mode == 'create_comment':
        lines.append(f"{indent}if not _yt_params_{node_id}['commentText']:")
        lines.append(f"{indent}    _yt_params_{node_id}['commentText'] = _yt_upstream_{node_id}")

    lines.append(f"{indent}_yt_out_{node_id} = ''")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _yt_token_{node_id} = _oauth.require_token('google_oauth', __owner_user_id__, db, service='YouTube')")
    lines.append(f"{indent}    _yt_def_{node_id} = _node_definition.get_definition('youtubeNode')")
    lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node['type']}'):")
    lines.append(f"{indent}        _yt_result_{node_id} = _youtube.run_action(_yt_def_{node_id}, '{mode}', _yt_token_{node_id}, _yt_params_{node_id})")
    lines.append(f"{indent}    _yt_out_{node_id} = _json.dumps(_yt_result_{node_id}, ensure_ascii=False)")
    lines.append(f"{indent}    print(f'[YouTube {mode} 성공] {{_yt_out_{node_id}}}')")
    lines.append(f"{indent}except _ConnectorError as _e:")
    # 실패해도 만들려던 내용은 버리지 않는다 — 다른 발송 노드와 같은 규약이다.
    lines.append(f"{indent}    print(f'[YouTube {mode} 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    _yt_out_{node_id} = _yt_upstream_{node_id} + f'\\n\\n[⚠️ {{_e.user_message}}]'")
    lines.append(f"{indent}    _cx_err_{node_id} = _e.to_node_error(domain='{_error_domain('youtubeNode', mode)}', node_type='youtubeNode', node_id='{node_id}')")
    lines.append(f"{indent}last_result = _yt_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result, error=_cx_err_{node_id})")

    for target_id, handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"_yt_out_{node_id}", visited=visited)


# ── Wave 1: RSS · Gmail · Google Drive (우선 백로그 8번) ────────────────
# ADR-0007/0008 계약의 반복 적용 — 생성 코드는 서비스 모듈 호출 한 번이 전부다.

@node_registry.register('rssTriggerNode')
def generate_rss_trigger_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    data = node.get('data', {})
    feed_url = str(data.get('feedUrl', '') or '').replace('\\', '\\\\').replace('"', '\\"')
    max_items = int(data.get('maxItems') or 10)

    lines.append(f"{indent}# --- RSS Trigger Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}_cx_err_{node_id} = None")
    lines.append(f"{indent}import json as _json")
    lines.append(f"{indent}from connectors.services import rss as _rss")
    lines.append(f"{indent}from connectors.errors import ConnectorError as _ConnectorError")
    lines.append(f"{indent}import node_definition as _node_definition")
    lines.append(f"{indent}from connectors import mock_runtime as _mock_runtime")
    lines.append(f"{indent}_rss_out_{node_id} = ''")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _rss_def_{node_id} = _node_definition.get_definition('rssTriggerNode')")
    lines.append(f"{indent}    _rss_cursor_{node_id} = _load_node_cursor('{node_id}', db, kwargs)")
    lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node['type']}'):")
    lines.append(f"{indent}        _rss_result_{node_id} = _rss.poll_new_items(")
    lines.append(f"{indent}            _rss_def_{node_id}, feed_url=\"{feed_url}\", cursor=_rss_cursor_{node_id}, max_items={max_items})")
    lines.append(f"{indent}    _save_node_cursor('{node_id}', _rss_result_{node_id}['cursor'], db, kwargs, provider='rss')")
    lines.append(f"{indent}    _rss_out_{node_id} = _json.dumps(_rss_result_{node_id}['items'], ensure_ascii=False)")
    lines.append(f"{indent}    if _rss_result_{node_id}['first_run']:")
    lines.append(f"{indent}        print('[RSS Trigger] 첫 실행이라 기준점만 기록했습니다. 다음 새 글부터 알립니다.')")
    lines.append(f"{indent}except _ConnectorError as _e:")
    lines.append(f"{indent}    print(f'[RSS Trigger 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    _rss_out_{node_id} = f'[⚠️ {{_e.user_message}}]'")
    lines.append(f"{indent}    _cx_err_{node_id} = _e.to_node_error(domain='connector', node_type='rssTriggerNode', node_id='{node_id}')")
    lines.append(f"{indent}last_result = _rss_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result, error=_cx_err_{node_id})")

    for target_id, handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"_rss_out_{node_id}", visited=visited)


@node_registry.register('gmailTriggerNode')
def generate_gmail_trigger_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    data = node.get('data', {})
    query = str(data.get('query', '') or '').replace('\\', '\\\\').replace('"', '\\"')
    max_results = int(data.get('maxResults') or 10)

    lines.append(f"{indent}# --- Gmail Trigger Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}_cx_err_{node_id} = None")
    lines.append(f"{indent}import json as _json")
    lines.append(f"{indent}from connectors.services import gmail as _gmail")
    lines.append(f"{indent}from connectors import oauth as _oauth")
    lines.append(f"{indent}from connectors.errors import ConnectorError as _ConnectorError")
    lines.append(f"{indent}import node_definition as _node_definition")
    lines.append(f"{indent}from connectors import mock_runtime as _mock_runtime")
    lines.append(f"{indent}_gm_out_{node_id} = ''")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _gm_token_{node_id} = _oauth.require_token('google_oauth', __owner_user_id__, db, service='Gmail')")
    lines.append(f"{indent}    _gm_def_{node_id} = _node_definition.get_definition('gmailTriggerNode')")
    lines.append(f"{indent}    _gm_cursor_{node_id} = _load_node_cursor('{node_id}', db, kwargs)")
    lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node['type']}'):")
    lines.append(f"{indent}        _gm_result_{node_id} = _gmail.poll_new_emails(")
    lines.append(f"{indent}            _gm_def_{node_id}, _gm_token_{node_id},")
    lines.append(f"{indent}            query=\"{query}\", cursor=_gm_cursor_{node_id}, max_results={max_results})")
    lines.append(f"{indent}    _save_node_cursor('{node_id}', _gm_result_{node_id}['cursor'], db, kwargs, provider='gmail')")
    lines.append(f"{indent}    _gm_out_{node_id} = _json.dumps(_gm_result_{node_id}['emails'], ensure_ascii=False)")
    lines.append(f"{indent}    if _gm_result_{node_id}['first_run']:")
    lines.append(f"{indent}        print('[Gmail Trigger] 첫 실행이라 기준점만 기록했습니다. 다음 새 메일부터 알립니다.')")
    lines.append(f"{indent}except _ConnectorError as _e:")
    lines.append(f"{indent}    print(f'[Gmail Trigger 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    _gm_out_{node_id} = f'[⚠️ {{_e.user_message}}]'")
    lines.append(f"{indent}    _cx_err_{node_id} = _e.to_node_error(domain='connector', node_type='gmailTriggerNode', node_id='{node_id}')")
    lines.append(f"{indent}last_result = _gm_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result, error=_cx_err_{node_id})")

    for target_id, handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"_gm_out_{node_id}", visited=visited)


def _emit_connector_action(node_id, node, indent, lines, *, service_alias, module_name, node_type,
                           service_label, mode, param_keys, upstream, body_field=None,
                           attachment_provider=None, incoming_edges=None, saves_download=False):
    """Gmail/Drive 액션의 공통 코드 골격 — youtubeNode 생성기와 같은 규약이다.

    `attachment_provider` 가 있으면 첨부 포트를 함께 배선한다(ADR-0018). 첨부 검증은 외부 호출
    **전에** 끝나고, 실패하면 run_action 을 아예 부르지 않는다 — 일부 파일만 빠진 메일이 나가는
    것보다 아무것도 보내지 않는 편이 되돌리기 쉽다(§4.10 FILE-SEND-3 ④).
    """
    def literal(key):
        data = node.get('data', {})
        return str(data.get(key, '') or '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    lines.append(f"{indent}# --- {service_label} Node ({node_id}, {mode}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}_cx_err_{node_id} = None")
    lines.append(f"{indent}import json as _json")
    lines.append(f"{indent}from connectors.services import {module_name} as {service_alias}")
    lines.append(f"{indent}from connectors import oauth as _oauth")
    lines.append(f"{indent}from connectors.errors import ConnectorError as _ConnectorError")
    lines.append(f"{indent}import node_definition as _node_definition")
    lines.append(f"{indent}from connectors import mock_runtime as _mock_runtime")
    lines.append(f"{indent}_cx_params_{node_id} = {{")
    for key in param_keys:
        lines.append(f"{indent}    '{key}': \"{literal(key)}\",")
    lines.append(f"{indent}}}")
    lines.append(f"{indent}_cx_upstream_{node_id} = str({upstream}) if {upstream} is not None else ''")
    lines.append(f"{indent}for _k, _v in list(_cx_params_{node_id}.items()):")
    lines.append(f"{indent}    if isinstance(_v, str) and '{{{{last_result}}}}' in _v:")
    lines.append(f"{indent}        _cx_params_{node_id}[_k] = _v.replace('{{{{last_result}}}}', _cx_upstream_{node_id})")
    if body_field:
        lines.append(f"{indent}if not _cx_params_{node_id}['{body_field}']:")
        lines.append(f"{indent}    _cx_params_{node_id}['{body_field}'] = _cx_upstream_{node_id}")
    if 'filePath' in param_keys:
        # 공개 문자열(uploads/<이름>)을 물리 경로로 풀고 소유권 검사를 태운다(_safe_user_path) —
        # per-user 이동 후 파일은 uploads/u<id>/ 에 있고, 서비스 쪽 resolve_stored_path 는 절대
        # 경로를 받으면 루트 가둠만 다시 확인한다.
        lines.append(f"{indent}if _cx_params_{node_id}.get('filePath'):")
        lines.append(f"{indent}    _cx_fp_{node_id} = _safe_user_path(_cx_params_{node_id}['filePath'])")
        lines.append(f"{indent}    _cx_params_{node_id}['filePath'] = str(_cx_fp_{node_id}) if _cx_fp_{node_id} is not None else ''")
    lines.append(f"{indent}_cx_out_{node_id} = ''")
    lines.append(f"{indent}_cx_attach_{node_id} = []")
    if attachment_provider:
        from .delivery_support import attachments_config, upstream_artifacts_expr
        lines.append(f"{indent}from artifacts import ArtifactError as _ArtifactError")
        lines.append(f"{indent}from delivery_attachments import open_attachments as _open_attachments, attachment_report as _attachment_report")
        lines.append(f"{indent}from delivery_runtime import prepare_attachments as _prepare_attachments")
    lines.append(f"{indent}try:")
    if attachment_provider:
        lines.append(f"{indent}    _cx_attach_{node_id} = _prepare_attachments(")
        lines.append(f"{indent}        db, provider='{attachment_provider}',")
        lines.append(f"{indent}        config={attachments_config(node)!r},")
        lines.append(f"{indent}        upstream_artifact_ids={upstream_artifacts_expr(node_id, incoming_edges or {})},")
        lines.append(f"{indent}        upstream_text=_cx_upstream_{node_id}, owner_user_id=__owner_user_id__,")
        lines.append(f"{indent}        project_id=kwargs.get('project_id'), node_type='{node_type}', node_id='{node_id}')")
    lines.append(f"{indent}    _cx_token_{node_id} = _oauth.require_token('google_oauth', __owner_user_id__, db, service='{service_label}')")
    lines.append(f"{indent}    _cx_def_{node_id} = _node_definition.get_definition('{node_type}')")
    if attachment_provider:
        lines.append(f"{indent}    with _open_attachments(_cx_attach_{node_id}) as _cx_opened_{node_id}:")
        lines.append(f"{indent}        _cx_params_{node_id}['__attachments__'] = _cx_opened_{node_id}")
        lines.append(f"{indent}        with _mock_runtime.node('{node_id}', '{node_type}'):")
        lines.append(f"{indent}            _cx_result_{node_id} = {service_alias}.run_action(_cx_def_{node_id}, '{mode}', _cx_token_{node_id}, _cx_params_{node_id})")
        lines.append(f"{indent}    _cx_result_{node_id}['attachments'] = _attachment_report(_cx_attach_{node_id})")
    elif saves_download:
        # 내려받은 파일은 artifact 로 등록된다(ADR-0018) — 저장 위치는 실행기가 정하고 서비스
        # 모듈은 바이트만 흘려 넣는다. 등록된 id 를 레지스트리에 올려 하류 발송 노드가 첨부한다.
        lines.append(f"{indent}    from drive_downloads import sink_factory as _sink_factory")
        lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node_type}'):")
        lines.append(f"{indent}        _cx_result_{node_id} = {service_alias}.run_action(")
        lines.append(f"{indent}            _cx_def_{node_id}, '{mode}', _cx_token_{node_id}, _cx_params_{node_id},")
        lines.append(f"{indent}            save_download=_sink_factory(db, owner_user_id=__owner_user_id__,")
        lines.append(f"{indent}                                        project_id=kwargs.get('project_id')))")
        lines.append(f"{indent}    _record_artifacts('{node_id}', [_cx_result_{node_id}.get('artifact_id')])")
    else:
        lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node_type}'):")
        lines.append(f"{indent}        _cx_result_{node_id} = {service_alias}.run_action(_cx_def_{node_id}, '{mode}', _cx_token_{node_id}, _cx_params_{node_id})")
    lines.append(f"{indent}    _cx_out_{node_id} = _json.dumps(_cx_result_{node_id}, ensure_ascii=False)")
    lines.append(f"{indent}    print(f'[{service_label} {mode} 성공] {{_cx_out_{node_id}}}')")
    if attachment_provider:
        # 첨부 검증 실패는 외부 호출 전에 끝난 것이라 effectState 가 not_started 다 — 그대로
        # 다시 보내도 중복 발송이 되지 않는다.
        lines.append(f"{indent}except _ArtifactError as _ae:")
        lines.append(f"{indent}    print(f'[{service_label} 첨부 거절] {{_ae.error.code}}: {{_ae.error.user_message}}')")
        lines.append(f"{indent}    _cx_out_{node_id} = _cx_upstream_{node_id} + f'\\n\\n[⚠️ {{_ae.error.user_message}}]'")
        lines.append(f"{indent}    _cx_err_{node_id} = _ae.error")
    lines.append(f"{indent}except _ConnectorError as _e:")
    lines.append(f"{indent}    print(f'[{service_label} {mode} 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    _cx_out_{node_id} = _cx_upstream_{node_id} + f'\\n\\n[⚠️ {{_e.user_message}}]'")
    lines.append(f"{indent}    _cx_err_{node_id} = _e.to_node_error(domain='{_error_domain(node_type, mode)}', node_type='{node_type}', node_id='{node_id}')")
    lines.append(f"{indent}last_result = _cx_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node_type}', _start_{node_id}, result=last_result, error=_cx_err_{node_id})")


@node_registry.register('gmailNode')
def generate_gmail_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    mode = str(node.get('data', {}).get('mode') or 'send_email')
    upstream = prev_res_var if prev_res_var else 'last_result'
    _emit_connector_action(
        node_id, node, indent, lines,
        service_alias='_gmail', module_name='gmail', node_type='gmailNode', service_label='Gmail',
        mode=mode, param_keys=('to', 'subject', 'body', 'messageId', 'labelName'),
        upstream=upstream, body_field='body' if mode in ('send_email', 'reply_email', 'create_draft') else None,
        # 라벨 적용은 메시지를 보내지 않으므로 첨부 포트가 없다.
        attachment_provider='gmail' if mode in ('send_email', 'reply_email', 'create_draft') else None,
        incoming_edges=incoming_edges,
    )
    for target_id, handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"_cx_out_{node_id}", visited=visited)


@node_registry.register('googleDriveNode')
def generate_google_drive_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    mode = str(node.get('data', {}).get('mode') or 'search_files')
    upstream = prev_res_var if prev_res_var else 'last_result'
    _emit_connector_action(
        node_id, node, indent, lines,
        service_alias='_drive', module_name='drive', node_type='googleDriveNode', service_label='Google Drive',
        mode=mode, param_keys=('query', 'filePath', 'fileName', 'folderId', 'fileId', 'maxResults'),
        upstream=upstream,
        body_field='filePath' if mode == 'upload_file' else ('query' if mode == 'search_files' else None),
        saves_download=(mode == 'download_file'),
    )
    for target_id, handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"_cx_out_{node_id}", visited=visited)


@node_registry.register('naverSearchNode')
def generate_naver_search_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    """네이버 검색.

    jusoNode 와 같은 규칙으로 **검색어가 비면 직전 노드 출력을 쓴다** — 동적 입력(사용자
    키워드)이나 앞 LLM 이 만든 검색어를 그대로 넣는 그래프가 흔하다. 둘 다 비면 서비스가
    '검색어가 비어 있다' 로 명확히 실패한다.
    """
    data = node.get('data', {})
    mode = str(data.get('mode') or 'blog').replace('\\', '\\\\').replace('"', '\\"')
    query = str(data.get('query', '') or '').replace('\\', '\\\\').replace('"', '\\"')
    display = int(data.get('display') or 10)
    sort = str(data.get('sort') or 'sim').replace('\\', '\\\\').replace('"', '\\"')
    incoming = prev_res_var if prev_res_var else 'last_result'

    lines.append(f"{indent}# --- Naver Search Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}_cx_err_{node_id} = None")
    lines.append(f"{indent}import json as _json")
    lines.append(f"{indent}from connectors.services import naver_search as _naver_search")
    lines.append(f"{indent}from connectors import oauth as _oauth")
    lines.append(f"{indent}from connectors.errors import ConnectorError as _ConnectorError")
    lines.append(f"{indent}import node_definition as _node_definition")
    lines.append(f"{indent}from connectors import mock_runtime as _mock_runtime")
    lines.append(f"{indent}_nv_out_{node_id} = ''")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _nv_query_{node_id} = \"{query}\" or str({incoming} or '').strip()")
    # 키는 실행 시점에 API 센터에서 가져온다 — graph_data 에 담기지 않아 revision/템플릿/로그로 새지 않는다.
    lines.append(f"{indent}    _nv_key_{node_id} = _oauth.require_token('naver_api_hub', __owner_user_id__, db, service='네이버 검색')")
    lines.append(f"{indent}    _nv_def_{node_id} = _node_definition.get_definition('naverSearchNode')")
    lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node['type']}'):")
    lines.append(f"{indent}        _nv_result_{node_id} = _naver_search.search(")
    lines.append(f"{indent}            _nv_def_{node_id}, _nv_key_{node_id}, mode=\"{mode}\",")
    lines.append(f"{indent}            query=_nv_query_{node_id}, display={display}, sort=\"{sort}\")")
    lines.append(f"{indent}    _nv_out_{node_id} = _json.dumps(_nv_result_{node_id}, ensure_ascii=False)")
    lines.append(f"{indent}except _ConnectorError as _e:")
    lines.append(f"{indent}    print(f'[네이버 검색 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    _nv_out_{node_id} = f'[⚠️ {{_e.user_message}}]'")
    lines.append(f"{indent}    _cx_err_{node_id} = _e.to_node_error(domain='connector', node_type='naverSearchNode', node_id='{node_id}')")
    lines.append(f"{indent}last_result = _nv_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result, error=_cx_err_{node_id})")

    for target_id, _handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id,
                          prev_res_var=f"_nv_out_{node_id}", visited=visited)


@node_registry.register('naverSearchTriggerNode')
def generate_naver_search_trigger_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    data = node.get('data', {})
    # 트리거 mode 는 감시 대상(blog/cafe_article)이고, connector.modes 의 이벤트 이름과 다르다.
    mode = str(data.get('mode') or 'blog').replace('\\', '\\\\').replace('"', '\\"')
    query = str(data.get('query', '') or '').replace('\\', '\\\\').replace('"', '\\"')
    max_results = int(data.get('maxResults') or 20)

    lines.append(f"{indent}# --- Naver Search Trigger Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}_cx_err_{node_id} = None")
    lines.append(f"{indent}import json as _json")
    lines.append(f"{indent}from connectors.services import naver_search as _naver_search")
    lines.append(f"{indent}from connectors import oauth as _oauth")
    lines.append(f"{indent}from connectors.errors import ConnectorError as _ConnectorError")
    lines.append(f"{indent}import node_definition as _node_definition")
    lines.append(f"{indent}from connectors import mock_runtime as _mock_runtime")
    lines.append(f"{indent}_nvt_out_{node_id} = ''")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _nvt_key_{node_id} = _oauth.require_token('naver_api_hub', __owner_user_id__, db, service='네이버 검색')")
    lines.append(f"{indent}    _nvt_def_{node_id} = _node_definition.get_definition('naverSearchTriggerNode')")
    # 한도는 키 단위로 공유된다 — **호출 전에** 센다. 넘으면 나가지 않는다.
    lines.append(f"{indent}    _nvt_quota_{node_id} = _naver_search.consume_quota(db, __owner_user_id__)")
    lines.append(f"{indent}    if _nvt_quota_{node_id}['limit'] and _nvt_quota_{node_id}['ratio'] >= 0.8:")
    lines.append(f"{indent}        print(f\"[네이버 검색] 오늘 한도의 {{int(_nvt_quota_{node_id}['ratio']*100)}}%% 를 썼습니다 \"")
    lines.append(f"{indent}              f\"(남은 호출 {{_nvt_quota_{node_id}['remaining']:,}}건). 확인 주기를 늘려주세요.\")")
    lines.append(f"{indent}    _nvt_cursor_{node_id} = _load_node_cursor('{node_id}', db, kwargs)")
    lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node['type']}'):")
    lines.append(f"{indent}        _nvt_result_{node_id} = _naver_search.poll_new_results(")
    lines.append(f"{indent}            _nvt_def_{node_id}, _nvt_key_{node_id}, mode=\"{mode}\",")
    lines.append(f"{indent}            query=\"{query}\", cursor=_nvt_cursor_{node_id}, max_results={max_results})")
    lines.append(f"{indent}    _save_node_cursor('{node_id}', _nvt_result_{node_id}['cursor'], db, kwargs, provider='naver_search')")
    lines.append(f"{indent}    _nvt_out_{node_id} = _json.dumps(_nvt_result_{node_id}['items'], ensure_ascii=False)")
    lines.append(f"{indent}    if _nvt_result_{node_id}['first_run']:")
    lines.append(f"{indent}        print('[네이버 검색 트리거] 첫 실행이라 기준점만 기록했습니다. 다음 새 글부터 알립니다.')")
    lines.append(f"{indent}except _ConnectorError as _e:")
    lines.append(f"{indent}    print(f'[네이버 검색 트리거 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    _nvt_out_{node_id} = f'[⚠️ {{_e.user_message}}]'")
    lines.append(f"{indent}    _cx_err_{node_id} = _e.to_node_error(domain='connector', node_type='naverSearchTriggerNode', node_id='{node_id}')")
    lines.append(f"{indent}last_result = _nvt_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result, error=_cx_err_{node_id})")

    for target_id, _handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id,
                          prev_res_var=f"_nvt_out_{node_id}", visited=visited)


@node_registry.register('naverCafeNode')
def generate_naver_cafe_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    data = node.get('data', {})

    def _s(key, default=''):
        return str(data.get(key) or default).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    mode = _s('mode', 'write_article')
    club_id, menu_id = _s('clubId'), _s('menuId')
    subject, nickname = _s('subject'), _s('nickname')
    content = _s('content')
    confirm = bool(data.get('confirm'))
    incoming = prev_res_var if prev_res_var else 'last_result'

    lines.append(f"{indent}# --- Naver Cafe Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}_cx_err_{node_id} = None")
    lines.append(f"{indent}import json as _json")
    lines.append(f"{indent}from connectors.services import naver_cafe as _naver_cafe")
    lines.append(f"{indent}from connectors import oauth as _oauth")
    lines.append(f"{indent}from connectors.errors import ConnectorError as _ConnectorError")
    lines.append(f"{indent}import node_definition as _node_definition")
    lines.append(f"{indent}from connectors import mock_runtime as _mock_runtime")
    lines.append(f"{indent}_nc_out_{node_id} = ''")
    lines.append(f"{indent}try:")
    # 본문을 비우면 직전 노드 결과를 쓴다 — "요약해서 카페에 올려줘" 가 가장 흔한 그래프다.
    lines.append(f"{indent}    _nc_content_{node_id} = \"{content}\" or str({incoming} or '')")
    lines.append(f"{indent}    _nc_preview_{node_id} = _naver_cafe.preview(")
    lines.append(f"{indent}        \"{mode}\", club_id=\"{club_id}\", menu_id=\"{menu_id}\",")
    lines.append(f"{indent}        subject=\"{subject}\", content=_nc_content_{node_id}, nickname=\"{nickname}\")")
    if not confirm:
        # 되돌릴 수 없는 동작이라 기본값은 미리보기다. 여기서 **요청이 나가지 않는다.**
        lines.append(f"{indent}    print('[네이버 카페] 미리보기만 했습니다 — 실제로 올리려면 노드의 \\'실제로 게시합니다\\' 를 켜주세요.')")
        lines.append(f"{indent}    _nc_out_{node_id} = _json.dumps(_nc_preview_{node_id}, ensure_ascii=False)")
    else:
        lines.append(f"{indent}    _nc_token_{node_id} = _oauth.require_token('naver_user_oauth', __owner_user_id__, db, service='네이버 카페')")
        lines.append(f"{indent}    _nc_def_{node_id} = _node_definition.get_definition('naverCafeNode')")
        lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node['type']}'):")
        if mode == 'join':
            lines.append(f"{indent}        _nc_result_{node_id} = _naver_cafe.join(")
            lines.append(f"{indent}            _nc_def_{node_id}, _nc_token_{node_id}, club_id=\"{club_id}\", nickname=\"{nickname}\")")
        else:
            lines.append(f"{indent}        _nc_result_{node_id} = _naver_cafe.write_article(")
            lines.append(f"{indent}            _nc_def_{node_id}, _nc_token_{node_id}, club_id=\"{club_id}\",")
            lines.append(f"{indent}            menu_id=\"{menu_id}\", subject=\"{subject}\", content=_nc_content_{node_id})")
        # 무엇이 실제로 나갔는지 로그에 남긴다 — 중복 게시를 사람이 확인할 근거다.
        lines.append(f"{indent}    print(f\"[네이버 카페] 게시 완료: {{_nc_result_{node_id}.get('articleId') or '(글 번호 없음)'}}\")")
        lines.append(f"{indent}    _nc_out_{node_id} = _json.dumps(_nc_result_{node_id}, ensure_ascii=False)")
    lines.append(f"{indent}except _ConnectorError as _e:")
    lines.append(f"{indent}    print(f'[네이버 카페 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    _nc_out_{node_id} = f'[⚠️ {{_e.user_message}}]'")
    lines.append(f"{indent}    _cx_err_{node_id} = _e.to_node_error(domain='delivery', node_type='naverCafeNode', node_id='{node_id}')")
    lines.append(f"{indent}last_result = _nc_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result, error=_cx_err_{node_id})")

    for target_id, _handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id,
                          prev_res_var=f"_nc_out_{node_id}", visited=visited)


@node_registry.register('jusoNode')
def generate_juso_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict,
                       forward_edges, incoming_edges, lines, generate_block_fn):
    """도로명주소 검색 (계획 §6.8, Phase 3).

    읽기 전용이라 카페 노드 같은 확인 절차가 없다. 대신 **검색어가 비면 직전 노드 출력을 쓴다** —
    "이 주소들 정리해줘" 처럼 앞 노드가 준 문자열을 그대로 넣는 그래프가 가장 흔하다.
    """
    data = node.get('data', {})

    def _s(key, default=''):
        return str(data.get(key) or default).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    keyword = _s('keyword')
    try:
        count = max(1, min(int(data.get('count') or 10), 100))
    except (TypeError, ValueError):
        count = 10
    include_history = bool(data.get('includeHistory'))
    incoming = prev_res_var if prev_res_var else 'last_result'

    lines.append(f"{indent}# --- Juso Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}_cx_err_{node_id} = None")
    lines.append(f"{indent}import json as _json")
    lines.append(f"{indent}from connectors.services import juso as _juso")
    lines.append(f"{indent}from connectors import oauth as _oauth")
    lines.append(f"{indent}from connectors.errors import ConnectorError as _ConnectorError")
    lines.append(f"{indent}import node_definition as _node_definition")
    lines.append(f"{indent}from connectors import mock_runtime as _mock_runtime")
    lines.append(f"{indent}_js_out_{node_id} = ''")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _js_keyword_{node_id} = \"{keyword}\" or str({incoming} or '').strip()")
    lines.append(f"{indent}    _js_key_{node_id} = _oauth.require_token('juso', __owner_user_id__, db, service='도로명주소')")
    lines.append(f"{indent}    _js_def_{node_id} = _node_definition.get_definition('jusoNode')")
    lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node['type']}'):")
    lines.append(f"{indent}        _js_result_{node_id} = _juso.search(")
    lines.append(f"{indent}            _js_def_{node_id}, _js_key_{node_id},")
    lines.append(f"{indent}            keyword=_js_keyword_{node_id}, count={count},")
    lines.append(f"{indent}            include_history={include_history!r})")
    lines.append(f"{indent}    _js_out_{node_id} = _json.dumps(_js_result_{node_id}, ensure_ascii=False)")
    lines.append(f"{indent}except _ConnectorError as _e:")
    lines.append(f"{indent}    print(f'[도로명주소 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    _js_out_{node_id} = f'[⚠️ {{_e.user_message}}]'")
    lines.append(f"{indent}    _cx_err_{node_id} = _e.to_node_error(domain='integration', node_type='jusoNode', node_id='{node_id}')")
    lines.append(f"{indent}last_result = _js_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result, error=_cx_err_{node_id})")

    for target_id, _handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id,
                          prev_res_var=f"_js_out_{node_id}", visited=visited)


@node_registry.register('dataGoKrNode')
def generate_data_go_kr_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict,
                             forward_edges, incoming_edges, lines, generate_block_fn):
    """공공데이터포털 조회 (계획 §6.8, Phase 3).

    **임의 URL 을 만들지 않는다.** 데이터셋 id 와 동작 이름만 넘기고, 실제 주소는
    `data_go_kr.DATASETS` 가 정한다 — 생성 코드에 주소가 박히면 registry 가 무의미해진다.
    """
    import json as _json_mod

    data = node.get('data', {})

    def _s(key, default=''):
        return str(data.get(key) or default).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    dataset = _s('dataset', 'kma_village_forecast')
    operation = _s('operation')
    try:
        rows = max(1, min(int(data.get('rows') or 10), 100))
    except (TypeError, ValueError):
        rows = 10

    # params 는 JSON 필드다. 문자열로 왔으면 여기서 한 번 읽어 두고, 못 읽으면 빈 dict 로 둔다
    # (실행 시점에 터지는 것보다 낫다 — 필수값이 빠지면 connector 가 이름을 짚어 준다).
    raw_params = data.get('params')
    if isinstance(raw_params, str):
        try:
            raw_params = _json_mod.loads(raw_params) if raw_params.strip() else {}
        except ValueError:
            raw_params = {}
    if not isinstance(raw_params, dict):
        raw_params = {}

    lines.append(f"{indent}# --- 공공데이터포털 Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}_cx_err_{node_id} = None")
    lines.append(f"{indent}import json as _json")
    lines.append(f"{indent}from connectors.services import data_go_kr as _dgk")
    lines.append(f"{indent}from connectors import oauth as _oauth")
    lines.append(f"{indent}from connectors.errors import ConnectorError as _ConnectorError")
    lines.append(f"{indent}import node_definition as _node_definition")
    lines.append(f"{indent}from connectors import mock_runtime as _mock_runtime")
    lines.append(f"{indent}_dg_out_{node_id} = ''")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _dg_key_{node_id} = _oauth.require_token('data_go_kr', __owner_user_id__, db, service='공공데이터포털')")
    lines.append(f"{indent}    _dg_def_{node_id} = _node_definition.get_definition('dataGoKrNode')")
    lines.append(f"{indent}    with _mock_runtime.node('{node_id}', '{node['type']}'):")
    lines.append(f"{indent}        _dg_result_{node_id} = _dgk.query(")
    lines.append(f"{indent}            _dg_def_{node_id}, _dg_key_{node_id}, dataset_id=\"{dataset}\",")
    lines.append(f"{indent}            operation=\"{operation}\", params={raw_params!r}, rows={rows})")
    lines.append(f"{indent}    _dg_out_{node_id} = _json.dumps(_dg_result_{node_id}, ensure_ascii=False)")
    lines.append(f"{indent}except _ConnectorError as _e:")
    lines.append(f"{indent}    print(f'[공공데이터포털 실패] {{_e.code}}: {{_e.user_message}}')")
    lines.append(f"{indent}    _dg_out_{node_id} = f'[⚠️ {{_e.user_message}}]'")
    lines.append(f"{indent}    _cx_err_{node_id} = _e.to_node_error(domain='integration', node_type='dataGoKrNode', node_id='{node_id}')")
    lines.append(f"{indent}last_result = _dg_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result, error=_cx_err_{node_id})")

    for target_id, _handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id,
                          prev_res_var=f"_dg_out_{node_id}", visited=visited)
