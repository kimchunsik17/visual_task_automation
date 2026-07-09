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
    for e in edges:
        source = e['source']
        if source not in forward_edges:
            forward_edges[source] = []
        forward_edges[source].append((e['target'], e.get('sourceHandle')))
        
    has_incoming = set(e['target'] for e in edges)
    roots = [n for n in nodes if n['id'] not in has_incoming and not n.get('parentNode')]
    
    if not roots:
        # Fallback to any node without a parentNode
        roots = [n for n in nodes if not n.get('parentNode')]
    if not roots:
        return "Error: No valid starting node found."
        
    # If there are multiple roots, prioritize the ones that are actually connected to something
    if len(roots) > 1:
        connected_roots = [r for r in roots if r['id'] in forward_edges]
        if connected_roots:
            roots = connected_roots
            
    root_node = roots[0]
    
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
    if needs_gemini or not used_models:
        lines.append("from langchain_google_genai import ChatGoogleGenerativeAI")
    if needs_openai:
        lines.append("from langchain_openai import ChatOpenAI")
    if needs_anthropic:
        lines.append("from langchain_anthropic import ChatAnthropic")
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
            
        if node['type'] == 'valueNode':
            file_path = node.get('data', {}).get('file_path', '')
            val = node.get('data', {}).get('value', '').replace('"', '\\"').replace('\n', '\\n')
            lines.append(f"{indent}# --- Value Node ({node_id}) ---")
            
            if file_path:
                lines.append(f"{indent}val_{node_id} = r\"{file_path}\"")
            else:
                lines.append(f"{indent}val_{node_id} = \"{val}\"")
                
            lines.append(f"{indent}last_result = val_{node_id}")
            
            next_edges = forward_edges.get(node_id, [])
            if not next_edges:
                lines.append(f"{indent}return last_result")
            else:
                for target_id, handle in next_edges:
                    generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"val_{node_id}", visited=visited)
                    
        elif node['type'] == 'llmNode':
            model = node.get('data', {}).get('model', 'gemini-3.5-flash')
            sys_prompt = node.get('data', {}).get('systemPrompt', 'You are a helpful assistant.').replace('"', '\\"').replace('\n', '\\n')
            lines.append(f"{indent}# --- LLM Node ({node_id}) ---")
            
            if model == "gpt-4o" or model == "gpt-4o-mini":
                lines.append(f"{indent}llm_{node_id} = ChatOpenAI(model=\"{model}\")")
            elif model == "claude-3-5-sonnet":
                lines.append(f"{indent}llm_{node_id} = ChatAnthropic(model_name=\"claude-3-5-sonnet-20240620\")")
            else:
                lines.append(f"{indent}llm_{node_id} = ChatGoogleGenerativeAI(model=\"{model}\")")
                
            lines.append(f"{indent}sys_prompt_{node_id} = \"{sys_prompt}\"")
            
            next_edges = forward_edges.get(node_id, [])
            if not next_edges:
                lines.append(f"{indent}return last_result")
            else:
                for target_id, handle in next_edges:
                    generate_block(target_id, indent, active_llm_id=node_id, prev_res_var=prev_res_var, visited=visited)
                
        elif node['type'] == 'promptNode':
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
                
            lines.append(f"{indent}prompt_{node_id} = ChatPromptTemplate.from_messages([('system', {sys_var}), ('user', \"{{user_input}}\")])")
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
