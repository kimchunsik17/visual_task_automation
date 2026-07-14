import os
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

from node_registry import node_registry
import node_generators.slack_node

load_dotenv()

def compile_workflow(nodes: list, edges: list) -> str:
    """
    Parses the graph data (순방향 탐색) and generates imperative Python LangChain code.
    """
    if not nodes:
        return "Error: Graph is empty. Please drag and drop nodes from the sidebar."

    node_dict = {n['id']: n for n in nodes}
    
    forward_edges = {}
    incoming_edges = {}
    control_flow_edges = []
    
    for e in edges:
        source = e['source']
        target = e['target']
        target_handle = e.get('targetHandle')
        
        if target not in incoming_edges:
            incoming_edges[target] = []
        incoming_edges[target].append({
            'source': source,
            'targetHandle': target_handle
        })
        
        # Exclude 'template' handles from control flow traversal
        if target_handle != 'template':
            control_flow_edges.append(e)
            if source not in forward_edges:
                forward_edges[source] = []
            forward_edges[source].append((target, e.get('sourceHandle')))
        
    has_incoming = set(e['target'] for e in control_flow_edges)
    
    # 1. Prioritize explicit Start Nodes
    roots = [n for n in nodes if n['type'] == 'startNode']
    
    # 2. Fallback to old heuristic if no start nodes are found
    if not roots:
        roots = [n for n in nodes if n['id'] not in has_incoming and not n.get('parentNode') and n['type'] != 'llmNode']
        
        if not roots:
            # Final fallback
            roots = [n for n in nodes if not n.get('parentNode')]
            
    if not roots:
        return "Error: No valid starting node found."
        
    # Filter out roots that have no forward connections (unless it's the only one)
    if len(roots) > 1:
        connected_roots = [r for r in roots if r['id'] in forward_edges]
        if connected_roots:
            roots = connected_roots
    
    # Collect used models to generate correct imports
    used_models = set()
    for node in nodes:
        if node['type'] == 'llmNode':
            used_models.add(node.get('data', {}).get('model', 'gemini-3.5-flash'))
    
    needs_gemini = any('gemini' in m for m in used_models)
    needs_openai = any('gpt' in m for m in used_models)
    needs_anthropic = any('claude' in m for m in used_models)

    lines = []
    lines.append("import os")
    lines.append("from langchain_google_genai import ChatGoogleGenerativeAI")
    if needs_openai:
        lines.append("from langchain_openai import ChatOpenAI")
    if needs_anthropic:
        lines.append("from langchain_anthropic import ChatAnthropic")
    lines.append("from langchain_core.prompts import ChatPromptTemplate")
    lines.append("from langchain_core.messages import SystemMessage")
    lines.append("import requests")
    lines.append("from bs4 import BeautifulSoup")
    lines.append("from dotenv import load_dotenv\n")
    lines.append("load_dotenv()\n")
    lines.append("def is_numeric(s):")
    lines.append("    try:")
    lines.append("        float(s)")
    lines.append("        return True")
    lines.append("    except ValueError:")
    lines.append("        return False\n")
    lines.append("__token_usage__ = {'nodes': {}, 'total_input': 0, 'total_output': 0, 'total_tokens': 0}")
    lines.append("def run_workflow(**kwargs):")
    lines.append("    global __token_usage__")
    lines.append("    __token_usage__ = {'nodes': {}, 'total_input': 0, 'total_output': 0, 'total_tokens': 0}")
    lines.append("    last_result = 'No execution occurred.'")
    
    # Generate all LLM configurations at the top of the workflow
    for node in nodes:
        if node['type'] == 'llmNode':
            node_id = node['id']
            model = node.get('data', {}).get('model', 'gemini-3.5-flash')
            sys_prompt = node.get('data', {}).get('systemPrompt', 'You are a helpful assistant.').replace('"', '\\"').replace('\n', '\\n')
            lines.append(f"    # --- LLM Node ({node_id}) ---")
            
            if model == "gpt-4o" or model == "gpt-4o-mini":
                lines.append(f"    llm_{node_id} = ChatOpenAI(model=\"{model}\")")
            elif model == "claude-3-5-sonnet":
                lines.append(f"    llm_{node_id} = ChatAnthropic(model_name=\"claude-3-5-sonnet-20240620\")")
            else:
                lines.append(f"    llm_{node_id} = ChatGoogleGenerativeAI(model=\"{model}\")")
                
            lines.append(f"    sys_prompt_{node_id} = \"{sys_prompt}\"")
    
    def generate_block(node_id, indent, active_llm_id=None, prev_res_var=None, visited=None):
        if visited is None:
            visited = set()
        
        # Prevent cyclic recursion (e.g. from loop_next handles connecting back to the loop node)
        if node_id in visited:
            return
        
        # We only add to visited if it's a loop node, or we can add all nodes.
        # Wait, if a node is visited, it shouldn't be generated again anyway.
        visited = visited.copy()
        visited.add(node_id)
        
        node = node_dict.get(node_id)
        if not node:
            return
            
        # 1. Use Registry if available (New Architecture)
        if node_registry.has_node(node['type']):
            generator = node_registry.get_generator(node['type'])
            generator(
                node_id=node_id,
                node=node,
                indent=indent,
                active_llm_id=active_llm_id,
                prev_res_var=prev_res_var,
                visited=visited,
                node_dict=node_dict,
                forward_edges=forward_edges,
                incoming_edges=incoming_edges,
                lines=lines,
                generate_block_fn=generate_block
            )
            return
            
        # 2. Fallback to Legacy Hardcoded Generation
        if node['type'] == 'startNode':
            lines.append(f"{indent}# --- Start Node ({node_id}) ---")
            next_edges = forward_edges.get(node_id, [])
            if not next_edges:
                lines.append(f"{indent}pass")
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)
                
        elif node['type'] == 'valueNode':
            file_path = node.get('data', {}).get('file_path', '').replace('\\', '/')
            val = node.get('data', {}).get('value', '').replace('"', '\\"').replace('\n', '\\n')
            lines.append(f"{indent}# --- Value Node ({node_id}) ---")
            
            if file_path:
                if prev_res_var:
                    lines.append(f"{indent}val_{node_id} = str({prev_res_var}) + \"\\n\\n[Attached File: \" + r\"{file_path}\" + \"]\"")
                else:
                    lines.append(f"{indent}val_{node_id} = r\"{file_path}\"")
            else:
                if prev_res_var:
                    lines.append(f"{indent}val_{node_id} = str({prev_res_var}) + \"\\n\\n\" + \"{val}\"")
                else:
                    lines.append(f"{indent}val_{node_id} = \"{val}\"")
                
            lines.append(f"{indent}last_result = val_{node_id}")
            
            next_edges = forward_edges.get(node_id, [])
            if not next_edges:
                lines.append(f"{indent}return last_result")
            else:
                for target_id, handle in next_edges:
                    generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"val_{node_id}", visited=visited)
                    
        elif node['type'] == 'promptNode':
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
                lines.append(f"{indent}llm_fb_{node_id} = ChatGoogleGenerativeAI(model=\"gemini-3.5-flash\")")
                lines.append(f"{indent}sys_fb_{node_id} = \"You are a helpful assistant.\"")
                current_llm = f"fb_{node_id}"
                sys_var = f"sys_fb_{node_id}"
            else:
                current_llm = active_llm_id
                sys_var = f"sys_prompt_{active_llm_id}"
                
            user_prompt = node.get('data', {}).get('userPrompt', '').replace('"', '\\"').replace('\n', '\\n')
            lines.append(f"{indent}# --- Prompt Node ({node_id}) ---")
            
            if prev_res_var:
                lines.append(f"{indent}full_prompt_{node_id} = str({prev_res_var}) + \"\\n\\n{user_prompt}\"")
            else:
                lines.append(f"{indent}full_prompt_{node_id} = \"{user_prompt}\"")
                
            lines.append(f"{indent}sys_msg_{node_id} = SystemMessage(content={sys_var})")
            lines.append(f"{indent}prompt_{node_id} = ChatPromptTemplate.from_messages([sys_msg_{node_id}, ('user', \"{{user_input}}\")])")
            lines.append(f"{indent}chain_{node_id} = prompt_{node_id} | llm_{current_llm}")
            lines.append(f"{indent}res_obj_{node_id} = chain_{node_id}.invoke({{\"user_input\": full_prompt_{node_id}}})")
            lines.append(f"{indent}res_text_{node_id} = str(res_obj_{node_id}.content)")
            
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
            
            next_edges = forward_edges.get(node_id, [])
            if not next_edges:
                lines.append(f"{indent}return last_result")
            else:
                for target_id, handle in next_edges:
                    generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)
                    
        elif node['type'] == 'llmNode':
            lines.append(f"{indent}# --- LLM Node ({node_id}) ---")
            
            if active_llm_id != node_id:
                user_prompt = node.get('data', {}).get('userPrompt', '').replace('"', '\\"').replace('\n', '\\n')
                if prev_res_var:
                    lines.append(f"{indent}full_prompt_{node_id} = str({prev_res_var}) + \"\\n\\n{user_prompt}\"")
                else:
                    lines.append(f"{indent}full_prompt_{node_id} = \"{user_prompt}\"")
                    
                lines.append(f"{indent}sys_msg_sa_{node_id} = SystemMessage(content=sys_prompt_{node_id})")
                lines.append(f"{indent}prompt_sa_{node_id} = ChatPromptTemplate.from_messages([sys_msg_sa_{node_id}, ('user', \"{{user_input}}\")])")
                lines.append(f"{indent}chain_sa_{node_id} = prompt_sa_{node_id} | llm_{node_id}")
                lines.append(f"{indent}res_obj_sa_{node_id} = chain_sa_{node_id}.invoke({{\"user_input\": full_prompt_{node_id}}})")
                lines.append(f"{indent}res_text_{node_id} = str(res_obj_sa_{node_id}.content)")
                
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
                generate_block(target_id, indent, active_llm_id=node_id, prev_res_var=pass_var, visited=visited)
                
        elif node['type'] == 'conditionNode':
            condition = node.get('data', {}).get('condition', 'Contains')
            val = node.get('data', {}).get('value', '')
            
            lines.append(f"{indent}# --- Condition Node ({node_id}) ---")
            if condition == 'Contains':
                lines.append(f"{indent}if \"{val}\" in str({prev_res_var if prev_res_var else 'last_result'}):")
            else:
                lines.append(f"{indent}if str({prev_res_var if prev_res_var else 'last_result'}) == \"{val}\":")
                
            true_edges = [t for t, h in forward_edges.get(node_id, []) if h == 'true']
            if true_edges:
                generate_block(true_edges[0], indent + "    ", active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)
            else:
                lines.append(f"{indent}    pass")
                
            lines.append(f"{indent}else:")
            false_edges = [t for t, h in forward_edges.get(node_id, []) if h == 'false']
            if false_edges:
                generate_block(false_edges[0], indent + "    ", active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)
            else:
                lines.append(f"{indent}    pass")
                
        elif node['type'] == 'dynamicInputNode':
            lines.append(f"{indent}# --- Dynamic Input Node ({node_id}) ---")
            input_label = node.get('data', {}).get('inputLabel', 'Input').replace('"', '\\"')
            test_val = node.get('data', {}).get('testValue', '').replace('"', '\\"').replace('\n', '\\n')
            lines.append(f"{indent}dyn_input_{node_id} = kwargs.get('{node_id}')")
            lines.append(f"{indent}if dyn_input_{node_id} is None:")
            lines.append(f"{indent}    dyn_input_{node_id} = kwargs.get('default_input', \"{test_val}\" if \"{test_val}\" else '<<No input provided>>')")
            if prev_res_var:
                lines.append(f"{indent}last_result = str({prev_res_var}) + \"\\n\" + str(dyn_input_{node_id})")
            else:
                lines.append(f"{indent}last_result = str(dyn_input_{node_id})")
            
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)
                
        elif node['type'] == 'webCrawlerNode':
            lines.append(f"{indent}# --- Web Crawler Node ({node_id}) ---")
            url = node.get('data', {}).get('url', '').replace('"', '\\"')
            lines.append(f"{indent}try:")
            if url:
                lines.append(f"{indent}    target_url_{node_id} = \"{url}\"")
            elif prev_res_var:
                lines.append(f"{indent}    target_url_{node_id} = str({prev_res_var}).strip()")
            else:
                lines.append(f"{indent}    raise ValueError('No URL provided for Web Crawler')")
            lines.append(f"{indent}    resp_{node_id} = requests.get(target_url_{node_id}, timeout=10)")
            lines.append(f"{indent}    soup_{node_id} = BeautifulSoup(resp_{node_id}.text, 'html.parser')")
            lines.append(f"{indent}    crawl_res_{node_id} = soup_{node_id}.get_text(separator=' ', strip=True)[:5000]")
            lines.append(f"{indent}except Exception as e:")
            lines.append(f"{indent}    crawl_res_{node_id} = 'Crawling failed: ' + str(e)")
            if prev_res_var:
                lines.append(f"{indent}last_result = str({prev_res_var}) + \"\\n\\n[Crawled Data]\\n\" + crawl_res_{node_id}")
            else:
                lines.append(f"{indent}last_result = crawl_res_{node_id}")
                
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)
                
        elif node['type'] == 'emailNode':
            lines.append(f"{indent}# --- Email Node ({node_id}) ---")
            to_email = node.get('data', {}).get('toEmail', '').replace('"', '\\"')
            subject = node.get('data', {}).get('subject', 'Auto Flow 알림').replace('"', '\\"')
            
            lines.append(f"{indent}import smtplib")
            lines.append(f"{indent}from email.mime.text import MIMEText")
            lines.append(f"{indent}from email.mime.multipart import MIMEMultipart")
            lines.append(f"{indent}import os")
            lines.append(f"{indent}smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')")
            lines.append(f"{indent}smtp_port = int(os.getenv('SMTP_PORT', '587'))")
            lines.append(f"{indent}smtp_user = os.getenv('SMTP_USER', '')")
            lines.append(f"{indent}smtp_password = os.getenv('SMTP_PASSWORD', '')")
            lines.append(f"{indent}msg = MIMEMultipart()")
            lines.append(f"{indent}msg['From'] = smtp_user")
            lines.append(f"{indent}msg['To'] = '{to_email}'")
            lines.append(f"{indent}msg['Subject'] = '{subject}'")
            lines.append(f"{indent}msg.attach(MIMEText(str({prev_res_var if prev_res_var else 'last_result'}), 'plain', 'utf-8'))")
            
            lines.append(f"{indent}try:")
            lines.append(f"{indent}    if not smtp_user or not smtp_password:")
            lines.append(f"{indent}        raise ValueError('SMTP credentials missing in .env')")
            lines.append(f"{indent}    server = smtplib.SMTP(smtp_server, smtp_port)")
            lines.append(f"{indent}    server.starttls()")
            lines.append(f"{indent}    server.login(smtp_user, smtp_password)")
            lines.append(f"{indent}    server.send_message(msg)")
            lines.append(f"{indent}    server.quit()")
            lines.append(f"{indent}    print(f'\\n[Email Successfully Sent to {to_email}]\\n')")
            lines.append(f"{indent}    res_text_{node_id} = f'Email Successfully Sent to {to_email}'")
            lines.append(f"{indent}except Exception as e:")
            lines.append(f"{indent}    print(f'\\n[Email Sending Failed: {{str(e)}}]\\n')")
            lines.append(f"{indent}    res_text_{node_id} = f'Email Sending Failed: {{str(e)}}'")
            lines.append(f"{indent}last_result = res_text_{node_id}")
            
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)
                
        elif node['type'] == 'kakaoNode':
            lines.append(f"{indent}# --- Kakao Node ({node_id}) ---")
            receiver = node.get('data', {}).get('receiver', '').replace('"', '\\"')
            lines.append(f"{indent}print(f'\\n[Kakao Msg to {receiver}]\\n{{last_result}}\\n')")
            
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)
                
        elif node['type'] == 'httpRequestNode':
            lines.append(f"{indent}# --- HTTP Request Node ({node_id}) ---")
            method = node.get('data', {}).get('method', 'GET')
            url = node.get('data', {}).get('url', '').replace('"', '\\"')
            headers_str = node.get('data', {}).get('headers', '{}')
            body_str = node.get('data', {}).get('body', '{}')
            
            lines.append(f"{indent}import requests")
            lines.append(f"{indent}import json")
            lines.append(f"{indent}try:")
            lines.append(f"{indent}    req_headers_{node_id} = json.loads('''{headers_str}''') if '''{headers_str}'''.strip() else {{}}")
            lines.append(f"{indent}    req_body_{node_id} = json.loads('''{body_str}''') if '''{body_str}'''.strip() else {{}}")
            
            if url:
                lines.append(f"{indent}    target_url_{node_id} = \"{url}\"")
            else:
                lines.append(f"{indent}    target_url_{node_id} = str({prev_res_var if prev_res_var else 'last_result'}).strip()")
                
            lines.append(f"{indent}    if '{method}' == 'GET':")
            lines.append(f"{indent}        resp_{node_id} = requests.get(target_url_{node_id}, headers=req_headers_{node_id}, params=req_body_{node_id}, timeout=15)")
            lines.append(f"{indent}    elif '{method}' == 'POST':")
            lines.append(f"{indent}        resp_{node_id} = requests.post(target_url_{node_id}, headers=req_headers_{node_id}, json=req_body_{node_id}, timeout=15)")
            lines.append(f"{indent}    elif '{method}' == 'PUT':")
            lines.append(f"{indent}        resp_{node_id} = requests.put(target_url_{node_id}, headers=req_headers_{node_id}, json=req_body_{node_id}, timeout=15)")
            lines.append(f"{indent}    elif '{method}' == 'DELETE':")
            lines.append(f"{indent}        resp_{node_id} = requests.delete(target_url_{node_id}, headers=req_headers_{node_id}, json=req_body_{node_id}, timeout=15)")
            
            lines.append(f"{indent}    try:")
            lines.append(f"{indent}        req_out_{node_id} = json.dumps(resp_{node_id}.json(), ensure_ascii=False, indent=2)")
            lines.append(f"{indent}    except json.JSONDecodeError:")
            lines.append(f"{indent}        req_out_{node_id} = resp_{node_id}.text")
            
            lines.append(f"{indent}except Exception as e:")
            lines.append(f"{indent}    req_out_{node_id} = f'HTTP Request Error: {{str(e)}}'")
            
            lines.append(f"{indent}last_result = req_out_{node_id}")
            
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"req_out_{node_id}", visited=visited)
                
        elif node['type'] == 'delayNode':
            lines.append(f"{indent}# --- Delay Node ({node_id}) ---")
            seconds = node.get('data', {}).get('seconds', 5)
            lines.append(f"{indent}import time")
            lines.append(f"{indent}print(f'Waiting for {seconds} seconds...')")
            lines.append(f"{indent}time.sleep(float({seconds}))")
            
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)
                
        elif node['type'] == 'jsonParserNode':
            lines.append(f"{indent}# --- JSON Parser Node ({node_id}) ---")
            mode = node.get('data', {}).get('mode', 'parse')
            extract_key = node.get('data', {}).get('extractKey', '')
            
            lines.append(f"{indent}import json")
            lines.append(f"{indent}try:")
            lines.append(f"{indent}    parser_in = {prev_res_var if prev_res_var else 'last_result'}")
            
            if mode == 'parse':
                lines.append(f"{indent}    parser_out_{node_id} = json.loads(str(parser_in))")
            elif mode == 'stringify':
                lines.append(f"{indent}    parser_out_{node_id} = json.dumps(parser_in, ensure_ascii=False, indent=2)")
            elif mode == 'extract':
                lines.append(f"{indent}    if isinstance(parser_in, str):")
                lines.append(f"{indent}        tmp_dict = json.loads(parser_in)")
                lines.append(f"{indent}    else:")
                lines.append(f"{indent}        tmp_dict = parser_in")
                lines.append(f"{indent}    parser_out_{node_id} = tmp_dict.get('{extract_key}', '')")
            else:
                lines.append(f"{indent}    parser_out_{node_id} = parser_in")
            
            lines.append(f"{indent}except Exception as e:")
            lines.append(f"{indent}    parser_out_{node_id} = f'JSON Parser Error: {{str(e)}}'")
            
            lines.append(f"{indent}last_result = parser_out_{node_id}")
            
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"parser_out_{node_id}", visited=visited)
                
        elif node['type'] == 'mergeNode':
            lines.append(f"{indent}# --- Merge Node ({node_id}) ---")
            strategy = node.get('data', {}).get('mergeStrategy', 'join_newline')
            
            lines.append(f"{indent}merge_in_dict_{node_id} = {{}}")
            # We must collect from incoming edges
            inc_edges = incoming_edges.get(node_id, [])
            for inc in inc_edges:
                src_id = inc['source']
                # Usually we only have prev_res_var of the last visited path, but dynamic collection requires global state tracking if branching. 
                # For simplicity in this linear compiler, we just use kwargs or prev_res_var.
                # Since React Flow runs linearly, merge might not wait for all paths unless we modify the compiler.
                # To mock it simply, we will just use prev_res_var and whatever global tracking we have.
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
            
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"merge_out_{node_id}", visited=visited)
                
        elif node['type'] == 'databaseNode':
            lines.append(f"{indent}# --- Database Node ({node_id}) ---")
            conn_str = node.get('data', {}).get('connectionString', '').replace('"', '\\"')
            query_str = node.get('data', {}).get('query', '').replace('"', '\\"').replace('\n', '\\n')
            
            lines.append(f"{indent}import json")
            lines.append(f"{indent}try:")
            lines.append(f"{indent}    from sqlalchemy import create_engine, text")
            lines.append(f"{indent}    engine_{node_id} = create_engine(\"{conn_str}\")")
            lines.append(f"{indent}    with engine_{node_id}.connect() as conn:")
            lines.append(f"{indent}        result_{node_id} = conn.execute(text(\"{query_str}\"))")
            lines.append(f"{indent}        if result_{node_id}.returns_rows:")
            lines.append(f"{indent}            rows_{node_id} = [dict(row._mapping) for row in result_{node_id}]")
            lines.append(f"{indent}            db_out_{node_id} = json.dumps(rows_{node_id}, ensure_ascii=False, indent=2, default=str)")
            lines.append(f"{indent}        else:")
            lines.append(f"{indent}            conn.commit()")
            lines.append(f"{indent}            db_out_{node_id} = 'Query executed successfully. (No rows returned)'")
            lines.append(f"{indent}except ImportError:")
            lines.append(f"{indent}    db_out_{node_id} = 'Database Error: sqlalchemy library is not installed.'")
            lines.append(f"{indent}except Exception as e:")
            lines.append(f"{indent}    db_out_{node_id} = f'Database Error: {{str(e)}}'")
            
            lines.append(f"{indent}last_result = db_out_{node_id}")
            
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"db_out_{node_id}", visited=visited)
                
        elif node['type'] == 'humanApprovalNode':
            lines.append(f"{indent}# --- Human Approval Node ({node_id}) ---")
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
            
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)
                
        elif node['type'] == 'pythonNode':
            user_code = node.get('data', {}).get('code', '')
            lines.append(f"{indent}# --- Python Node ({node_id}) ---")
            lines.append(f"{indent}input_data = {prev_res_var if prev_res_var else 'last_result'}")
            lines.append(f"{indent}output_data = input_data # Default fallback")
            
            if user_code.strip():
                for line in user_code.split('\n'):
                    lines.append(f"{indent}{line}")
                    
            lines.append(f"{indent}res_text_{node_id} = output_data")
            lines.append(f"{indent}last_result = res_text_{node_id}")
            
            next_edges = forward_edges.get(node_id, [])
            if not next_edges:
                lines.append(f"{indent}return last_result")
            else:
                for target_id, handle in next_edges:
                    generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)
                    
        elif node['type'] == 'outputNode':
            lines.append(f"{indent}# --- Output Node ({node_id}) ---")
            lines.append(f"{indent}return {prev_res_var if prev_res_var else 'last_result'}")
            
        elif node['type'] == 'loopNode':
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
                generate_block(loop_start_edges[0], indent + "    ", active_llm_id=active_llm_id, prev_res_var=acc_var, visited=visited)
                lines.append(f"{indent}    {acc_var} = last_result")
            else:
                loop_body_nodes = [n for n in nodes if n.get('parentNode') == node_id]
                if loop_body_nodes:
                    body_node_ids = {n['id'] for n in loop_body_nodes}
                    
                    has_inner_incoming = set()
                    for e in edges:
                        if e['target'] in body_node_ids and e['source'] in body_node_ids:
                            has_inner_incoming.add(e['target'])
                            
                    body_roots = [n for n in loop_body_nodes if n['id'] not in has_inner_incoming]
                    
                    if body_roots:
                        generate_block(body_roots[0]['id'], indent + "    ", active_llm_id=active_llm_id, prev_res_var=acc_var, visited=visited)
                        lines.append(f"{indent}    {acc_var} = last_result")
                    else:
                        lines.append(f"{indent}    pass")
                else:
                    lines.append(f"{indent}    pass")
                
            done_edges = [t for t, h in forward_edges.get(node_id, []) if h == 'done']
            if done_edges:
                generate_block(done_edges[0], indent, active_llm_id=active_llm_id, prev_res_var=acc_var, visited=visited)
                
        elif node['type'] == 'tokenizerNode':
            method = node.get('data', {}).get('method', 'extract_text')
            lines.append(f"{indent}# --- Tokenizer Node ({node_id}) ---")
            lines.append(f"{indent}file_path = {prev_res_var if prev_res_var else 'last_result'}")
            lines.append(f"{indent}res_text_{node_id} = []")
            
            lines.append(f"{indent}if str(file_path).lower().endswith('.pdf'):")
            lines.append(f"{indent}    import PyPDF2")
            lines.append(f"{indent}    with open(file_path, 'rb') as f:")
            lines.append(f"{indent}        reader = PyPDF2.PdfReader(f)")
            if method == 'chunk_pages':
                lines.append(f"{indent}        res_text_{node_id} = [page.extract_text() for page in reader.pages]")
            else:
                lines.append(f"{indent}        res_text_{node_id} = ['\\n'.join([page.extract_text() for page in reader.pages])]")
                
            lines.append(f"{indent}elif str(file_path).lower().endswith('.xlsx') or str(file_path).lower().endswith('.xls'):")
            lines.append(f"{indent}    import pandas as pd")
            if method == 'chunk_pages':
                lines.append(f"{indent}    df = pd.read_excel(file_path, sheet_name=None)")
                lines.append(f"{indent}    res_text_{node_id} = [f'Sheet: {{sheet}}\\n{{df[sheet].to_string()}}' for sheet in df.keys()]")
            else:
                lines.append(f"{indent}    df = pd.read_excel(file_path)")
                lines.append(f"{indent}    res_text_{node_id} = [df.to_string()]")
                
            lines.append(f"{indent}elif str(file_path).lower().endswith('.pptx'):")
            lines.append(f"{indent}    from pptx import Presentation")
            lines.append(f"{indent}    prs = Presentation(file_path)")
            if method == 'chunk_pages':
                lines.append(f"{indent}    for slide in prs.slides:")
                lines.append(f"{indent}        slide_text = []")
                lines.append(f"{indent}        for shape in slide.shapes:")
                lines.append(f"{indent}            if hasattr(shape, 'text'): slide_text.append(shape.text)")
                lines.append(f"{indent}        res_text_{node_id}.append('\\n'.join(slide_text))")
            else:
                lines.append(f"{indent}    full_text = []")
                lines.append(f"{indent}    for slide in prs.slides:")
                lines.append(f"{indent}        for shape in slide.shapes:")
                lines.append(f"{indent}            if hasattr(shape, 'text'): full_text.append(shape.text)")
                lines.append(f"{indent}    res_text_{node_id} = ['\\n'.join(full_text)]")

            lines.append(f"{indent}elif str(file_path).lower().endswith('.hwp'):")
            lines.append(f"{indent}    try:")
            lines.append(f"{indent}        import olefile")
            lines.append(f"{indent}        import zlib")
            lines.append(f"{indent}        import struct")
            lines.append(f"{indent}        f = olefile.OleFileIO(file_path)")
            lines.append(f"{indent}        dirs = f.listdir()")
            lines.append(f"{indent}        if ['PrvText'] in dirs:")
            lines.append(f"{indent}            text = f.openstream('PrvText').read().decode('utf-16le')")
            lines.append(f"{indent}            res_text_{node_id} = [text]")
            lines.append(f"{indent}        else:")
            lines.append(f"{indent}            body_dirs = [d for d in dirs if d[0] == 'BodyText']")
            lines.append(f"{indent}            text = ''")
            lines.append(f"{indent}            for d in body_dirs:")
            lines.append(f"{indent}                unpacked_data = zlib.decompress(f.openstream(d).read(), -15)")
            lines.append(f"{indent}                i = 0")
            lines.append(f"{indent}                while i < len(unpacked_data):")
            lines.append(f"{indent}                    header = struct.unpack_from('<I', unpacked_data, i)[0]")
            lines.append(f"{indent}                    tag_id = header & 0x3FF")
            lines.append(f"{indent}                    size = (header >> 20) & 0xFFF")
            lines.append(f"{indent}                    if size == 0xFFF:")
            lines.append(f"{indent}                        size = struct.unpack_from('<I', unpacked_data, i + 4)[0]")
            lines.append(f"{indent}                        i += 8")
            lines.append(f"{indent}                    else:")
            lines.append(f"{indent}                        i += 4")
            lines.append(f"{indent}                    if tag_id == 67:")
            lines.append(f"{indent}                        try:")
            lines.append(f"{indent}                            decoded = unpacked_data[i:i+size].decode('utf-16le')")
            lines.append(f"{indent}                            text += ''.join(c for c in decoded if ord(c) >= 32 or c in '\\n\\r\\t') + '\\n'")
            lines.append(f"{indent}                        except: pass")
            lines.append(f"{indent}                    i += size")
            lines.append(f"{indent}            if text.strip():")
            lines.append(f"{indent}                res_text_{node_id} = [text]")
            lines.append(f"{indent}            else:")
            lines.append(f"{indent}                import subprocess")
            lines.append(f"{indent}                res = subprocess.run(['hwp5txt', file_path], capture_output=True, text=True, encoding='utf-8')")
            lines.append(f"{indent}                res_text_{node_id} = [res.stdout] if res.stdout else ['[Error or empty: hwp5txt]']")
            lines.append(f"{indent}    except Exception as e:")
            lines.append(f"{indent}        res_text_{node_id} = [str(e)]")

            lines.append(f"{indent}elif str(file_path).lower().endswith('.hwpx'):")
            lines.append(f"{indent}    import zipfile")
            lines.append(f"{indent}    import xml.etree.ElementTree as ET")
            lines.append(f"{indent}    try:")
            lines.append(f"{indent}        with zipfile.ZipFile(file_path, 'r') as zf:")
            lines.append(f"{indent}            sec_files = [f for f in zf.namelist() if f.startswith('Contents/section') and f.endswith('.xml')]")
            lines.append(f"{indent}            hwpx_text = []")
            lines.append(f"{indent}            for sec in sorted(sec_files):")
            lines.append(f"{indent}                root = ET.fromstring(zf.read(sec))")
            lines.append(f"{indent}                for elem in root.iter():")
            lines.append(f"{indent}                    if elem.tag.endswith('}}t') or elem.tag.endswith(':t'):")
            lines.append(f"{indent}                        if elem.text: hwpx_text.append(elem.text)")
            lines.append(f"{indent}                hwpx_text.append('\\n')")
            lines.append(f"{indent}            res_text_{node_id} = [''.join(hwpx_text)]")
            lines.append(f"{indent}    except Exception as e:")
            lines.append(f"{indent}        res_text_{node_id} = [str(e)]")
                
            lines.append(f"{indent}last_result = res_text_{node_id}")
            
            next_edges = forward_edges.get(node_id, [])
            if not next_edges:
                lines.append(f"{indent}return last_result")
            else:
                for target_id, handle in next_edges:
                    generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)
                    
        elif node['type'] == 'distributorNode':
            lines.append(f"{indent}# --- Distributor Node ({node_id}) ---")
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
                    generate_block(target_id, indent + "    ", active_llm_id=active_llm_id, prev_res_var=f"dist_item_{node_id}", visited=visited)

        elif node['type'] == 'breakNode':
            lines.append(f"{indent}# --- Break Node ({node_id}) ---")
            lines.append(f"{indent}break")
            
        elif node['type'] == 'templateAnalyzerNode':
            lines.append(f"{indent}# --- Template Analyzer Node ({node_id}) ---")
            template_file = node.get('data', {}).get('template_path', '').replace('"', '\\"').replace('\n', '\\n').replace('\\', '/')
            lines.append(f"{indent}try:")
            lines.append(f"{indent}    import re")
            lines.append(f"{indent}    import json")
            lines.append(f"{indent}    import os")
            lines.append(f"{indent}    template_ext = \"{template_file}\".lower()")
            lines.append(f"{indent}    extracted_keys = set()")
            lines.append(f"{indent}    full_text = ''")
            lines.append(f"{indent}    if template_ext.endswith('.hwp') or template_ext.endswith('.hwpx'):")
            lines.append(f"{indent}        import pythoncom")
            lines.append(f"{indent}        pythoncom.CoInitialize()")
            lines.append(f"{indent}        from pyhwpx import Hwp")
            lines.append(f"{indent}        hwp = Hwp(visible=False)")
            lines.append(f"{indent}        try:")
            lines.append(f"{indent}            hwp.open(os.path.abspath(\"{template_file}\"))")
            lines.append(f"{indent}            hwp.InitScan()")
            lines.append(f"{indent}            while True:")
            lines.append(f"{indent}                status, text = hwp.GetText()")
            lines.append(f"{indent}                if status in [0, 1]: break")
            lines.append(f"{indent}                full_text += text")
            lines.append(f"{indent}            hwp.ReleaseScan()")
            lines.append(f"{indent}            field_str = hwp.get_field_list(1, 0)")
            lines.append(f"{indent}            if field_str:")
            lines.append(f"{indent}                for field in field_str.split('\\x02'):")
            lines.append(f"{indent}                    if field.strip(): extracted_keys.add(field.strip())")
            lines.append(f"{indent}        finally:")
            lines.append(f"{indent}            hwp.quit()")
            lines.append(f"{indent}    elif template_ext.endswith('.xlsx') or template_ext.endswith('.xls'):")
            lines.append(f"{indent}        import openpyxl")
            lines.append(f"{indent}        wb = openpyxl.load_workbook(\"{template_file}\")")
            lines.append(f"{indent}        for sheet in wb.worksheets:")
            lines.append(f"{indent}            for row in sheet.iter_rows():")
            lines.append(f"{indent}                for cell in row:")
            lines.append(f"{indent}                    if cell.value and isinstance(cell.value, str):")
            lines.append(f"{indent}                        full_text += cell.value + ' '")
            lines.append(f"{indent}    elif template_ext.endswith('.pptx') or template_ext.endswith('.ppt'):")
            lines.append(f"{indent}        from pptx import Presentation")
            lines.append(f"{indent}        prs = Presentation(\"{template_file}\")")
            lines.append(f"{indent}        for slide in prs.slides:")
            lines.append(f"{indent}            for shape in slide.shapes:")
            lines.append(f"{indent}                if shape.has_text_frame:")
            lines.append(f"{indent}                    for p in shape.text_frame.paragraphs:")
            lines.append(f"{indent}                        for run in p.runs:")
            lines.append(f"{indent}                            if run.text:")
            lines.append(f"{indent}                                full_text += run.text + ' '")
            lines.append(f"{indent}    else:")
            lines.append(f"{indent}        with open(\"{template_file}\", \"r\", encoding=\"utf-8\", errors='ignore') as f:")
            lines.append(f"{indent}            full_text = f.read()")
            lines.append(f"{indent}    ")
            lines.append(indent + "    found_keys = re.findall(r'\\{\\{([^}]+)\\}\\}', full_text)")
            lines.append(f"{indent}    for k in found_keys:")
            lines.append(f"{indent}        extracted_keys.add(k.strip())")
            lines.append(f"{indent}    ")
            lines.append(f"{indent}    schema_dict = {{k: '' for k in extracted_keys}}")
            lines.append(f"{indent}    res_val_{node_id} = json.dumps(schema_dict, ensure_ascii=False, indent=2)")
            lines.append(f"{indent}except Exception as e:")
            lines.append(f"{indent}    res_val_{node_id} = f'Error analyzing template: {{str(e)}}'")
            lines.append(f"{indent}last_result = res_val_{node_id}")
            
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_val_{node_id}", visited=visited)

        elif node['type'] == 'fileModifierNode':
            lines.append(f"{indent}# --- Auto Fill Node ({node_id}) ---")
            template_file = node.get('data', {}).get('template_path', '').replace('"', '\\"').replace('\n', '\\n').replace('\\', '/')
                            
            output_file = node.get('data', {}).get('output_path', '').replace('"', '\\"').replace('\n', '\\n')
            if not output_file:
                if template_file:
                    ext = template_file.split('.')[-1]
                    output_file = f"output.{ext}"
                else:
                    output_file = "output.txt"
            
            if not output_file.startswith('uploads/') and not output_file.startswith('uploads\\\\'):
                import os as _os
                output_file = 'uploads/' + _os.path.basename(output_file)
            lines.append(f"{indent}try:")
            lines.append(f"{indent}    import json")
            lines.append(f"{indent}    import os")
            lines.append(f"{indent}    data_in = {prev_res_var if prev_res_var else 'last_result'}")
            lines.append(f"{indent}    if isinstance(data_in, str):")
            lines.append(f"{indent}        try:")
            lines.append(f"{indent}            data_dict = json.loads(data_in)")
            lines.append(f"{indent}        except: data_dict = {{}}")
            lines.append(f"{indent}    elif isinstance(data_in, dict):")
            lines.append(f"{indent}        data_dict = data_in")
            lines.append(f"{indent}    else:")
            lines.append(f"{indent}        data_dict = {{}}")
            lines.append(f"{indent}    ")
            lines.append(f"{indent}    template_ext = \"{template_file}\".lower()")
            lines.append(f"{indent}    if template_ext.endswith('.hwp') or template_ext.endswith('.hwpx'):")
            lines.append(f"{indent}        import pythoncom")
            lines.append(f"{indent}        pythoncom.CoInitialize()")
            lines.append(f"{indent}        from pyhwpx import Hwp")
            lines.append(f"{indent}        hwp = Hwp(visible=False)")
            lines.append(f"{indent}        try:")
            lines.append(f"{indent}            hwp.open(os.path.abspath(\"{template_file}\"))")
            lines.append(f"{indent}            for k, v in data_dict.items():")
            lines.append(f"{indent}                hwp.put_field_text(str(k), str(v))")
            lines.append(f"{indent}                hwp.find_replace_all('{{{{' + str(k) + '}}}}', str(v))")
            lines.append(f"{indent}            hwp.save_as(os.path.abspath(\"{output_file}\"))")
            lines.append(f"{indent}        finally:")
            lines.append(f"{indent}            hwp.quit()")
            lines.append(f"{indent}    elif template_ext.endswith('.xlsx') or template_ext.endswith('.xls'):")
            lines.append(f"{indent}        import openpyxl")
            lines.append(f"{indent}        wb = openpyxl.load_workbook(\"{template_file}\")")
            lines.append(f"{indent}        for sheet in wb.worksheets:")
            lines.append(f"{indent}            for row in sheet.iter_rows():")
            lines.append(f"{indent}                for cell in row:")
            lines.append(f"{indent}                    if cell.value and isinstance(cell.value, str):")
            lines.append(f"{indent}                        for k, v in data_dict.items():")
            lines.append(f"{indent}                            if '{{{{' + str(k) + '}}}}' in cell.value:")
            lines.append(f"{indent}                                cell.value = cell.value.replace('{{{{' + str(k) + '}}}}', str(v))")
            lines.append(f"{indent}        wb.save(\"{output_file}\")")
            lines.append(f"{indent}    elif template_ext.endswith('.pptx') or template_ext.endswith('.ppt'):")
            lines.append(f"{indent}        from pptx import Presentation")
            lines.append(f"{indent}        prs = Presentation(\"{template_file}\")")
            lines.append(f"{indent}        for slide in prs.slides:")
            lines.append(f"{indent}            for shape in slide.shapes:")
            lines.append(f"{indent}                if shape.has_text_frame:")
            lines.append(f"{indent}                    for p in shape.text_frame.paragraphs:")
            lines.append(f"{indent}                        for run in p.runs:")
            lines.append(f"{indent}                            if run.text:")
            lines.append(f"{indent}                                for k, v in data_dict.items():")
            lines.append(f"{indent}                                    if '{{{{' + str(k) + '}}}}' in run.text:")
            lines.append(f"{indent}                                        run.text = run.text.replace('{{{{' + str(k) + '}}}}', str(v))")
            lines.append(f"{indent}        prs.save(\"{output_file}\")")
            lines.append(f"{indent}    else:")
            lines.append(f"{indent}        with open(\"{output_file}\", \"w\", encoding=\"utf-8\") as _f:")
            lines.append(f"{indent}            _f.write(str({prev_res_var if prev_res_var else 'last_result'}))")
            lines.append(f"{indent}    ")
            lines.append(f"{indent}    res_text_{node_id} = \"{output_file}\"")
            lines.append(f"{indent}except Exception as e:")
            lines.append(f"{indent}    res_text_{node_id} = f\"Error formatting file: {{str(e)}}\"")
            lines.append(f"{indent}last_result = res_text_{node_id}")
            
            next_edges = forward_edges.get(node_id, [])
            if not next_edges:
                lines.append(f"{indent}return last_result")
            else:
                for target_id, handle in next_edges:
                    generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)

    # Start generation for all roots
    lines.append("    __global_results = []")
    for idx, r in enumerate(roots):
        lines.append(f"    def run_root_{idx}():")
        lines.append(f"        last_result = 'No execution occurred.'")
        
        generate_block(r['id'], "        ")
        
        # If the block didn't explicitly return, add a fallback return
        if "return last_result" not in lines[-1]:
             lines.append("        return last_result")
             
        lines.append(f"    try:")
        lines.append(f"        res_{idx} = run_root_{idx}()")
        if len(roots) > 1:
            lines.append(f"        __global_results.append(f'► Flow {idx + 1} Result:\\n{{str(res_{idx})}}')")
        else:
            lines.append(f"        __global_results.append(str(res_{idx}))")
        lines.append(f"    except Exception as e:")
        lines.append(f"        __global_results.append(f'► Flow {idx + 1} Error: {{str(e)}}')")

    if len(roots) > 1:
        lines.append("    return '\\n\\n' + ('='*40) + '\\n\\n'.join(__global_results)")
    else:
        lines.append("    return __global_results[0] if __global_results else 'No result'")

    lines.append("\nif __name__ == '__main__':")
    lines.append("    print(run_workflow())")
    
    return "\n".join(lines)


def run_workflow(nodes: list, edges: list, **kwargs):
    """
    Compiles the graph into Python code and dynamically executes it using exec().
    Returns a tuple (result_text, token_usage_dict).
    """
    python_code = compile_workflow(nodes, edges)
    
    if python_code.startswith("Error"):
        return python_code, {}
        
    # Dynamically execute the generated code
    namespace = {}
    try:
        # We wrap it in a try-except to catch compile/runtime errors safely
        exec(python_code, namespace)
        if 'run_workflow' in namespace:
            result = namespace['run_workflow'](**kwargs)
            tokens = namespace.get('__token_usage__', {})
            return str(result), tokens
        else:
            return "Execution failed: run_workflow function not found.", {}
    except Exception as e:
        return f"Dynamic Execution Error: {str(e)}", {}
