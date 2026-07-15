import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

nodes = re.findall(r'export const (\w+) = \(\{.*?\}\) => \{([\s\S]*?)\n\};', content)

for name, body in nodes:
    if 'isExpanded' in body and 'const [isExpanded' not in body:
        print(f"{name} uses isExpanded but it is NOT defined!")
