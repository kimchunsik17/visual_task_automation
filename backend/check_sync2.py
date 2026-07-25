import re, os

# Read customNodes.jsx
sidebar_path = '../frontend/src/customNodes.jsx'
with open(sidebar_path, 'r', encoding='utf-8') as f:
    sidebar_content = f.read()
    
frontend_nodes = set(re.findall(r'const\s+([A-Za-z0-9_]+Node)\s*=', sidebar_content))

# Read graph.py
graph_path = 'graph.py'
with open(graph_path, 'r', encoding='utf-8') as f:
    graph_content = f.read()

backend_nodes = set()
matches1 = re.findall(r'node\[\x27type\x27\]\s*==\s*[\x27\x22]([^\x27\x22]+)[\x27\x22]', graph_content)
matches2 = re.findall(r'node\[\x27type\x27\]\s*in\s*\(([^)]+)\)', graph_content)

for m in matches1:
    backend_nodes.add(m)
for m in matches2:
    for t in m.split(','):
        backend_nodes.add(t.strip().strip('\x27\x22'))

# Some nodes might be named differently in React components (e.g. StartNode -> startNode). We lowercase first char to compare.
frontend_nodes_lower = {n[0].lower() + n[1:] for n in frontend_nodes}

print('Frontend nodes missing in Backend:', frontend_nodes_lower - backend_nodes)
