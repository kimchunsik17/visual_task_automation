from node_registry import node_registry

@node_registry.register("slackNode")
def generate_slack_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    channel = node.get('data', {}).get('channel', '#general')
    message = node.get('data', {}).get('message', 'Hello from Visual Task Automation!')
    
    # Use repr to safely escape newlines and quotes in the generated python code
    safe_channel = repr(channel)
    safe_message_base = repr(message)
    
    lines.append(f"{indent}# --- Slack Node ({node_id}) ---")
    lines.append(f"{indent}slack_channel_{node_id} = {safe_channel}")
    
    if prev_res_var:
        # Strip the trailing quote, append newlines, then close the quote + append variable
        safe_message = safe_message_base[:-1] + "\\n\\n\" + str(" + prev_res_var + ")"
        lines.append(f"{indent}slack_msg_{node_id} = {safe_message}")
    else:
        lines.append(f"{indent}slack_msg_{node_id} = {safe_message_base}")
        
    lines.append(f"{indent}print(f'Mocking Slack send to {{slack_channel_{node_id}}}: {{slack_msg_{node_id}}}')")
    lines.append(f"{indent}last_result = f'Sent message to Slack channel {{slack_channel_{node_id}}}'")
    
    next_edges = forward_edges.get(node_id, [])
    if not next_edges:
        lines.append(f"{indent}return last_result")
    else:
        for target_id, handle in next_edges:
            generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"last_result", visited=visited)
