import datetime
import json
from node_registry import node_registry

def _extract_text(obj):
    if hasattr(obj, 'content'):
        c = obj.content
        if isinstance(c, list):
            return '\n'.join([str(x.get('text', x)) if isinstance(x, dict) else str(x) for x in c])
        return str(c)
    elif isinstance(obj, dict) and 'content' in obj:
        return str(obj['content'])
    return str(obj)

@node_registry.register('valueNode')
def generate_value_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    file_path = node.get('data', {}).get('file_path', '').replace('\\', '/')
    val = node.get('data', {}).get('value', '').replace('"', '\\"').replace('\n', '\\n')
    lines.append(f"{indent}# --- Value Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    
    if file_path:
        lines.append(f"{indent}import os")
        lines.append(f"{indent}file_content_{node_id} = ''")
        lines.append(f"{indent}try:")
        lines.append(f"{indent}    if os.path.exists(r\"{file_path}\"):")
        lines.append(f"{indent}        with open(r\"{file_path}\", 'r', encoding='utf-8', errors='replace') as f:")
        lines.append(f"{indent}            file_content_{node_id} = f.read()")
        lines.append(f"{indent}    else:")
        lines.append(f"{indent}        file_content_{node_id} = 'File not found'")
        lines.append(f"{indent}except Exception as e:")
        lines.append(f"{indent}    file_content_{node_id} = f'Error reading file: {{str(e)}}'")
        
        if prev_res_var:
            lines.append(f"{indent}val_{node_id} = f\"{{{prev_res_var}}}\\n\\n[Attached File: {file_path}]:\\n{{file_content_{node_id}}}\"")
        else:
            lines.append(f"{indent}val_{node_id} = f\"[Attached File: {file_path}]:\\n{{file_content_{node_id}}}\"")
    else:
        if prev_res_var:
            lines.append(f"{indent}val_{node_id} = f\"{{{prev_res_var}}}\\n\\n[Value]:\\n{val}\"")
        else:
            lines.append(f"{indent}val_{node_id} = \"{val}\"")
        
    lines.append(f"{indent}last_result = val_{node_id}")
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"val_{node_id}", visited=visited)


@node_registry.register('promptNode')
def generate_prompt_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # Dynamically find connected LLM Node
    for inc in incoming_edges.get(node_id, []):
        src_node = node_dict.get(inc['source'])
        if src_node and src_node['type'] == 'llmNode':
            active_llm_id = inc['source']
    for fwd in forward_edges.get(node_id, []):
        tgt_node = node_dict.get(fwd[0])
        if tgt_node and tgt_node['type'] == 'llmNode':
            active_llm_id = fwd[0]
            
    if not active_llm_id:
        lines.append(f"{indent}# --- Fallback LLM for Prompt Node ({node_id}) ---")
        lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
        lines.append(f"{indent}llm_fb_{node_id} = ChatGoogleGenerativeAI(model=\"gemini-1.5-flash\", max_retries=0)")
        lines.append(f"{indent}sys_fb_{node_id} = \"You are a helpful assistant.\"")
        current_llm = f"fb_{node_id}"
        sys_var = f"sys_fb_{node_id}"
    else:
        current_llm = active_llm_id
        sys_var = f"sys_prompt_{active_llm_id}"
        
    user_prompt = node.get('data', {}).get('userPrompt', '').replace('"', '\\"').replace('\n', '\\n')
    lines.append(f"{indent}# --- Prompt Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    
    if prev_res_var:
        lines.append(f"{indent}full_prompt_{node_id} = str({prev_res_var}) + \"\\n\\n{user_prompt}\"")
    else:
        lines.append(f"{indent}full_prompt_{node_id} = \"{user_prompt}\"")
        
    llm_n = node_dict.get(current_llm) if current_llm and not current_llm.startswith("fb_") else None
    use_memory = llm_n.get('data', {}).get('useMemory', False) if llm_n else False
    use_structured = llm_n.get('data', {}).get('useStructuredOutput', False) if llm_n else False
    json_schema_str = llm_n.get('data', {}).get('jsonSchema', '').replace('\n', '\\n').replace('"', '\\"') if llm_n else ""
    
    lines.append(f"{indent}import json")
    lines.append(f"{indent}sys_msg_{node_id} = SystemMessage(content={sys_var})")
    
    if use_structured and json_schema_str:
        lines.append(f"{indent}schema_dict_{node_id} = json.loads(\"{json_schema_str}\")")
        lines.append(f"{indent}structured_llm_{node_id} = llm_{current_llm}.with_structured_output(schema_dict_{node_id}, include_raw=True)")
        target_llm = f"structured_llm_{node_id}"
    else:
        target_llm = f"llm_{current_llm}"
        
    if use_memory:
        lines.append(f"{indent}history_msgs_{node_id} = []")
        lines.append(f"{indent}mem_record_{node_id} = None")
        lines.append(f"{indent}if db:")
        lines.append(f"{indent}    session_id = kwargs.get('session_id', 'default')")
        lines.append(f"{indent}    project_id = kwargs.get('project_id', 0)")
        lines.append(f"{indent}    mem_record_{node_id} = db.query(models.NodeMemory).filter_by(session_id=session_id, project_id=project_id, node_id='{node_id}').first()")
        lines.append(f"{indent}    if mem_record_{node_id}:")
        lines.append(f"{indent}        history_msgs_{node_id} = messages_from_dict(json.loads(mem_record_{node_id}.history))")
        
        lines.append(f"{indent}prompt_{node_id} = ChatPromptTemplate.from_messages([sys_msg_{node_id}, ('placeholder', '{{history}}'), ('user', \"{{user_input}}\")])")
        lines.append(f"{indent}chain_{node_id} = prompt_{node_id} | {target_llm}")
        
        if use_structured and json_schema_str:
            lines.append(f"{indent}res_obj_wrapper_{node_id} = chain_{node_id}.invoke({{'history': history_msgs_{node_id}, 'user_input': full_prompt_{node_id}}})")
            lines.append(f"{indent}res_obj_{node_id} = res_obj_wrapper_{node_id}['raw']")
            lines.append(f"{indent}res_text_{node_id} = json.dumps(res_obj_wrapper_{node_id}['parsed'], ensure_ascii=False)")
        else:
            lines.append(f"{indent}res_obj_{node_id} = chain_{node_id}.invoke({{'history': history_msgs_{node_id}, 'user_input': full_prompt_{node_id}}})")
            lines.append(f"{indent}res_text_{node_id} = _extract_text(res_obj_{node_id})")
        
        lines.append(f"{indent}if db:")
        lines.append(f"{indent}    history_msgs_{node_id}.append(HumanMessage(content=full_prompt_{node_id}))")
        lines.append(f"{indent}    history_msgs_{node_id}.append(AIMessage(content=res_text_{node_id}))")
        lines.append(f"{indent}    if not mem_record_{node_id}:")
        lines.append(f"{indent}        mem_record_{node_id} = models.NodeMemory(session_id=session_id, project_id=project_id, node_id='{node_id}', history=json.dumps(messages_to_dict(history_msgs_{node_id}), ensure_ascii=False))")
        lines.append(f"{indent}        db.add(mem_record_{node_id})")
        lines.append(f"{indent}    else:")
        lines.append(f"{indent}        mem_record_{node_id}.history = json.dumps(messages_to_dict(history_msgs_{node_id}), ensure_ascii=False)")
        lines.append(f"{indent}    db.commit()")
    else:
        lines.append(f"{indent}prompt_{node_id} = ChatPromptTemplate.from_messages([sys_msg_{node_id}, ('user', \"{{user_input}}\")])")
        lines.append(f"{indent}chain_{node_id} = prompt_{node_id} | {target_llm}")
        
        if use_structured and json_schema_str:
            lines.append(f"{indent}res_obj_wrapper_{node_id} = chain_{node_id}.invoke({{\"user_input\": full_prompt_{node_id}}})")
            lines.append(f"{indent}res_obj_{node_id} = res_obj_wrapper_{node_id}['raw']")
            lines.append(f"{indent}res_text_{node_id} = json.dumps(res_obj_wrapper_{node_id}['parsed'], ensure_ascii=False)")
        else:
            lines.append(f"{indent}res_obj_{node_id} = chain_{node_id}.invoke({{\"user_input\": full_prompt_{node_id}}})")
            lines.append(f"{indent}res_text_{node_id} = _extract_text(res_obj_{node_id})")
    
    lines.append(f"{indent}usage_dict = getattr(res_obj_{node_id}, 'usage_metadata', None)")
    lines.append(f"{indent}if not usage_dict and hasattr(res_obj_{node_id}, 'response_metadata'):")
    lines.append(f"{indent}    rm = res_obj_{node_id}.response_metadata")
    lines.append(f"{indent}    if 'token_usage' in rm: usage_dict = rm['token_usage']")
    lines.append(f"{indent}if usage_dict:")
    lines.append(f"{indent}    __token_usage__['nodes']['{node_id}'] = usage_dict")
    lines.append(f"{indent}    __token_usage__['total_input'] += usage_dict.get('input_tokens', usage_dict.get('prompt_tokens', 0))")
    lines.append(f"{indent}    __token_usage__['total_output'] += usage_dict.get('output_tokens', usage_dict.get('completion_tokens', 0))")
    lines.append(f"{indent}    __token_usage__['total_tokens'] += usage_dict.get('total_tokens', 0)")
    
    lines.append(f"{indent}last_result = res_text_{node_id}")
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register('llmNode')
def generate_llm_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- LLM Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    
    if active_llm_id != node_id:
        user_prompt = node.get('data', {}).get('userPrompt', '').replace('"', '\\"').replace('\n', '\\n')
        if prev_res_var:
            lines.append(f"{indent}full_prompt_{node_id} = str({prev_res_var}) + \"\\n\\n{user_prompt}\"")
        else:
            lines.append(f"{indent}full_prompt_{node_id} = \"{user_prompt}\"")
            
        use_memory = node.get('data', {}).get('useMemory', False)
        use_structured = node.get('data', {}).get('useStructuredOutput', False)
        json_schema_str = node.get('data', {}).get('jsonSchema', '').replace('\n', '\\n').replace('"', '\\"')
        
        lines.append(f"{indent}import json")
        lines.append(f"{indent}sys_msg_sa_{node_id} = SystemMessage(content=sys_prompt_{node_id})")
        
        if use_structured and json_schema_str:
            lines.append(f"{indent}schema_dict_{node_id} = json.loads(\"{json_schema_str}\")")
            lines.append(f"{indent}structured_llm_{node_id} = llm_{node_id}.with_structured_output(schema_dict_{node_id}, include_raw=True)")
            target_llm = f"structured_llm_{node_id}"
        else:
            target_llm = f"llm_{node_id}"
        
        if use_memory:
            lines.append(f"{indent}history_msgs_{node_id} = []")
            lines.append(f"{indent}mem_record_{node_id} = None")
            lines.append(f"{indent}if db:")
            lines.append(f"{indent}    session_id = kwargs.get('session_id', 'default')")
            lines.append(f"{indent}    project_id = kwargs.get('project_id', 0)")
            lines.append(f"{indent}    mem_record_{node_id} = db.query(models.NodeMemory).filter_by(session_id=session_id, project_id=project_id, node_id='{node_id}').first()")
            lines.append(f"{indent}    if mem_record_{node_id}:")
            lines.append(f"{indent}        history_msgs_{node_id} = messages_from_dict(json.loads(mem_record_{node_id}.history))")
            
            lines.append(f"{indent}prompt_sa_{node_id} = ChatPromptTemplate.from_messages([sys_msg_sa_{node_id}, ('placeholder', '{{history}}'), ('user', \"{{user_input}}\")])")
            lines.append(f"{indent}chain_sa_{node_id} = prompt_sa_{node_id} | {target_llm}")
            
            if use_structured and json_schema_str:
                lines.append(f"{indent}res_obj_wrapper_{node_id} = chain_sa_{node_id}.invoke({{'history': history_msgs_{node_id}, 'user_input': full_prompt_{node_id}}})")
                lines.append(f"{indent}res_obj_sa_{node_id} = res_obj_wrapper_{node_id}['raw']")
                lines.append(f"{indent}res_text_{node_id} = json.dumps(res_obj_wrapper_{node_id}['parsed'], ensure_ascii=False)")
            else:
                lines.append(f"{indent}res_obj_sa_{node_id} = chain_sa_{node_id}.invoke({{'history': history_msgs_{node_id}, 'user_input': full_prompt_{node_id}}})")
                lines.append(f"{indent}res_text_{node_id} = _extract_text(res_obj_sa_{node_id})")
            
            lines.append(f"{indent}if db:")
            lines.append(f"{indent}    history_msgs_{node_id}.append(HumanMessage(content=full_prompt_{node_id}))")
            lines.append(f"{indent}    history_msgs_{node_id}.append(AIMessage(content=res_text_{node_id}))")
            lines.append(f"{indent}    if not mem_record_{node_id}:")
            lines.append(f"{indent}        mem_record_{node_id} = models.NodeMemory(session_id=session_id, project_id=project_id, node_id='{node_id}', history=json.dumps(messages_to_dict(history_msgs_{node_id}), ensure_ascii=False))")
            lines.append(f"{indent}        db.add(mem_record_{node_id})")
            lines.append(f"{indent}    else:")
            lines.append(f"{indent}        mem_record_{node_id}.history = json.dumps(messages_to_dict(history_msgs_{node_id}), ensure_ascii=False)")
            lines.append(f"{indent}    db.commit()")
        else:
            lines.append(f"{indent}prompt_sa_{node_id} = ChatPromptTemplate.from_messages([sys_msg_sa_{node_id}, ('user', \"{{user_input}}\")])")
            lines.append(f"{indent}chain_sa_{node_id} = prompt_sa_{node_id} | {target_llm}")
            
            if use_structured and json_schema_str:
                lines.append(f"{indent}res_obj_wrapper_{node_id} = chain_sa_{node_id}.invoke({{\"user_input\": full_prompt_{node_id}}})")
                lines.append(f"{indent}res_obj_sa_{node_id} = res_obj_wrapper_{node_id}['raw']")
                lines.append(f"{indent}res_text_{node_id} = json.dumps(res_obj_wrapper_{node_id}['parsed'], ensure_ascii=False)")
            else:
                lines.append(f"{indent}res_obj_sa_{node_id} = chain_sa_{node_id}.invoke({{\"user_input\": full_prompt_{node_id}}})")
                lines.append(f"{indent}res_text_{node_id} = _extract_text(res_obj_sa_{node_id})")
        
        lines.append(f"{indent}usage_dict_sa = getattr(res_obj_sa_{node_id}, 'usage_metadata', None)")
        lines.append(f"{indent}if not usage_dict_sa and hasattr(res_obj_sa_{node_id}, 'response_metadata'):")
        lines.append(f"{indent}    rm_sa = res_obj_sa_{node_id}.response_metadata")
        lines.append(f"{indent}    if 'token_usage' in rm_sa: usage_dict_sa = rm_sa['token_usage']")
        lines.append(f"{indent}if usage_dict_sa:")
        lines.append(f"{indent}    __token_usage__['nodes']['{node_id}'] = usage_dict_sa")
        lines.append(f"{indent}    __token_usage__['total_input'] += usage_dict_sa.get('input_tokens', usage_dict_sa.get('prompt_tokens', 0))")
        lines.append(f"{indent}    __token_usage__['total_output'] += usage_dict_sa.get('output_tokens', usage_dict_sa.get('completion_tokens', 0))")
        lines.append(f"{indent}    __token_usage__['total_tokens'] += usage_dict_sa.get('total_tokens', 0)")

        lines.append(f"{indent}last_result = res_text_{node_id}")
        pass_var = f"res_text_{node_id}"
    else:
        pass_var = prev_res_var
        
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=node_id, prev_res_var=pass_var, visited=visited)
