import os
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()

import os
from typing import TypedDict, Annotated, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

def compile_workflow(nodes: list, edges: list) -> str:
    """
    Parses the graph data (순방향 탐색) and generates imperative Python LangChain code.
    """
    if not nodes:
        return "Error: Graph is empty. Please drag and drop nodes from the sidebar."

    node_dict = {n['id']: n for n in nodes}
    
    forward_edges = {}
    for e in edges:
        source = e['source']
        if source not in forward_edges:
            forward_edges[source] = []
        forward_edges[source].append((e['target'], e.get('sourceHandle')))
        
    has_incoming = set(e['target'] for e in edges)
    roots = [n for n in nodes if n['id'] not in has_incoming]
    
    if not roots:
        roots = nodes
    if not roots:
        return "Error: No valid starting node found."
        
    root_node = roots[0]
    
    lines = []
    lines.append("import os")
    lines.append("from langchain_google_genai import ChatGoogleGenerativeAI")
    lines.append("from langchain_core.prompts import ChatPromptTemplate")
    lines.append("from dotenv import load_dotenv\n")
    lines.append("load_dotenv()\n")
    lines.append("def is_numeric(s):")
    lines.append("    try:")
    lines.append("        float(s)")
    lines.append("        return True")
    lines.append("    except ValueError:")
    lines.append("        return False\n")
    lines.append("def run_workflow():")
    lines.append("    last_result = 'No execution occurred.'")
    
    def generate_block(node_id, indent, active_llm_id=None, prev_res_var=None):
        node = node_dict.get(node_id)
        if not node:
            return
            
        if node['type'] == 'llmNode':
            model = node.get('data', {}).get('model', 'gemini-3.5-flash')
            # Escape quotes and newlines. Also double curly braces to prevent LangChain from parsing them as variables.
            sys_prompt = node.get('data', {}).get('systemPrompt', 'You are a helpful assistant.')
            sys_prompt = sys_prompt.replace('{', '{{').replace('}', '}}')
            sys_prompt = sys_prompt.replace('"', '\\"').replace('\n', '\\n')
            
            lines.append(f"{indent}# --- LLM Node ({node_id}) ---")
            lines.append(f"{indent}sys_prompt_{node_id} = \"{sys_prompt}\"")
            lines.append(f"{indent}llm_{node_id} = ChatGoogleGenerativeAI(model=\"{model}\")")
            
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=node_id, prev_res_var=prev_res_var)
                
        elif node['type'] == 'promptNode':
            if not active_llm_id:
                lines.append(f"{indent}# Error: Prompt node '{node_id}' has no active LLM.")
                return
                
            user_prompt = node.get('data', {}).get('userPrompt', '').replace('"', '\\"').replace('\n', '\\n')
            lines.append(f"{indent}# --- Prompt Node ({node_id}) ---")
            
            if prev_res_var:
                # Combine previous result with current prompt using string concatenation, NOT f-strings
                lines.append(f"{indent}full_prompt_{node_id} = {prev_res_var} + \"\\n\\n{user_prompt}\"")
            else:
                lines.append(f"{indent}full_prompt_{node_id} = \"{user_prompt}\"")
                
            # Use {user_input} in the template to safely pass the combined text without triggering template errors
            lines.append(f"{indent}prompt_{node_id} = ChatPromptTemplate.from_messages([('system', sys_prompt_{active_llm_id}), ('user', \"{{user_input}}\")])")
            lines.append(f"{indent}chain_{node_id} = prompt_{node_id} | llm_{active_llm_id}")
            lines.append(f"{indent}res_obj_{node_id} = chain_{node_id}.invoke({{\"user_input\": full_prompt_{node_id}}})")
            # Extract content to a pure string immediately
            lines.append(f"{indent}res_text_{node_id} = str(res_obj_{node_id}.content)")
            lines.append(f"{indent}last_result = res_text_{node_id}")
            
            next_edges = forward_edges.get(node_id, [])
            if not next_edges:
                lines.append(f"{indent}return last_result")
            else:
                for target_id, handle in next_edges:
                    generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}")
                    
        elif node['type'] == 'conditionNode':
            rules = node.get('data', {}).get('rules', [])
            if not prev_res_var:
                lines.append(f"{indent}# Error: Switch node missing previous result")
                return
                
            lines.append(f"{indent}# --- Switch / Branch Node ({node_id}) ---")
            lines.append(f"{indent}switch_val = str({prev_res_var}).strip()")
            
            first_if = True
            for rule in rules:
                op = rule.get('operator', '==')
                val = rule.get('value', '').replace('"', '\\"')
                rule_id = rule.get('id')
                
                if op == '==':
                    cond_str = f"switch_val == \"{val}\""
                elif op == 'Contains':
                    cond_str = f"\"{val}\" in switch_val"
                elif op in ('>', '<', '>=', '<='):
                    cond_str = f"is_numeric(switch_val) and is_numeric(\"{val}\") and float(switch_val) {op} float(\"{val}\")"
                else:
                    continue
                    
                keyword = "if" if first_if else "elif"
                lines.append(f"{indent}{keyword} {cond_str}:")
                
                edges = [t for t, h in forward_edges.get(node_id, []) if h == rule_id]
                if edges:
                    generate_block(edges[0], indent + "    ", active_llm_id=active_llm_id, prev_res_var=prev_res_var)
                else:
                    lines.append(f"{indent}    pass")
                first_if = False
                
            if first_if:
                # No rules were generated (empty rules array)
                lines.append(f"{indent}if False:")
                lines.append(f"{indent}    pass")
                
            lines.append(f"{indent}else:")
            else_edges = [t for t, h in forward_edges.get(node_id, []) if h == 'else']
            if else_edges:
                generate_block(else_edges[0], indent + "    ", active_llm_id=active_llm_id, prev_res_var=prev_res_var)
            else:
                lines.append(f"{indent}    pass")
                
        elif node['type'] == 'valueNode':
            val_text = node.get('data', {}).get('value', '').replace('"', '\\"').replace('\n', '\\n')
            lines.append(f"{indent}# --- Value Node ({node_id}) ---")
            lines.append(f"{indent}val_{node_id} = \"{val_text}\"")
            lines.append(f"{indent}last_result = val_{node_id}")
            
            next_edges = forward_edges.get(node_id, [])
            if not next_edges:
                lines.append(f"{indent}return last_result")
            else:
                for target_id, handle in next_edges:
                    generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"val_{node_id}")
                    
        elif node['type'] == 'outputNode':
            lines.append(f"{indent}# --- Output Node ({node_id}) ---")
            if prev_res_var:
                lines.append(f"{indent}return {prev_res_var}")
            else:
                lines.append(f"{indent}return last_result")

    # Start generation from root
    generate_block(root_node['id'], "    ")
    
    # If the block didn't explicitly return (e.g. no output node), add a fallback return
    if "return last_result" not in lines[-1]:
         lines.append("    return last_result")

    lines.append("\nif __name__ == '__main__':")
    lines.append("    print(run_workflow())")
    
    return "\n".join(lines)


def run_workflow(nodes: list, edges: list) -> str:
    """
    Compiles the graph into Python code and dynamically executes it using exec().
    """
    python_code = compile_workflow(nodes, edges)
    
    if python_code.startswith("Error"):
        return python_code
        
    # Dynamically execute the generated code
    local_vars = {}
    try:
        # We wrap it in a try-except to catch compile/runtime errors safely
        exec(python_code, globals(), local_vars)
        if 'run_workflow' in local_vars:
            result = local_vars['run_workflow']()
            return str(result)
        else:
            return "Execution failed: run_workflow function not found."
    except Exception as e:
        return f"Dynamic Execution Error: {str(e)}"
