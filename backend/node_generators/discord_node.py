from node_registry import node_registry

@node_registry.register('discordNode')
def generate_discord_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    node_data = node.get('data', {})
    bot_token = node_data.get('botToken', '').strip()
    channel_id = node_data.get('channelId', '').strip()
    
    lines.append(f"{indent}# --- Discord Action Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}msg_content = {prev_res_var if prev_res_var else 'last_result'}")
    lines.append(f"{indent}bot_token = {repr(bot_token)}")
    lines.append(f"{indent}channel_id = {repr(channel_id)}")
    
    lines.append(f"{indent}import requests")
    lines.append(f"{indent}if bot_token.startswith('http'):")
    lines.append(f"{indent}    resp = requests.post(bot_token, json={{'content': str(msg_content)[:2000]}})")
    lines.append(f"{indent}else:")
    lines.append(f"{indent}    headers = {{'Authorization': f'Bot {{bot_token}}'}}")
    lines.append(f"{indent}    url = f'https://discord.com/api/v10/channels/{{channel_id}}/messages'")
    lines.append(f"{indent}    resp = requests.post(url, headers=headers, json={{'content': str(msg_content)[:2000]}})")
    
    lines.append(f"{indent}if resp.status_code not in (200, 204):")
    lines.append(f"{indent}    print(f'Discord send failed: {{resp.status_code}} {{resp.text}}')")
    
    lines.append(f"{indent}res_text_{node_id} = f'Discord Message Sent. Status: {{resp.status_code}}'")
    lines.append(f"{indent}last_result = res_text_{node_id}")
    
    lines.append(f"{indent}log_step(\'{node_id}\', \'discordNode\', _start_{node_id}, result=last_result)")
    
    next_edges = forward_edges.get(node_id, [])
    if not next_edges:
        lines.append(f"{indent}return last_result")
    else:
        for target_id, handle in next_edges:
            generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)
