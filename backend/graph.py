import os
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
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


def run_workflow(nodes: list, edges: list) -> str:
    """
    Compiles the graph into Python code and dynamically executes it using exec().
    """
    python_code = compile_workflow(nodes, edges)
    
    if python_code.startswith("Error"):
        return python_code
        
    # Dynamically execute the generated code
    namespace = {}
    try:
        # We wrap it in a try-except to catch compile/runtime errors safely
        exec(python_code, namespace)
        if 'run_workflow' in namespace:
            result = namespace['run_workflow']()
            return str(result)
        else:
            return "Execution failed: run_workflow function not found."
    except Exception as e:
        return f"Dynamic Execution Error: {str(e)}"
