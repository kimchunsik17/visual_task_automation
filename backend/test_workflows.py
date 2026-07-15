import json
from graph import run_workflow

# Workflow 1: Linear LLM Workflow
nodes_1 = [
    {'id': 'start', 'type': 'startNode', 'data': {}},
    {'id': 'val', 'type': 'valueNode', 'data': {'value': 'Tell me a short joke.'}},
    {'id': 'llm', 'type': 'llmNode', 'data': {'model': 'gemini-1.5-flash', 'systemPrompt': 'You are a comedian.'}},
    {'id': 'out', 'type': 'outputNode', 'data': {}}
]
edges_1 = [
    {'source': 'start', 'target': 'val', 'sourceHandle': 'out', 'targetHandle': 'in'},
    {'source': 'val', 'target': 'llm', 'sourceHandle': 'out', 'targetHandle': 'in'},
    {'source': 'llm', 'target': 'out', 'sourceHandle': 'out', 'targetHandle': 'in'}
]

# Workflow 2: Conditional Workflow
nodes_2 = [
    {'id': 'start', 'type': 'startNode', 'data': {}},
    {'id': 'val', 'type': 'valueNode', 'data': {'value': 'APPLE'}},
    {'id': 'cond', 'type': 'conditionNode', 'data': {'condition': 'Contains', 'value': 'APP'}},
    {'id': 'out_t', 'type': 'outputNode', 'data': {'label': 'True Branch'}},
    {'id': 'out_f', 'type': 'outputNode', 'data': {'label': 'False Branch'}}
]
edges_2 = [
    {'source': 'start', 'target': 'val', 'sourceHandle': 'out', 'targetHandle': 'in'},
    {'source': 'val', 'target': 'cond', 'sourceHandle': 'out', 'targetHandle': 'in'},
    {'source': 'cond', 'target': 'out_t', 'sourceHandle': 'true', 'targetHandle': 'in'},
    {'source': 'cond', 'target': 'out_f', 'sourceHandle': 'false', 'targetHandle': 'in'}
]

# Workflow 3: HTTP Request Workflow
nodes_3 = [
    {'id': 'start', 'type': 'startNode', 'data': {}},
    {'id': 'http', 'type': 'httpRequestNode', 'data': {'method': 'GET', 'url': 'https://jsonplaceholder.typicode.com/todos/1'}},
    {'id': 'out', 'type': 'outputNode', 'data': {}}
]
edges_3 = [
    {'source': 'start', 'target': 'http', 'sourceHandle': 'out', 'targetHandle': 'in'},
    {'source': 'http', 'target': 'out', 'sourceHandle': 'out', 'targetHandle': 'in'}
]

import traceback
print('=== Running Workflow 1 ===')
try:
    result_1, tokens_1, logs_1 = run_workflow(nodes_1, edges_1)
    print("Result:", result_1)
    for log in logs_1: print(f"Node {log['node_id']} ({log['status']}): {log.get('result', '')}")
except Exception as e:
    traceback.print_exc()

print('\n=== Running Workflow 2 ===')
try:
    result_2, tokens_2, logs_2 = run_workflow(nodes_2, edges_2)
    print("Result:", result_2)
    for log in logs_2: print(f"Node {log['node_id']} ({log['status']}): {log.get('result', '')}")
except Exception as e:
    traceback.print_exc()

print('\n=== Running Workflow 3 ===')
try:
    result_3, tokens_3, logs_3 = run_workflow(nodes_3, edges_3)
    print("Result:", result_3)
    for log in logs_3: print(f"Node {log['node_id']} ({log['status']}): {log.get('result', '')}")
except Exception as e:
    traceback.print_exc()
