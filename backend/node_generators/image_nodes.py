"""Generated-code adapters for AI image nodes."""

from __future__ import annotations

from node_registry import node_registry


@node_registry.register("imageGenerationNode")
def generate_image_generation_node(
    node_id, node, indent, active_llm_id, prev_res_var, visited,
    node_dict, forward_edges, incoming_edges, lines, generate_block_fn,
):
    data = node.get("data") or {}
    incoming = prev_res_var or "last_result"

    lines.append(f"{indent}# --- AI Image Generation/Edit Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}from image_generation_runtime import generate_or_edit_image, ImageGenerationError as _ImgErr")
    # 생성 실패(크레딧 소진·키 없음·한도)는 이 노드의 오류로 남기고 흐름은 계속 간다 — 커넥터·발송
    # 노드와 같은 관례('[⚠️ …]' 결과, log_step 이 오류로 분류). 예전에는 예외가 그대로 새어
    # 워크플로우 전체가 "Flow 1 Error" 로 죽었다(시연 포스터: 이미지 크레딧 소진 하나로 문안·조판까지
    # 전부 사라졌다, 2026-09-04 실행 로그). 하류 디자인 포맷은 배경 슬롯이 비면 테마 배경으로 완성한다.
    lines.append(f"{indent}_image_result_{node_id} = None")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    _image_result_{node_id} = generate_or_edit_image(")
    lines.append(f"{indent}        api_key={str(data.get('apiKey') or '')!r},")
    lines.append(f"{indent}        prompt={str(data.get('prompt') or '')!r},")
    lines.append(f"{indent}        incoming={incoming},")
    lines.append(f"{indent}        action={str(data.get('action') or 'auto')!r},")
    lines.append(f"{indent}        model={str(data.get('model') or 'gpt-5.6')!r},")
    lines.append(f"{indent}        size={str(data.get('size') or 'auto')!r},")
    lines.append(f"{indent}        quality={str(data.get('quality') or 'auto')!r},")
    lines.append(f"{indent}        background={str(data.get('background') or 'auto')!r},")
    lines.append(f"{indent}        output_format={str(data.get('outputFormat') or 'png')!r},")
    lines.append(f"{indent}        previous_response_id={str(data.get('previousResponseId') or '')!r},")
    lines.append(f"{indent}        db=db,")
    lines.append(f"{indent}        owner_user_id=__owner_user_id__,")
    lines.append(f"{indent}        project_id=kwargs.get('project_id'),")
    lines.append(f"{indent}        node_id={node_id!r},")
    lines.append(f"{indent}        session_id=kwargs.get('session_id') or '',")
    lines.append(f"{indent}    )")
    lines.append(f"{indent}except _ImgErr as _e:")
    lines.append(f"{indent}    print(f'[이미지 생성 실패] {{_e.code}}: {{_e}}')")
    lines.append(f"{indent}    last_result = f'[⚠️ 이미지 생성 실패: {{_e}}]'")
    lines.append(f"{indent}    log_step('{node_id}', 'imageGenerationNode', _start_{node_id}, result=last_result)")
    ok = indent + "    "
    lines.append(f"{indent}if _image_result_{node_id} is not None:")
    lines.append(f"{ok}last_result = _image_result_{node_id}['file_path']")
    # 생성 이미지를 이번 실행의 artifact 로 등록한다(ADR-0018) — 발송 노드의 첨부 포트가 이 값을
    # 읽는다. 예전에는 하류 노드가 결과 문자열의 `uploads/...` 를 정규식으로 주워 열었다.
    lines.append(f"{ok}_record_artifacts('{node_id}', [_image_result_{node_id}.get('artifact_id')])")
    lines.append(f"{ok}_image_usage_{node_id} = _image_result_{node_id}.get('usage') or {{}}")
    lines.append(f"{ok}_image_in_{node_id} = int(_image_usage_{node_id}.get('input_tokens') or 0)")
    lines.append(f"{ok}_image_out_{node_id} = int(_image_usage_{node_id}.get('output_tokens') or 0)")
    lines.append(f"{ok}_image_total_{node_id} = int(_image_usage_{node_id}.get('total_tokens') or (_image_in_{node_id} + _image_out_{node_id}))")
    lines.append(f"{ok}__token_usage__['nodes']['{node_id}'] = {{")
    lines.append(f"{ok}    'input_tokens': _image_in_{node_id}, 'output_tokens': _image_out_{node_id},")
    lines.append(f"{ok}    'total_tokens': _image_total_{node_id}, 'image': _image_usage_{node_id},")
    lines.append(f"{ok}    'artifact_id': _image_result_{node_id}.get('artifact_id'),")
    lines.append(f"{ok}    'response_id': _image_result_{node_id}.get('response_id'),")
    lines.append(f"{ok}    'revision_index': _image_result_{node_id}.get('revision_index', 0),")
    lines.append(f"{ok}}}")
    lines.append(f"{ok}__token_usage__['total_input'] += _image_in_{node_id}")
    lines.append(f"{ok}__token_usage__['total_output'] += _image_out_{node_id}")
    lines.append(f"{ok}__token_usage__['total_tokens'] += _image_total_{node_id}")
    lines.append(f"{ok}log_step('{node_id}', 'imageGenerationNode', _start_{node_id}, result=last_result)")

    for target_id, _handle in forward_edges.get(node_id, []):
        generate_block_fn(
            target_id,
            indent,
            active_llm_id=active_llm_id,
            prev_res_var="last_result",
            visited=visited,
        )

