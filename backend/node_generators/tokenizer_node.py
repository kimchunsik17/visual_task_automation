from node_registry import node_registry

@node_registry.register("tokenizerNode")
def generate_tokenizer_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    method = node.get('data', {}).get('method', 'extract_text')
    
    lines.append(f"{indent}# --- Tokenizer Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    
    if prev_res_var:
        # prev_res_var typically holds the file path if the previous node was a valueNode that uploaded a file
        lines.append(f"{indent}file_path_{node_id} = str({prev_res_var}).strip()")
        lines.append(f"{indent}import os")
        lines.append(f"{indent}if os.path.exists(file_path_{node_id}):")
        lines.append(f"{indent}    _, ext = os.path.splitext(file_path_{node_id})")
        lines.append(f"{indent}    ext = ext.lower()")
        lines.append(f"{indent}    if ext == '.pdf':")
        lines.append(f"{indent}        try:")
        lines.append(f"{indent}            import fitz  # PyMuPDF")
        lines.append(f"{indent}            doc_{node_id} = fitz.open(file_path_{node_id})")
        lines.append(f"{indent}            text_{node_id} = ''")
        lines.append(f"{indent}            for page_num in range(len(doc_{node_id})):")
        lines.append(f"{indent}                text_{node_id} += doc_{node_id}.load_page(page_num).get_text()")
        lines.append(f"{indent}            last_result_{node_id} = text_{node_id}")
        lines.append(f"{indent}            log_step('{node_id}', 'tokenizerNode', _start_{node_id}, result=f'Extracted {{len(text_{node_id})}} characters from PDF.')")
        lines.append(f"{indent}        except Exception as e:")
        lines.append(f"{indent}            last_result_{node_id} = f'Error parsing PDF: {{e}}'")
        lines.append(f"{indent}            log_step('{node_id}', 'tokenizerNode', _start_{node_id}, result=last_result_{node_id}, error=True)")
        lines.append(f"{indent}    else:")
        lines.append(f"{indent}        # For now, only PDF is fully supported in this demo. For others, return the path or raw text.")
        lines.append(f"{indent}        try:")
        lines.append(f"{indent}            with open(file_path_{node_id}, 'r', encoding='utf-8') as f:")
        lines.append(f"{indent}                last_result_{node_id} = f.read()")
        lines.append(f"{indent}            log_step('{node_id}', 'tokenizerNode', _start_{node_id}, result=f'Extracted text from text file.')")
        lines.append(f"{indent}        except Exception as e:")
        lines.append(f"{indent}            last_result_{node_id} = f'Unsupported file or encoding error: {{e}}'")
        lines.append(f"{indent}            log_step('{node_id}', 'tokenizerNode', _start_{node_id}, result=last_result_{node_id}, error=True)")
        lines.append(f"{indent}else:")
        lines.append(f"{indent}    # If it's not a valid file path, just pass the previous string down")
        lines.append(f"{indent}    last_result_{node_id} = file_path_{node_id}")
        lines.append(f"{indent}    log_step('{node_id}', 'tokenizerNode', _start_{node_id}, result='Passed through plain text.')")
    else:
        lines.append(f"{indent}last_result_{node_id} = ''")
        lines.append(f"{indent}log_step('{node_id}', 'tokenizerNode', _start_{node_id}, result='Empty input.')")

    lines.append(f"{indent}last_result = last_result_{node_id}")
    
    next_edges = forward_edges.get(node_id, [])
    if not next_edges:
        lines.append(f"{indent}return last_result_{node_id}")
    else:
        for target_id, handle in next_edges:
            generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"last_result_{node_id}", visited=visited)
