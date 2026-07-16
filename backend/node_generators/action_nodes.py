import datetime
import json
from node_registry import node_registry
from meta_agent import PLACEHOLDER_URL


def _emit_needs_input(node_id, node_type, indent, lines, forward_edges, generate_block_fn, active_llm_id, visited, out_var):
    """url이 아직 PLACEHOLDER_URL(실제 값 미입력)인 경우 공통으로 쓰는 블록.
    진짜 요청을 시도하지 않고, 사용자에게 채팅창을 참고하라는 안내로 대체한 뒤 다음 노드로 넘어간다."""
    lines.append(f"{indent}{out_var} = '⚠️ 채워넣어야 하는 필드가 있습니다. AI와 대화하는 창을 참고해주세요. (노드: {node_id})'")
    lines.append(f"{indent}last_result = {out_var}")
    lines.append(f"{indent}log_step('{node_id}', '{node_type}', _start_{node_id}, result=last_result, error='URL이 아직 채워지지 않음(PLACEHOLDER_URL)')")
    for target_id, handle in forward_edges.get(node_id, []):
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=out_var, visited=visited)


@node_registry.register('httpRequestNode')
def generate_http_request_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- HTTP Request Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    method = node.get('data', {}).get('method', 'GET')
    url = node.get('data', {}).get('url', '').replace('"', '\\"')
    headers_str = node.get('data', {}).get('headers', '{}')
    body_str = node.get('data', {}).get('body', '{}')

    if url == PLACEHOLDER_URL:
        _emit_needs_input(node_id, node['type'], indent, lines, forward_edges, generate_block_fn, active_llm_id, visited, f"req_out_{node_id}")
        return

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
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"req_out_{node_id}", visited=visited)


@node_registry.register('webCrawlerNode')
def generate_web_crawler_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Web Crawler Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    url = node.get('data', {}).get('url', '').replace('"', '\\"')

    if url == PLACEHOLDER_URL:
        _emit_needs_input(node_id, node['type'], indent, lines, forward_edges, generate_block_fn, active_llm_id, visited, f"crawl_res_{node_id}")
        return

    lines.append(f"{indent}try:")
    if url:
        lines.append(f"{indent}    target_url_{node_id} = \"{url}\"")
    elif prev_res_var:
        lines.append(f"{indent}    target_url_{node_id} = str({prev_res_var}).strip()")
    else:
        lines.append(f"{indent}    raise ValueError('No URL provided for Web Crawler')")
    lines.append(f"{indent}    import requests")
    lines.append(f"{indent}    from bs4 import BeautifulSoup")
    lines.append(f"{indent}    resp_{node_id} = requests.get(target_url_{node_id}, timeout=10)")
    lines.append(f"{indent}    soup_{node_id} = BeautifulSoup(resp_{node_id}.text, 'html.parser')")
    lines.append(f"{indent}    crawl_res_{node_id} = soup_{node_id}.get_text(separator=' ', strip=True)[:5000]")
    lines.append(f"{indent}except Exception as e:")
    lines.append(f"{indent}    crawl_res_{node_id} = 'Crawling failed: ' + str(e)")
    if prev_res_var:
        lines.append(f"{indent}last_result = str({prev_res_var}) + \"\\n\\n[Crawled Data]\\n\" + crawl_res_{node_id}")
    else:
        lines.append(f"{indent}last_result = crawl_res_{node_id}")
        
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)


@node_registry.register('pythonNode')
def generate_python_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    user_code = node.get('data', {}).get('code', '')
    lines.append(f"{indent}# --- Python Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}input_data = {prev_res_var if prev_res_var else 'last_result'}")
    lines.append(f"{indent}output_data = input_data # Default fallback")
    
    if user_code.strip():
        for line in user_code.split('\n'):
            lines.append(f"{indent}{line}")
            
    lines.append(f"{indent}res_text_{node_id} = output_data")
    lines.append(f"{indent}last_result = res_text_{node_id}")
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    if not next_edges:
        lines.append(f"{indent}return last_result")
    else:
        for target_id, handle in next_edges:
            generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register('delayNode')
def generate_delay_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Delay Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    seconds = node.get('data', {}).get('seconds', 5)
    lines.append(f"{indent}import time")
    lines.append(f"{indent}print(f'Waiting for {seconds} seconds...')")
    lines.append(f"{indent}time.sleep(float({seconds}))")
    
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)


@node_registry.register('dynamicInputNode')
@node_registry.register('webhookNode')
def generate_dynamic_input_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Dynamic Input Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    input_label = node.get('data', {}).get('inputLabel', 'Input').replace('"', '\\"')
    input_type = node.get('data', {}).get('inputType', 'text')
    test_val = node.get('data', {}).get('testValue', '').replace('"', '\\"').replace('\n', '\\n')
    
    lines.append(f"{indent}dyn_input_{node_id} = kwargs.get('{node_id}')")
    lines.append(f"{indent}if dyn_input_{node_id} is None:")
    lines.append(f"{indent}    dyn_input_{node_id} = kwargs.get('default_input', \"{test_val}\" if \"{test_val}\" else '<<No input provided>>')")
    
    if input_type == 'file':
        lines.append(f"{indent}import os")
        lines.append(f"{indent}file_content_{node_id} = ''")
        lines.append(f"{indent}try:")
        lines.append(f"{indent}    if os.path.exists(str(dyn_input_{node_id})):")
        lines.append(f"{indent}        with open(str(dyn_input_{node_id}), 'r', encoding='utf-8', errors='replace') as f:")
        lines.append(f"{indent}            file_content_{node_id} = f.read()")
        lines.append(f"{indent}        dyn_input_{node_id} = file_content_{node_id}")
        lines.append(f"{indent}except Exception as e:")
        lines.append(f"{indent}    dyn_input_{node_id} = f'Error reading file: {{str(e)}}'")
        
    if prev_res_var:
        lines.append(f"{indent}last_result = f\"{{{prev_res_var}}}\\n\\n[{input_label}]:\\n{{dyn_input_{node_id}}}\"")
    else:
        lines.append(f"{indent}last_result = f\"[{input_label}]:\\n{{dyn_input_{node_id}}}\"")
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)
