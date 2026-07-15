import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace nodeLookup.get with robust checking
content = content.replace(
    'const node = s.nodeLookup.get(', 
    'const map = s.nodeLookup || s.nodeInternals;\n    if (!map) return 0;\n    const node = map.get('
)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Robust node map lookup applied")
