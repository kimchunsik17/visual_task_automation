import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Split by "export const "
nodes = content.split("export const ")

for node in nodes[1:]: # skip the first empty or import part
    name = node.split("=")[0].strip()
    if 'isExpanded' in node and 'const [isExpanded' not in node:
        print(f"{name} uses isExpanded but it is NOT defined!")
