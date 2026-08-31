"""node_generators/document_nodes.py — `hwpxDocumentNode` 실행 코드 생성 (계획 §3.2).

**얇은 wrapper 만 낸다.** 실제 동작은 `documents/hwpx_runtime.py` 에 있는 평범한 파이썬이라
직접 테스트할 수 있다 — `template_nodes.py` 가 zipfile·XML 조작을 문자열로 조립해 두는 바람에
테스트가 불가능했던 것을 반복하지 않는다.
"""

import json

from node_bindings import bound_expr
from node_registry import node_registry

from . import delivery_support


@node_registry.register('hwpxDocumentNode')
def generate_hwpx_document_node(node_id, node, indent, active_llm_id, prev_res_var, visited,
                                node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    data = node.get('data', {})
    mode = str(data.get('mode') or 'create').replace('\\', '\\\\').replace('"', '\\"')

    # 저장 이름은 경로가 아니라 파일 이름이다 — 런타임이 uploads/ 밑으로 정규화한다.
    output_path = str(data.get('output_path') or '').replace('\\', '/').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '')
    incoming = prev_res_var if prev_res_var else 'last_result'

    # 살펴볼 파일은 **경로가 아니라 artifact** 다(ADR-0018 의 첨부 규칙을 그대로 쓴다).
    # 사용자가 직접 고른 것이 있으면 그것을, 없으면 앞 노드가 만든 파일을 쓴다 —
    # "문서 만들고 검사해줘" 처럼 두 노드를 일자로 잇는 그래프가 배선 없이 동작해야 한다.
    picked = delivery_support.attachments_config(node)
    chosen_ids = picked.get("artifactIds") or []
    upstream = delivery_support.upstream_artifacts_expr(node_id, incoming_edges)
    if picked.get("mode") == "select" and chosen_ids:
        source_expr = repr(str(chosen_ids[0]))
    elif picked.get("mode") == "none":
        source_expr = "''"
    else:
        source_expr = f"({upstream} or [''])[0]"

    lines.append(f"{indent}# --- HWPX Document Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}import json as _json")
    lines.append(f"{indent}from documents import hwpx_runtime as _hwpx_rt")
    lines.append(f"{indent}from documents import hwpx as _hwpx_engine")
    lines.append(f"{indent}_hx_err_{node_id} = None")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _hx_source_{node_id} = {source_expr}")
    lines.append(f"{indent}    _hx_result_{node_id} = _hwpx_rt.run(")
    lines.append(f"{indent}        \"{mode}\", incoming={incoming},")
    lines.append(f"{indent}        output_path=\"{output_path}\", source_artifact_id=_hx_source_{node_id},")
    lines.append(f"{indent}        db=db, owner_user_id=__owner_user_id__, project_id=kwargs.get('project_id'))")
    # 만든 파일은 artifact 로 등록해야 뒤의 발송 노드가 첨부할 수 있다(ADR-0018).
    lines.append(f"{indent}    if _hx_result_{node_id}.get('mode') == 'create':")
    lines.append(f"{indent}        import artifacts as _artifacts")
    lines.append(f"{indent}        _hx_ref_{node_id} = _artifacts.register_generated_file(")
    lines.append(f"{indent}            db, path=_hx_result_{node_id}['path'], owner_user_id=__owner_user_id__,")
    lines.append(f"{indent}            project_id=kwargs.get('project_id'), purpose='generated')")
    lines.append(f"{indent}        _record_artifacts('{node_id}', [_hx_ref_{node_id}.to_public_dict()] if _hx_ref_{node_id} else [])")
    lines.append(f"{indent}        _hx_out_{node_id} = _hx_result_{node_id}['path']")
    lines.append(f"{indent}    else:")
    lines.append(f"{indent}        _hx_out_{node_id} = _json.dumps(_hx_result_{node_id}, ensure_ascii=False)")
    # 사용자가 고칠 수 있는 오류(스펙이 잘못됐다·지원 안 하는 블록이다)는 문구를 그대로 보여준다.
    lines.append(f"{indent}except (_hwpx_rt.HwpxNodeError, _hwpx_engine.PackageRejected) as _e:")
    lines.append(f"{indent}    _hx_out_{node_id} = f'[⚠️ {{_e}}]'")
    lines.append(f"{indent}    _hx_err_{node_id} = _e")
    lines.append(f"{indent}except Exception as _e:")
    lines.append(f"{indent}    _hx_out_{node_id} = f'HWPX 문서 처리 실패: {{_e}}'")
    lines.append(f"{indent}    _hx_err_{node_id} = _e")
    lines.append(f"{indent}last_result = _hx_out_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")

    for target_id, _handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id,
                          prev_res_var=f"_hx_out_{node_id}", visited=visited)


@node_registry.register('formatNode')
def generate_format_node(node_id, node, indent, active_llm_id, prev_res_var, visited,
                         node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    """문서 포맷 노드(포맷 스튜디오 계획 Phase 1) — 포맷+빈칸 값 → 완성 파일(artifact).

    LLM 을 부르지 않는 결정적 노드다. 값 해석·렌더·오류 코드는 documents/format_runtime 이
    담당하고, 여기서는 hwpxDocumentNode 와 같은 뼈대(호출 → artifact 등록 → NodeError 변환)만
    생성한다.
    """
    data = node.get('data', {})
    format_id = str(data.get('formatId') or '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '')
    output = str(data.get('output') or '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '')
    output_path = str(data.get('output_path') or '').replace('\\', '/').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '')
    values_json = json.dumps(str(data.get('values') or ''), ensure_ascii=False)
    incoming = prev_res_var if prev_res_var else 'last_result'

    lines.append(f"{indent}# --- Format Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}from documents import format_runtime as _fmt_rt")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _fmt_result_{node_id} = _fmt_rt.run(")
    # 바인딩 지원 필드(계획 §4): 앞 노드 출력에서 포맷 id·빈칸 값·파일 이름을 직접 가져올 수 있다.
    lines.append(f"{indent}        format_id={bound_expr(node, node_id, 'formatId')}, output=\"{output}\",")
    lines.append(f"{indent}        values_json={bound_expr(node, node_id, 'values')} or {values_json}, incoming={incoming},")
    lines.append(f"{indent}        output_path={bound_expr(node, node_id, 'output_path')},")
    lines.append(f"{indent}        db=db, owner_user_id=__owner_user_id__)")
    # 완성 파일을 artifact 로 등록 — 뒤의 발송 노드가 자동 첨부한다(ADR-0018).
    lines.append(f"{indent}    import artifacts as _artifacts")
    lines.append(f"{indent}    _fmt_ref_{node_id} = _artifacts.register_generated_file(")
    lines.append(f"{indent}        db, path=_fmt_result_{node_id}['path'], owner_user_id=__owner_user_id__,")
    lines.append(f"{indent}        project_id=kwargs.get('project_id'), purpose='generated')")
    lines.append(f"{indent}    _record_artifacts('{node_id}', [_fmt_ref_{node_id}.to_public_dict()] if _fmt_ref_{node_id} else [])")
    lines.append(f"{indent}    _fmt_out_{node_id} = _fmt_result_{node_id}['path']")
    lines.append(f"{indent}    log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_fmt_out_{node_id})")
    lines.append(f"{indent}except _fmt_rt.FormatNodeError as _e:")
    # 오류 코드(FORMAT_*)를 NodeError 로 실어 프론트가 필드 안내를 그릴 수 있게 한다(ADR-0016).
    lines.append(f"{indent}    _fmt_safe_{node_id} = {{'formatId': \"{format_id}\"}}")
    lines.append(f"{indent}    if _e.reason == 'FORMAT_FIELD_MISSING':")
    lines.append(f"{indent}        _fmt_safe_{node_id}['missingFields'] = list(getattr(_e, 'missing_fields', []) or [])")
    lines.append(f"{indent}    _fmt_err_{node_id} = _make_node_error(_e.reason, node_type='{node['type']}', node_id='{node_id}',")
    lines.append(f"{indent}        safe_details=_fmt_safe_{node_id}, user_message=str(_e))")
    lines.append(f"{indent}    _fmt_out_{node_id} = f'[⚠️ {{_e}}]'")
    lines.append(f"{indent}    log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_fmt_out_{node_id}, error=_fmt_err_{node_id})")
    lines.append(f"{indent}except Exception as _e:")
    lines.append(f"{indent}    _fmt_out_{node_id} = f'문서 포맷 처리 실패: {{_e}}'")
    lines.append(f"{indent}    log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_fmt_out_{node_id}, error=_e)")
    lines.append(f"{indent}last_result = _fmt_out_{node_id}")

    for target_id, _handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id,
                          prev_res_var=f"_fmt_out_{node_id}", visited=visited)

