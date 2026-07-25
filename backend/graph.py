import models
import json
import os
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

from node_registry import node_registry
import node_generators

load_dotenv()

def add_tracking(res_var, track_id, indent_str):
    return f"""{indent_str}usage_dict = getattr({res_var}, 'usage_metadata', None)
{indent_str}if not usage_dict and hasattr({res_var}, 'response_metadata'):
{indent_str}    rm = {res_var}.response_metadata
{indent_str}    if 'token_usage' in rm: usage_dict = rm['token_usage']
{indent_str}if usage_dict:
{indent_str}    if '{track_id}' not in __token_usage__['nodes']:
{indent_str}        __token_usage__['nodes']['{track_id}'] = {{'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}}
{indent_str}    i_tok = usage_dict.get('input_tokens', usage_dict.get('prompt_tokens', 0))
{indent_str}    o_tok = usage_dict.get('output_tokens', usage_dict.get('completion_tokens', 0))
{indent_str}    t_tok = usage_dict.get('total_tokens', 0)
{indent_str}    __token_usage__['nodes']['{track_id}']['input_tokens'] += i_tok
{indent_str}    __token_usage__['nodes']['{track_id}']['output_tokens'] += o_tok
{indent_str}    __token_usage__['nodes']['{track_id}']['total_tokens'] += t_tok
{indent_str}    __token_usage__['total_input'] += i_tok
{indent_str}    __token_usage__['total_output'] += o_tok
{indent_str}    __token_usage__['total_tokens'] += t_tok"""

def compile_workflow(nodes: list, edges: list, project_id=None) -> str:
    """
    Parses the graph data (순방향 탐색) and generates imperative Python LangChain code.
    """
    if not nodes:
        return "Error: Graph is empty. Please drag and drop nodes from the sidebar."

    node_dict = {n['id']: n for n in nodes}
    
    tool_node_ids = set()
    for e in edges:
        if e.get('targetHandle') == 'tools':
            tool_node_ids.add(e['source'])

    
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
        if target_handle not in ('template', 'tools'):
            control_flow_edges.append(e)
            if source not in forward_edges:
                forward_edges[source] = []
            forward_edges[source].append((target, e.get('sourceHandle')))
        
    has_incoming = set(e['target'] for e in control_flow_edges)
    
    # 1. Prioritize explicit Start Nodes
    roots = [n for n in nodes if n['type'] in ('startNode', 'scheduleNode', 'webhookNode', 'discordTriggerNode', 'telegramTriggerNode') and n['id'] not in tool_node_ids]
    
    # 2. Fallback to old heuristic if no start nodes are found
    if not roots:
        roots = [n for n in nodes if n['id'] not in has_incoming and not n.get('parentNode') and n['type'] != 'llmNode' and n['id'] not in tool_node_ids]
        
        if not roots:
            # Final fallback: probably a cycle with no start node. Pick the first top-level node.
            top_level = [n for n in nodes if not n.get('parentNode')]
            roots = [top_level[0]] if top_level else []
            
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
            used_models.add(node.get('data', {}).get('model', 'gemini-1.5-flash'))
    
    needs_gemini = any('gemini' in m for m in used_models)
    needs_openai = any('gpt' in m for m in used_models)
    needs_anthropic = any('claude' in m for m in used_models)

    lines = []
    lines.append("import os")
    lines.append("has_langfuse = bool(os.getenv('LANGFUSE_PUBLIC_KEY')) and bool(os.getenv('LANGFUSE_SECRET_KEY'))")
    lines.append("if has_langfuse:")
    lines.append("    from langfuse.langchain import CallbackHandler")
    if project_id:
        lines.append("    langfuse_handler = CallbackHandler()")
    else:
        lines.append("    langfuse_handler = CallbackHandler()")
    lines.append("else:")
    lines.append("    langfuse_handler = None")
    lines.append("from langchain_google_genai import ChatGoogleGenerativeAI")
    if needs_openai:
        lines.append("from langchain_openai import ChatOpenAI")
    if needs_anthropic:
        lines.append("from langchain_anthropic import ChatAnthropic")
    lines.append("from langchain_core.prompts import ChatPromptTemplate")
    lines.append("from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, messages_from_dict, messages_to_dict")
    lines.append("import requests")
    lines.append("from bs4 import BeautifulSoup")
    lines.append("from dotenv import load_dotenv\n")
    lines.append("import datetime")
    lines.append("load_dotenv()\n")
    lines.append("def is_numeric(s):")
    lines.append("    try:")
    lines.append("        float(s)")
    lines.append("        return True")
    lines.append("    except ValueError:")
    lines.append("        return False")
    lines.append("__token_usage__ = {'nodes': {}, 'total_input': 0, 'total_output': 0, 'total_tokens': 0}")
    lines.append("__execution_logs__ = []")
    # mergeNode가 실제로 "여러 갈래의 결과를 합치는" 게 아니라 그중 마지막으로 도달한 값 하나만
    # last_result로 갖고 있다가 그대로 통과시키는 버그가 있었다(merge_in_dict를 만들어놓고 정작
    # 안 쓰고 그냥 prev_res_var 하나만 merge_vals에 넣었음 — 실제로 자연어 포스터 프로젝트에서
    # mergeNode 이전 갈래(구조화된 정보)가 통째로 사라지는 문제로 나타남). 이제 각 노드가
    # log_step을 호출할 때마다 자기 결과를 node_id로 저장해두고, mergeNode가 자신에게 들어오는
    # 모든 incoming edge의 source node_id로 이 딕셔너리를 찾아서 실제로 합친다.
    lines.append("__node_results__ = {}")
    lines.append("def _extract_text(obj):")
    lines.append("    if hasattr(obj, 'content'):")
    lines.append("        c = obj.content")
    lines.append("        if isinstance(c, list):")
    lines.append("            return '\\n'.join([str(x.get('text', x)) if isinstance(x, dict) else str(x) for x in c])")
    lines.append("        return str(c)")
    lines.append("    elif isinstance(obj, dict) and 'content' in obj:")
    lines.append("        return str(obj['content'])")
    lines.append("    return str(obj)")
    # useStructuredOutput 없이 "반드시 JSON만 출력해라"라고 프롬프트로만 지시한 llmNode는,
    # 지시를 어기고 답을 ```json ... ``` 코드펜스로 감싸는 경우가 실제로 흔하다. json.loads가
    # 그 펜스 때문에 바로 실패해서 fileModifierNode/jsonParserNode 등이 조용히 빈 값으로
    # fallback되는 버그가 실제로 있었다(자기소개서 hwpx가 빈칸 하나도 안 채워진 채 저장됨).
    # json.loads를 쓰는 모든 노드가 펜스를 먼저 벗겨내고 파싱하도록 공용 헬퍼로 뺀다.
    lines.append("def _strip_json_fence(s):")
    lines.append("    s = str(s).strip()")
    lines.append("    if s.startswith('```'):")
    lines.append("        s = s[3:]")
    lines.append("        if s[:4].lower().startswith('json'):")
    lines.append("            s = s[4:]")
    lines.append("        if '```' in s:")
    lines.append("            s = s[:s.rfind('```')]")
    lines.append("    return s.strip()")
    # fileModifierNode가 .hwpx/.docx 안의 {{key}} 자리표시자를 채우는 것과 똑같은 규칙을, JSON
    # 문자열 안에서도 쓸 수 있게 공용으로 뺐다 — notionNode의 properties처럼 "직전 노드가 만든
    # 구조화된 값을 참조하는 JSON 템플릿"을 LLM이 자연스럽게 {{key}} 문법으로 짜는 경우가 실제로
    # 있었다(문서화된 관례가 아니었는데도 fileModifierNode에서 배운 패턴을 그대로 재사용함). 이걸
    # 그냥 리터럴 문자열로 두면 실제 값 대신 "{{key}}"라는 텍스트가 그대로 나가버린다.
    lines.append("def _fill_template_placeholders(template_str, values):")
    lines.append("    import json")
    lines.append("    if not isinstance(values, dict):")
    lines.append("        return template_str")
    lines.append("    for k, v in values.items():")
    lines.append("        placeholder = '{{' + str(k) + '}}'")
    lines.append("        if placeholder in template_str:")
    lines.append("            replacement = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)")
    lines.append("            # 문자열 값은 JSON 문자열 리터럴 안(따옴표 사이)에 들어가는 경우가 대부분이라")
    lines.append("            # 그 안의 따옴표/줄바꿈만 이스케이프한다(값 자체가 이미 JSON인 dict/list면 그대로).")
    lines.append("            if not isinstance(v, (dict, list)):")
    lines.append("                replacement = replacement.replace('\\\\', '\\\\\\\\').replace('\"', '\\\\\"').replace('\\n', '\\\\n')")
    lines.append("            template_str = template_str.replace(placeholder, replacement)")
    lines.append("    return template_str")
    lines.append("def log_step(node_id, node_type, start_time, result=None, error=None):")
    lines.append("    end_time = datetime.datetime.utcnow().isoformat()")
    lines.append("    res_str = str(result) if result is not None else None")
    lines.append("    if res_str and len(res_str) > 10000:")
    lines.append("        res_str = res_str[:10000] + '...(truncated)'")
    lines.append("    __execution_logs__.append({")
    lines.append("        'node_id': node_id,")
    lines.append("        'node_type': node_type,")
    lines.append("        'start_time': start_time,")
    lines.append("        'end_time': end_time,")
    lines.append("        'status': 'error' if error else 'success',")
    lines.append("        'result_data': res_str,")
    lines.append("        'error_message': str(error) if error else None")
    lines.append("    })")
    lines.append("    __node_results__[node_id] = result")
    lines.append("def run_workflow(**kwargs):")
    lines.append("    global __token_usage__")
    lines.append("    global __execution_logs__")
    lines.append("    global __node_results__")
    lines.append("    __token_usage__ = {'nodes': {}, 'total_input': 0, 'total_output': 0, 'total_tokens': 0}")
    lines.append("    __execution_logs__ = []")
    lines.append("    __node_results__ = {}")
    lines.append("    last_result = 'No execution occurred.'")
    
    # Generate all LLM configurations at the top of the workflow
    for node in nodes:
        if node['type'] == 'llmNode':
            node_id = node['id']
            model = node.get('data', {}).get('model', 'gemini-1.5-flash')
            api_key = node.get('data', {}).get('apiKey', '')
            
            sys_prompt = node.get('data', {}).get('systemPrompt', 'You are a helpful assistant.').replace('"', '\\"').replace('\n', '\\n')
            lines.append(f"    # --- LLM Node ({node_id}) ---")
            
            if model == "gpt-4o" or model == "gpt-4o-mini":
                api_key_arg = f', api_key="{api_key}"' if api_key else ''
                lines.append(f"    llm_{node_id} = ChatOpenAI(model=\"{model}\", max_retries=0{api_key_arg})")
            elif "claude" in model:
                api_key_arg = f', api_key="{api_key}"' if api_key else ''
                lines.append(f"    llm_{node_id} = ChatAnthropic(model_name=\"{model}\", max_retries=0{api_key_arg})")
            else:
                api_key_arg = f', google_api_key="{api_key}"' if api_key else ''
                lines.append(f"    llm_{node_id} = ChatGoogleGenerativeAI(model=\"{model}\", max_retries=0{api_key_arg})")
                
            lines.append(f"    if langfuse_handler:")
            if project_id:
                lines.append(f"        llm_{node_id} = llm_{node_id}.with_config(callbacks=[langfuse_handler], metadata={{'langfuse_session_id': 'project-{project_id}'}}, tags=['workflow_execution'])")
            else:
                lines.append(f"        llm_{node_id} = llm_{node_id}.with_config(callbacks=[langfuse_handler], tags=['workflow_execution'])")
            lines.append(f"    sys_prompt_{node_id} = \"{sys_prompt}\"")
    
    def generate_block(node_id, indent, active_llm_id=None, prev_res_var=None, visited=None):
        if visited is None:
            visited = set()
        
        # Prevent cyclic recursion
        if node_id in visited:
            return
        
        # Tool nodes are generated inside MultiAgentNode
        if node_id in tool_node_ids and node.get('type') != 'multiAgentNode':
            pass # wait, if it's explicitly called, we should generate it.
            # We should only skip if it's called from regular control flow.
            # But the roots logic already excludes them? Let's exclude from roots instead.

        
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
        else:
            lines.append(f"{indent}# --- Unsupported Node ({node_id}) ---")
            lines.append(f"{indent}print('Unsupported node type: {node['type']}')")
            lines.append(f"{indent}last_result = 'Unsupported node type: {node['type']}'")
            next_edges = forward_edges.get(node_id, [])
            for target_id, handle in next_edges:
                generate_block(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result', visited=visited)

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

    lines.append("    if langfuse_handler and hasattr(langfuse_handler, '_langfuse_client'):")
    lines.append("        langfuse_handler._langfuse_client.flush()")
    if len(roots) > 1:
        lines.append("    return '\\n\\n' + ('='*40) + '\\n\\n'.join(__global_results)")
    else:
        lines.append("    return __global_results[0] if __global_results else 'No result'")

    lines.append("\nif __name__ == '__main__':")
    lines.append("    print(run_workflow())")
    
    return "\n".join(lines)


def run_workflow(nodes: list, edges: list, db=None, session_id=None, project_id=None, **kwargs):
    """
    Compiles the graph into Python code and dynamically executes it using exec().
    Returns a tuple (result_text, token_usage_dict, execution_logs).
    """
    import models
    # kakaoNode.data.accessToken은 실제 메시지 전송용 access_token(provider="kakao_token")이어야
    # 하는데, "kakao"(REST API 키/client_id — 토큰 자동 갱신에만 쓰이고 발송 인증엔 절대 못 쓴다)로
    # 잘못 채워지는 경우가 있다(과거 노드 컴포넌트 자체가 그렇게 하드코딩돼 있었고, AI 생성 그래프도
    # 가끔 이 실수를 반복한다). 어디서 왔든 실행 시점에 여기서 한 번 더 교정해서, 프롬프트/UI가
    # 매번 완벽하길 바라는 대신 실행 계층에서 스스로 막는다.
    for n in nodes:
        if isinstance(n, dict) and n.get('type') == 'kakaoNode':
            if (n.get('data') or {}).get('accessToken') == '{{API_CENTER:kakao}}':
                n['data']['accessToken'] = '{{API_CENTER:kakao_token}}'

    if db and project_id:
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if project and project.user_id:
            api_keys = db.query(models.UserApiKey).filter(models.UserApiKey.user_id == project.user_id).all()
            api_key_map = {f"{{{{API_CENTER:{k.provider}}}}}": k.api_key for k in api_keys}

            # 카카오 access_token(provider=kakao_token)은 6시간마다 만료된다 — 그냥 저장된 값을
            # 쓰지 않고, 만료가 임박했으면 refresh_token으로 자동 갱신한 최신 값을 대신 넣는다.
            if any(k.provider == "kakao_token" for k in api_keys):
                from kakao_utils import ensure_kakao_token_fresh
                fresh_token = ensure_kakao_token_fresh(project.user_id, db)
                if fresh_token:
                    api_key_map["{{API_CENTER:kakao_token}}"] = fresh_token

            def replace_api_keys(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, str) and v in api_key_map:
                            obj[k] = api_key_map[v]
                        elif isinstance(v, (dict, list)):
                            replace_api_keys(v)
                elif isinstance(obj, list):
                    for i in range(len(obj)):
                        if isinstance(obj[i], str) and obj[i] in api_key_map:
                            obj[i] = api_key_map[obj[i]]
                        elif isinstance(obj[i], (dict, list)):
                            replace_api_keys(obj[i])
            replace_api_keys(nodes)

    python_code = compile_workflow(nodes, edges, project_id=project_id)
    
    if python_code.startswith("Error"):
        return python_code, {}, []
        
    # Dynamically execute the generated code
    namespace = {'db': db, 'models': models, 'json': json}
    try:
        # We wrap it in a try-except to catch compile/runtime errors safely
        exec(python_code, namespace)
        if 'run_workflow' in namespace:
            result = namespace['run_workflow'](**kwargs)
            tokens = namespace.get('__token_usage__', {})
            logs = namespace.get('__execution_logs__', [])
            return str(result), tokens, logs
        else:
            return "Execution failed: run_workflow function not found.", {}, []
    except Exception as e:
        return f"Dynamic Execution Error: {str(e)}", {}, []
