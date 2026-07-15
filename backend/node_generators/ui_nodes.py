import datetime
from node_registry import node_registry

@node_registry.register('outputNode')
def generate_output_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Output Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}return {prev_res_var if prev_res_var else 'last_result'}")

@node_registry.register('humanApprovalNode')
def generate_human_approval_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Human Approval Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    message = node.get('data', {}).get('message', '승인이 필요합니다.').replace('"', '\\"')
    
    lines.append(f"{indent}# To fully support Human-in-the-loop in a deployed API, execution must be paused and state saved.")
    lines.append(f"{indent}# Here we simulate it by requiring 'approval_decision' in kwargs for web context,")
    lines.append(f"{indent}# or using input() for local script execution.")
    lines.append(f"{indent}if 'approval_decision' in kwargs:")
    lines.append(f"{indent}    approval_{node_id} = kwargs.get('approval_decision')")
    lines.append(f"{indent}else:")
    fallback_var = "last_result"
    var_to_use = prev_res_var if prev_res_var else fallback_var
    lines.append(f"{indent}    print(f'\\n[Human Approval Required] {{str({var_to_use})}}')")
    lines.append(f"{indent}    approval_{node_id} = 'Y'  # Auto-approve in API mode if no decision is provided")
    
    lines.append(f"{indent}if str(approval_{node_id}).strip().upper() not in ['Y', 'YES', 'APPROVE', 'TRUE', '1']:")
    lines.append(f"{indent}    raise Exception('Workflow execution halted by Human Approval Node (Rejected).')")
    
    lines.append(f"{indent}last_result = {prev_res_var if prev_res_var else 'last_result'}")
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)
