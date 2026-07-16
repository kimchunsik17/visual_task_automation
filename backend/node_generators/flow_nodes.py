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

@node_registry.register('conditionNode')
def generate_condition_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    rules = node.get('data', {}).get('rules', [])
    var = prev_res_var if prev_res_var else 'last_result'

    lines.append(f"{indent}# --- Condition Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")

    edge_by_handle = {handle: target for target, handle in forward_edges.get(node_id, [])}

    def _emit_branch(handle, branch_indent):
        target_id = edge_by_handle.get(handle)
        if target_id is None:
            lines.append(f"{branch_indent}pass")
        else:
            generate_block_fn(target_id, branch_indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)

    def _cond_expr(operator, value):
        value_escaped = str(value).replace('"', '\\"')
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
        
    done_edges = [t for t, h in forward_edges.get(node_id, []) if h == 'done']
    if done_edges:
        generate_block_fn(done_edges[0], indent, active_llm_id=active_llm_id, prev_res_var=acc_var, visited=visited)

@node_registry.register('breakNode')
def generate_break_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Break Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}break")

@node_registry.register('mergeNode')
def generate_merge_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Merge Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    strategy = node.get('data', {}).get('mergeStrategy', 'join_newline')
    
    lines.append(f"{indent}merge_in_dict_{node_id} = {{}}")
    inc_edges = incoming_edges.get(node_id, [])
    for inc in inc_edges:
        src_id = inc['source']
        lines.append(f"{indent}merge_in_dict_{node_id}['{src_id}'] = __global_results.get('{src_id}', '') if '{src_id}' in globals().get('__global_results', {{}}) else ''")
        
    lines.append(f"{indent}# Simple fallback to prev_res_var if complex branching isn't fully supported")
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
    lines.append(f"{indent}for dist_item_{node_id} in dist_list_{node_id}:")
    lines.append(f"{indent}    last_result = dist_item_{node_id}")
    
    next_edges = forward_edges.get(node_id, [])
    if not next_edges:
        lines.append(f"{indent}    pass")
    else:
        for target_id, handle in next_edges:
            generate_block_fn(target_id, indent + "    ", active_llm_id=active_llm_id, prev_res_var=f"dist_item_{node_id}", visited=visited)
