import datetime
from node_registry import node_registry

@node_registry.register('outputNode')
def generate_output_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Output Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    output_var = prev_res_var if prev_res_var else 'last_result'
    lines.append(f"{indent}last_result = {output_var}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    lines.append(f"{indent}return last_result")

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

    # P0(INCOMPLETE_NODE_STRUCTURE_REVIEW §4.1): 자동 승인 제거 — fail-closed.
    # 예전에는 결정값이 없으면 'Y'로 자동 승인했다. 결제·발송·게시 앞에 승인 노드를 둔
    # 사용자는 "사람이 확인한다"고 믿는데, 스케줄/웹훅/API 실행에서는 아무도 확인하지 않고
    # 통과했다. 이제 결정이 없으면 명시적 오류로 실행을 중단한다(durable 대기·재개는 P2).
    # 결정은 노드별(approval_decisions[node_id])이 우선이고, 호출자가 의도적으로 넘기는
    # 전역 approval_decision(평가 파이프라인의 승인 시뮬레이션 등)을 폴백으로 인정한다 —
    # 어느 쪽이든 '명시적으로 전달된 결정'만 유효하고 기본값으로 승인되는 경로는 없다.
    lines.append(f"{indent}_decisions_{node_id} = kwargs.get('approval_decisions') or {{}}")
    lines.append(f"{indent}if isinstance(_decisions_{node_id}, dict) and '{node_id}' in _decisions_{node_id}:")
    lines.append(f"{indent}    approval_{node_id} = _decisions_{node_id}['{node_id}']")
    lines.append(f"{indent}elif 'approval_decision' in kwargs:")
    lines.append(f"{indent}    approval_{node_id} = kwargs.get('approval_decision')")
    lines.append(f"{indent}else:")
    # 결정이 없으면 durable 대기 신호를 던진다(ADR-0015). graph.run_workflow 가 이 신호를
    # ApprovalRequest(사이트/이메일/카카오/디스코드 알림 + 결정 후 이 지점부터 재개)로 바꾼다.
    # DB 가 없는 경로(평가 등)에서는 신호 메시지가 그대로 fail-closed 오류로 남는다 —
    # 어느 경로에서도 자동 승인은 없다.
    var_for_signal = prev_res_var if prev_res_var else 'last_result'
    lines.append(f"{indent}    raise __ApprovalPendingSignal__('{node_id}', {var_for_signal})")

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
