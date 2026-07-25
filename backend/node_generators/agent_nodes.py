from node_registry import node_registry

def add_tracking(var_name, node_id, indent):
    # Generates code to track token usage dynamically if available
    lines = []
    lines.append(f"{indent}usage_dict_tmp = getattr({var_name}, 'usage_metadata', None)")
    lines.append(f"{indent}if not usage_dict_tmp and hasattr({var_name}, 'response_metadata'):")
    lines.append(f"{indent}    rm_tmp = {var_name}.response_metadata")
    lines.append(f"{indent}    if 'token_usage' in rm_tmp: usage_dict_tmp = rm_tmp['token_usage']")
    lines.append(f"{indent}if usage_dict_tmp:")
    lines.append(f"{indent}    __token_usage__['nodes']['{node_id}'] = usage_dict_tmp")
    lines.append(f"{indent}    __token_usage__['total_input'] += usage_dict_tmp.get('input_tokens', usage_dict_tmp.get('prompt_tokens', 0))")
    lines.append(f"{indent}    __token_usage__['total_output'] += usage_dict_tmp.get('output_tokens', usage_dict_tmp.get('completion_tokens', 0))")
    lines.append(f"{indent}    __token_usage__['total_tokens'] += usage_dict_tmp.get('total_tokens', 0)")
    return "\n".join(lines)

@node_registry.register('multiAgentNode')
def generate_multi_agent_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Multi-Agent Node ({node_id}) ---")
    mode = node.get('data', {}).get('mode', 'supervisor')
    
    # Find incoming tool/agent edges
    sub_nodes = []
    for inc in incoming_edges.get(node_id, []):
        if inc.get('targetHandle') == 'tools':
            src_node = node_dict.get(inc['source'])
            if src_node:
                sub_nodes.append(src_node)
                
    input_val = prev_res_var if prev_res_var else 'last_result'
    
    if mode == 'supervisor':
        supervisor_prompt = node.get('data', {}).get('supervisorPrompt', 'Choose an expert.').replace('"', '\\"').replace('\n', '\\n')
        lines.append(f"{indent}ma_input_{node_id} = str({input_val})")
        
        # Build descriptions
        expert_names = []
        for idx, sub in enumerate(sub_nodes):
            if sub['type'] == 'llmNode':
                name = f"Expert_{idx}"
                desc = sub.get('data', {}).get('systemPrompt', f"Expert {idx}").replace('"', '\\"').replace('\n', ' ')
                expert_names.append(f"- {name}: {desc}")
        
        experts_str = "\\n".join(expert_names)
        lines.append(f"{indent}experts_{node_id} = \"{experts_str}\"")
        lines.append(f"{indent}from langchain_openai import ChatOpenAI")
        lines.append(f"{indent}supervisor_llm_{node_id} = ChatOpenAI(model='gpt-4o-mini')")
        lines.append(f"{indent}sys_msg_sup_{node_id} = SystemMessage(content=f\"{supervisor_prompt}\\nAvailable Experts:\\n{{experts_{node_id}}}\\nRespond ONLY with the exact name of the chosen expert (e.g. Expert_0), or 'None' if none fit.\")")
        lines.append(f"{indent}prompt_sup_{node_id} = ChatPromptTemplate.from_messages([sys_msg_sup_{node_id}, ('user', \"{{user_input}}\")])")
        lines.append(f"{indent}chain_sup_{node_id} = prompt_sup_{node_id} | supervisor_llm_{node_id}")
        lines.append(f"{indent}choice_obj_{node_id} = chain_sup_{node_id}.invoke({{\"user_input\": ma_input_{node_id}}})")
        lines.append(f"{indent}choice_text_{node_id} = _extract_text(choice_obj_{node_id}).strip()")
        lines.append(add_tracking(f"choice_obj_{node_id}", node_id, indent))
        lines.append(f"{indent}print(f'Supervisor chose: {{choice_text_{node_id}}}')")
        
        # Generate execution block for chosen expert
        lines.append(f"{indent}res_ma_{node_id} = f'No suitable expert found. (Supervisor output: {{choice_text_{node_id}}})'")
        for idx, sub in enumerate(sub_nodes):
            if sub['type'] == 'llmNode':
                name = f"Expert_{idx}"
                model = sub.get('data', {}).get('model', 'gpt-4o-mini')
                sys_p = sub.get('data', {}).get('systemPrompt', '').replace('"', '\\"').replace('\n', '\\n')
                lines.append(f"{indent}if '{name}' in choice_text_{node_id}:")
                lines.append(f"{indent}    tmp_llm_{node_id}_{idx} = ChatOpenAI(model='{model}')")
                lines.append(f"{indent}    tmp_sys_{node_id}_{idx} = SystemMessage(content=\"{sys_p}\")")
                lines.append(f"{indent}    tmp_prompt_{node_id}_{idx} = ChatPromptTemplate.from_messages([tmp_sys_{node_id}_{idx}, ('user', \"{{user_input}}\")])")
                lines.append(f"{indent}    tmp_chain_{node_id}_{idx} = tmp_prompt_{node_id}_{idx} | tmp_llm_{node_id}_{idx}")
                lines.append(f"{indent}    tmp_res_{node_id}_{idx} = tmp_chain_{node_id}_{idx}.invoke({{\"user_input\": ma_input_{node_id}}})")
                lines.append(add_tracking(f"tmp_res_{node_id}_{idx}", sub['id'], indent + "    "))
                lines.append(f"{indent}    res_ma_{node_id} = f'[{name} 답변]\\n' + _extract_text(tmp_res_{node_id}_{idx})")
                
        lines.append(f"{indent}last_result = res_ma_{node_id}")
        
    elif mode == 'group_chat':
        max_rounds = node.get('data', {}).get('maxRounds', 3)
        lines.append(f"{indent}ma_input_{node_id} = str({input_val})")
        lines.append(f"{indent}chat_history_{node_id} = [HumanMessage(content=f\'주제: {{ma_input_{node_id}}}\')]")
        lines.append(f"{indent}res_ma_{node_id} = ''")
        
        # Setup LLMs
        for idx, sub in enumerate(sub_nodes):
            if sub['type'] == 'llmNode':
                model = sub.get('data', {}).get('model', 'gpt-4o-mini')
                sys_p = sub.get('data', {}).get('systemPrompt', '').replace('"', '\\"').replace('\n', '\\n')
                lines.append(f"{indent}llm_{node_id}_{idx} = ChatOpenAI(model='{model}')")
                lines.append(f"{indent}sys_{node_id}_{idx} = SystemMessage(content=\"{sys_p}\")")
                
        lines.append(f"{indent}for round_idx in range({max_rounds}):")
        for idx, sub in enumerate(sub_nodes):
            if sub['type'] == 'llmNode':
                name = f"Expert_{idx}"
                lines.append(f"{indent}    tmp_msgs_{node_id}_{idx} = [sys_{node_id}_{idx}] + chat_history_{node_id}")
                lines.append(f"{indent}    tmp_res_{node_id}_{idx} = llm_{node_id}_{idx}.invoke(tmp_msgs_{node_id}_{idx})")
                lines.append(add_tracking(f"tmp_res_{node_id}_{idx}", sub['id'], indent + "    "))
                lines.append(f"{indent}    chat_history_{node_id}.append(AIMessage(content=f'[{name}] ' + _extract_text(tmp_res_{node_id}_{idx})))")
                
        lines.append(f"{indent}res_ma_{node_id} = '\\n\\n'.join([m.content for m in chat_history_{node_id} if isinstance(m, AIMessage)])")
        lines.append(f"{indent}last_result = res_ma_{node_id}")
        
    elif mode == 'tool_agent':
        agent_prompt = node.get('data', {}).get('agentPrompt', 'Solve the task.').replace('"', '\\"').replace('\n', '\\n')
        lines.append(f"{indent}ma_input_{node_id} = str({input_val})")
        lines.append(f"{indent}res_ma_{node_id} = 'Tool Agent not fully implemented for dynamic tools yet.'")
        # Creating tools on the fly in generated python is complex.
        # We will provide a simple mock implementation or pre-built tools for now.
        lines.append(f"{indent}try:")
        lines.append(f"{indent}    from langchain_openai import ChatOpenAI")
        lines.append(f"{indent}    from langgraph.prebuilt import create_react_agent")
        lines.append(f"{indent}    from langchain_community.tools.tavily_search import TavilySearchResults")
        lines.append(f"{indent}    tools_{node_id} = [TavilySearchResults(max_results=2)] # Default tool")
        lines.append(f"{indent}    agent_llm_{node_id} = ChatOpenAI(model='gpt-4o-mini', temperature=0)")
        lines.append(f"{indent}    agent_{node_id} = create_react_agent(agent_llm_{node_id}, tools=tools_{node_id}, prompt=\"{agent_prompt}\")")
        lines.append(f"{indent}    res_obj_{node_id} = agent_{node_id}.invoke({{'messages': [('user', ma_input_{node_id})]}})")
        lines.append(f"{indent}    final_msg_{node_id} = res_obj_{node_id}['messages'][-1]")
        # Note: Tool agent intermediate steps are harder to track directly from AgentExecutor res_obj without callbacks, but some metadata might be available
        lines.append(add_tracking(f"final_msg_{node_id}", node_id, indent + "    "))
        lines.append(f"{indent}    res_ma_{node_id} = _extract_text(final_msg_{node_id})")
        lines.append(f"{indent}except Exception as e:")
        lines.append(f"{indent}    res_ma_{node_id} = f'Tool Agent Error: {{str(e)}}'")
        
        lines.append(f"{indent}last_result = res_ma_{node_id}")

    # Continue flow
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_ma_{node_id}", visited=visited)
