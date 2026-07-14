import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

import datetime
load_dotenv()

def is_numeric(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

__token_usage__ = {'nodes': {}, 'total_input': 0, 'total_output': 0, 'total_tokens': 0}
__execution_logs__ = []
def log_step(node_id, node_type, start_time, result=None, error=None):
    end_time = datetime.datetime.utcnow().isoformat()
    res_str = str(result) if result is not None else None
    if res_str and len(res_str) > 10000:
        res_str = res_str[:10000] + '...(truncated)'
    __execution_logs__.append({
        'node_id': node_id,
        'node_type': node_type,
        'start_time': start_time,
        'end_time': end_time,
        'status': 'error' if error else 'success',
        'result_data': res_str,
        'error_message': str(error) if error else None
    })
def run_workflow(**kwargs):
    global __token_usage__
    global __execution_logs__
    __token_usage__ = {'nodes': {}, 'total_input': 0, 'total_output': 0, 'total_tokens': 0}
    __execution_logs__ = []
    last_result = 'No execution occurred.'
    # --- LLM Node (node_2) ---
    llm_node_2 = ChatGoogleGenerativeAI(model="gemini-3.5-flash")
    sys_prompt_node_2 = "You are a helpful assistant."
    __global_results = []
    def run_root_0():
        last_result = 'No execution occurred.'
        # --- Start Node (node_start) ---
        _start_node_start = datetime.datetime.utcnow().isoformat()
        log_step('node_start', 'startNode', _start_node_start, result='Started')
        # --- Value Node (node_1) ---
        _start_node_1 = datetime.datetime.utcnow().isoformat()
        val_node_1 = "Hello, how are you?"
        last_result = val_node_1
        log_step('node_1', 'valueNode', _start_node_1, result=last_result)
        # --- LLM Node (node_2) ---
        _start_node_2 = datetime.datetime.utcnow().isoformat()
        full_prompt_node_2 = str(val_node_1) + "\n\n"
        sys_msg_sa_node_2 = SystemMessage(content=sys_prompt_node_2)
        prompt_sa_node_2 = ChatPromptTemplate.from_messages([sys_msg_sa_node_2, ('user', "{user_input}")])
        chain_sa_node_2 = prompt_sa_node_2 | llm_node_2
        res_obj_sa_node_2 = chain_sa_node_2.invoke({"user_input": full_prompt_node_2})
        res_text_node_2 = str(res_obj_sa_node_2.content)
        usage_dict_sa = getattr(res_obj_sa_node_2, 'usage_metadata', None)
        if not usage_dict_sa and hasattr(res_obj_sa_node_2, 'response_metadata'):
            rm_sa = res_obj_sa_node_2.response_metadata
            if 'token_usage' in rm_sa: usage_dict_sa = rm_sa['token_usage']
        if usage_dict_sa:
            __token_usage__['nodes']['node_2'] = usage_dict_sa
            __token_usage__['total_input'] += usage_dict_sa.get('input_tokens', usage_dict_sa.get('prompt_tokens', 0))
            __token_usage__['total_output'] += usage_dict_sa.get('output_tokens', usage_dict_sa.get('completion_tokens', 0))
            __token_usage__['total_tokens'] += usage_dict_sa.get('total_tokens', 0)
        last_result = res_text_node_2
        # --- Output Node (node_3) ---
        _start_node_3 = datetime.datetime.utcnow().isoformat()
        return res_text_node_2
        return last_result
    try:
        res_0 = run_root_0()
        __global_results.append(str(res_0))
    except Exception as e:
        __global_results.append(f'► Flow 1 Error: {str(e)}')
    return __global_results[0] if __global_results else 'No result'

if __name__ == '__main__':
    print(run_workflow())