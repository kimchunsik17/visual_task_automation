import re, os

# Read Sidebar.jsx
sidebar_path = '../frontend/src/Sidebar.jsx'
with open(sidebar_path, 'r', encoding='utf-8') as f:
    sidebar_content = f.read()
    
# Extract node types from Sidebar.jsx
frontend_nodes = set(re.findall(r'type:\s*[\x27\x22]([^\x27\x22]+)[\x27\x22]', sidebar_content))

# Read graph.py
graph_path = 'graph.py'
with open(graph_path, 'r', encoding='utf-8') as f:
    graph_content = f.read()

# Extract node types from graph.py
backend_nodes = set()
matches1 = re.findall(r'node\[\x27type\x27\]\s*==\s*[\x27\x22]([^\x27\x22]+)[\x27\x22]', graph_content)
matches2 = re.findall(r'node\[\x27type\x27\]\s*in\s*\(([^)]+)\)', graph_content)

for m in matches1:
    backend_nodes.add(m)
for m in matches2:
    for t in m.split(','):
        backend_nodes.add(t.strip().strip('\x27\x22'))

print('Frontend nodes missing in Backend:', frontend_nodes - backend_nodes)
print('Backend nodes missing in Frontend:', backend_nodes - frontend_nodes)
