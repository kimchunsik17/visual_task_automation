import datetime
from node_registry import node_registry

@node_registry.register('outputNode')
def generate_output_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Output Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}return {prev_res_var if prev_res_var else 'last_result'}")

@node_registry.register('humanApprovalNode')
def generate_human_approval_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # 예전엔 거절 시 무조건 raise(=워크플로우 전체가 죽음)만 가능해서, tpl5/7/10처럼
    # "승인/거절에 따라 다르게 알림"을 만들려고 뒤에 conditionNode(==승인)를 붙이는 패턴이
    # 실제로는 절대 안 통했다 — last_result가 항상 원본 값 그대로라 리터럴 "승인"과 절대
    # 같아지지 않았기 때문. conditionNode처럼 이 노드 스스로 sourceHandle
    # 'approved'/'rejected'(또는 'else')로 분기하도록 바꾼다. 핸들 없는 기존 단순 연결
    # (승인 시 그냥 다음으로) 방식도 그대로 지원한다 — 거절되면 여전히 raise로 중단.
    lines.append(f"{indent}# --- Human Approval Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    var_to_use = prev_res_var if prev_res_var else 'last_result'

    lines.append(f"{indent}if 'approval_decision' in kwargs:")
    lines.append(f"{indent}    approval_{node_id} = kwargs.get('approval_decision')")
    lines.append(f"{indent}else:")
    lines.append(f"{indent}    print(f'\\n[Human Approval Required] {{str({var_to_use})}}')")
    lines.append(f"{indent}    approval_{node_id} = 'Y'  # 실제 승인 UI가 연결되기 전까지는 API 모드에서 자동 승인")

    lines.append(f"{indent}last_result = {var_to_use}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")

    all_edges = forward_edges.get(node_id, [])
    approved_edges = [t for t, h in all_edges if h == 'approved']
    rejected_edges = [t for t, h in all_edges if h in ('rejected', 'else')]
    plain_edges = [t for t, h in all_edges if h not in ('approved', 'rejected', 'else')]

    if approved_edges or rejected_edges:
        lines.append(f"{indent}if str(approval_{node_id}).strip().upper() in ['Y', 'YES', 'APPROVE', 'TRUE', '1']:")
        approve_targets = approved_edges + plain_edges
        if approve_targets:
            for t in approve_targets:
                generate_block_fn(t, indent + "    ", active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)
        else:
            lines.append(f"{indent}    pass")
        lines.append(f"{indent}else:")
        if rejected_edges:
            for t in rejected_edges:
                generate_block_fn(t, indent + "    ", active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)
        else:
            lines.append(f"{indent}    raise Exception('Workflow execution halted by Human Approval Node (Rejected).')")
    else:
        lines.append(f"{indent}if str(approval_{node_id}).strip().upper() not in ['Y', 'YES', 'APPROVE', 'TRUE', '1']:")
        lines.append(f"{indent}    raise Exception('Workflow execution halted by Human Approval Node (Rejected).')")
        for t in plain_edges:
            generate_block_fn(t, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)
