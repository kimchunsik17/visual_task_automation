import datetime
from node_registry import node_registry

@node_registry.register('startNode')
def generate_start_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- startNode ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    next_edges = forward_edges.get(node_id, [])
    if not next_edges:
        lines.append(f"{indent}pass")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)

@node_registry.register('scheduleNode')
def generate_schedule_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- scheduleNode ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    next_edges = forward_edges.get(node_id, [])
    if not next_edges:
        lines.append(f"{indent}pass")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)

@node_registry.register('discordTriggerNode')
def generate_discord_trigger_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # webhookNode와 동일한 방식 — discord_bot.py의 on_message가 run_workflow(..., default_input=메시지내용)로
    # 실행을 트리거하므로, 그 kwarg를 그대로 이 노드의 출력으로 흘려보낸다. 봇 토큰 자체(data.botToken)는
    # 이 노드가 실제로 실행되는 시점(=메시지가 이미 도착한 뒤)엔 필요 없다 — 봇을 언제 띄울지는
    # main.py가 그래프에 이 노드가 있는지 보고 별도로 결정한다(라이브 토글 시).
    lines.append(f"{indent}# --- Discord Trigger Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}dyn_input_{node_id} = kwargs.get('{node_id}')")
    lines.append(f"{indent}if dyn_input_{node_id} is None:")
    lines.append(f"{indent}    dyn_input_{node_id} = kwargs.get('default_input', '')")
    lines.append(f"{indent}last_result = dyn_input_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)

@node_registry.register('telegramTriggerNode')
def generate_telegram_trigger_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # discordTriggerNode와 완전히 동일한 패턴 — telegram_bot.py의 process_update가
    # run_workflow(..., default_input=메시지텍스트)로 실행을 트리거한다.
    lines.append(f"{indent}# --- Telegram Trigger Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}dyn_input_{node_id} = kwargs.get('{node_id}')")
    lines.append(f"{indent}if dyn_input_{node_id} is None:")
    lines.append(f"{indent}    dyn_input_{node_id} = kwargs.get('default_input', '')")
    lines.append(f"{indent}last_result = dyn_input_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)

@node_registry.register('conditionNode')
def generate_condition_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    rules = node.get('data', {}).get('rules', [])
    var = prev_res_var if prev_res_var else 'last_result'

    lines.append(f"{indent}# --- Condition Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    # 분기 판정에 쓴 입력을 그대로 기록한다 — 이게 없으면 __node_results__ 에 이 노드가
    # 아예 없어서, 하류 mergeNode·데이터 바인딩에서 값이 조용히 사라진다(재검증 §2.1).
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result={var})")

    edge_by_handle = {handle: target for target, handle in forward_edges.get(node_id, [])}

    # 갈래를 방출하는 동안 분기 경로를 표시한다 — 형제 갈래에 걸친 재합류 노드는 갈래 안에
    # 자리 잡지 않고, 분기 구문이 닫힌 뒤(graph.generate_block 의 _flush_ready_joins) 방출된다.
    _begin_branch = getattr(generate_block_fn, 'begin_branch', lambda *_: None)
    _end_branch = getattr(generate_block_fn, 'end_branch', lambda: None)

    def _emit_branch(handle, branch_indent):
        target_id = edge_by_handle.get(handle)
        if target_id is None:
            lines.append(f"{branch_indent}pass")
        else:
            _lines_before = len(lines)
            _begin_branch(node_id, handle)
            try:
                generate_block_fn(target_id, branch_indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)
            finally:
                _end_branch()
            # 갈래 본문이 재합류 노드뿐이면 방출이 분기 뒤로 미뤄져 아무 줄도 안 생긴다 —
            # 빈 if/else 블록은 문법 오류이므로 pass 로 채운다.
            if len(lines) == _lines_before:
                lines.append(f"{branch_indent}pass")

    def _cond_expr(operator, value):
        value_escaped = str(value).replace('\\', '\\\\').replace('"', '\\"')
        if operator == "==":
            return f'str({var}) == "{value_escaped}"'
        if operator == "Contains":
            return f'"{value_escaped}" in str({var})'
        if operator in (">", "<", ">=", "<="):
            return f'is_numeric({var}) and is_numeric("{value_escaped}") and float({var}) {operator} float("{value_escaped}")'
        return f'"{value_escaped}" in str({var})'  # 알 수 없는 operator는 Contains로 취급(방어적 기본값)

    if not rules:
        lines.append(f"{indent}if False:")
        lines.append(f"{indent}    pass")
        lines.append(f"{indent}else:")
        _emit_branch("else", indent + "    ")
        return

    for i, rule in enumerate(rules):
        keyword = "if" if i == 0 else "elif"
        lines.append(f"{indent}{keyword} {_cond_expr(rule.get('operator', 'Contains'), rule.get('value', ''))}:")
        _emit_branch(rule.get("id"), indent + "    ")

    lines.append(f"{indent}else:")
    _emit_branch("else", indent + "    ")

@node_registry.register('loopNode')
def generate_loop_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    max_iter = node.get('data', {}).get('maxIterations', 5)
    lines.append(f"{indent}# --- Loop Node (Container) ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")

    acc_var = f"loop_acc_{node_id}"
    if prev_res_var:
        lines.append(f"{indent}{acc_var} = {prev_res_var}")
    else:
        lines.append(f"{indent}{acc_var} = last_result")
        
    lines.append(f"{indent}for _loop_idx_{node_id} in range(int({max_iter})):")
    
    # Prioritize explicit 'loop_start' handle
    loop_start_edges = [t for t, h in forward_edges.get(node_id, []) if h == 'loop_start']
    
    if loop_start_edges:
        generate_block_fn(loop_start_edges[0], indent + "    ", active_llm_id=active_llm_id, prev_res_var=acc_var, visited=visited)
        lines.append(f"{indent}    {acc_var} = last_result")
    else:
        loop_body_nodes = [n for n, v in node_dict.items() if v.get('parentNode') == node_id]
        if loop_body_nodes:
            body_node_ids = {n for n in loop_body_nodes}
            
            has_inner_incoming = set()
            for src_id in body_node_ids:
                for target_id, handle in forward_edges.get(src_id, []):
                    if target_id in body_node_ids:
                        has_inner_incoming.add(target_id)
                    
            body_roots = [n for n in loop_body_nodes if n not in has_inner_incoming]
            
            if body_roots:
                generate_block_fn(body_roots[0], indent + "    ", active_llm_id=active_llm_id, prev_res_var=acc_var, visited=visited)
                lines.append(f"{indent}    {acc_var} = last_result")
            else:
                lines.append(f"{indent}    pass")
        else:
            lines.append(f"{indent}    pass")
        
    # 반복이 끝난 뒤 최종 누적값을 기록한다 — 이 노드가 __node_results__ 에 없으면
    # done 뒤의 mergeNode·데이터 바인딩이 루프 결과를 통째로 잃는다(재검증 §2.1).
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result={acc_var})")
    done_edges = [t for t, h in forward_edges.get(node_id, []) if h == 'done']
    if done_edges:
        generate_block_fn(done_edges[0], indent, active_llm_id=active_llm_id, prev_res_var=acc_var, visited=visited)

@node_registry.register('breakNode')
def generate_break_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Break Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    # break 는 제어를 끊으므로 기록을 그 앞에 남긴다 — 실행 로그에서 "여기서 끊겼다"가 보여야 한다.
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    lines.append(f"{indent}break")

@node_registry.register('mergeNode')
def generate_merge_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Merge Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    strategy = node.get('data', {}).get('mergeStrategy', 'join_newline')
    
    # __node_results__는 각 노드가 log_step을 호출할 때마다 자기 결과를 node_id로 저장해두는
    # 전역 딕셔너리다(graph.py 참고). 예전엔 여기서 각 incoming edge의 source를 찾는 딕셔너리를
    # 만들어놓고 정작 쓰지 않은 채 prev_res_var(직전에 도착한 갈래) 하나만 merge_vals에 넣어서,
    # 조건 분기 등으로 먼저 실행된 다른 갈래의 결과가 조용히 사라지는 버그가 있었다(실제로 겪음 —
    # 포스터 생성 워크플로우에서 conditionNode 이전 갈래의 구조화된 정보가 통째로 없어졌었음).
    # 이제 실제로 존재하는 모든 incoming source의 결과를 __node_results__에서 찾아 합친다
    # (조건 분기로 인해 실행되지 않은 갈래는 빈 문자열로 빠지고, 실행된 것만 합쳐진다).
    inc_edges = incoming_edges.get(node_id, [])
    inc_source_ids = [inc['source'] for inc in inc_edges]
    if inc_source_ids:
        src_list_literal = ", ".join(f"'{sid}'" for sid in inc_source_ids)
        lines.append(f"{indent}merge_vals_{node_id} = [str(__node_results__.get(_sid, '')) for _sid in [{src_list_literal}] if __node_results__.get(_sid, '')]")
        lines.append(f"{indent}if not merge_vals_{node_id}:")
        lines.append(f"{indent}    merge_vals_{node_id} = [str({prev_res_var if prev_res_var else 'last_result'})]")
    else:
        lines.append(f"{indent}merge_vals_{node_id} = [str({prev_res_var if prev_res_var else 'last_result'})]")

    if strategy == 'join_newline':
        lines.append(f"{indent}merge_out_{node_id} = '\\n'.join(merge_vals_{node_id})")
    elif strategy == 'join_comma':
        lines.append(f"{indent}merge_out_{node_id} = ', '.join(merge_vals_{node_id})")
    elif strategy == 'array':
        lines.append(f"{indent}import json")
        lines.append(f"{indent}merge_out_{node_id} = json.dumps(merge_vals_{node_id}, ensure_ascii=False)")
        
    lines.append(f"{indent}last_result = merge_out_{node_id}")
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"merge_out_{node_id}", visited=visited)

@node_registry.register('distributorNode')
def generate_distributor_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Distributor Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}dist_list_{node_id} = {prev_res_var if prev_res_var else 'last_result'}")
    lines.append(f"{indent}if not isinstance(dist_list_{node_id}, list):")
    lines.append(f"{indent}    dist_list_{node_id} = [dist_list_{node_id}]")

    # 항목별 결과를 **모두 모은다.** 예전에는 `acc = last_result` 로 매 반복 덮어써서 done
    # 경로가 **마지막 항목 하나만** 받았다 — "문단 여러 개를 한 번에 번역" 같은 워크플로우가
    # 마지막 문단만 내놓았다(실제로 겪음). loopNode 는 직전 결과를 다음 회차에 넘기는 게
    # 의도라 지금 방식이 맞지만, distributorNode 는 "목록 각각 처리" 라 모아야 한다.
    #
    # 모은 뒤에는 **줄바꿈으로 이어 붙여 문자열로 넘긴다.** 리스트를 그대로 넘기면 뒤에 오는
    # 노드(메시지 본문, 출력 등)가 `['a', 'b']` 를 그대로 받아 깨진다.
    acc_var = f"dist_acc_{node_id}"
    joined_var = f"dist_joined_{node_id}"
    lines.append(f"{indent}{acc_var} = []")
    lines.append(f"{indent}for dist_item_{node_id} in dist_list_{node_id}:")
    lines.append(f"{indent}    last_result = dist_item_{node_id}")

    # 'done' 핸들 엣지는 반복 밖(전 항목 처리 후 딱 한 번)에서 이어간다 — loopNode의 done과 동일한 패턴.
    # 이게 없으면 반복 안에서 outputNode에 닿는 순간 return이 실행돼 첫 항목만 처리하고 끝나버린다.
    body_edges = [(t, h) for t, h in forward_edges.get(node_id, []) if h != 'done']
    if not body_edges:
        lines.append(f"{indent}    pass")
    else:
        for target_id, handle in body_edges:
            generate_block_fn(target_id, indent + "    ", active_llm_id=active_llm_id, prev_res_var=f"dist_item_{node_id}", visited=visited)
    lines.append(f"{indent}    {acc_var}.append(last_result)")

    # 빈 값은 빼고 이어 붙인다 — 조건 분기로 건너뛴 항목이 빈 줄로 남으면 결과가 지저분해진다.
    lines.append(f"{indent}{joined_var} = '\\n'.join(str(_r) for _r in {acc_var} if str(_r).strip())")
    lines.append(f"{indent}last_result = {joined_var}")
    # 전 항목 처리가 끝난 합본을 기록한다 — 없으면 done 뒤 mergeNode 가 이 노드 결과를 못 본다.
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result={joined_var})")

    done_edges = [t for t, h in forward_edges.get(node_id, []) if h == 'done']
    if done_edges:
        generate_block_fn(done_edges[0], indent, active_llm_id=active_llm_id, prev_res_var=joined_var, visited=visited)
