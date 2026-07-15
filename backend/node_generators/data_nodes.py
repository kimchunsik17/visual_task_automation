import datetime
from node_registry import node_registry

@node_registry.register('jsonParserNode')
def generate_json_parser_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- JSON Parser Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
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
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"parser_out_{node_id}", visited=visited)


@node_registry.register('databaseNode')
def generate_database_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Database Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
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
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"db_out_{node_id}", visited=visited)
