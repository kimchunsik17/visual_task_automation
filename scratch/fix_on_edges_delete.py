import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    'const detachedNode = updatedNodes.find(n => n.id === edge.source && n.type === \'detachedText\');',
    'const detachedNode = updatedNodes.find(n => (n.id === edge.source || n.id === edge.target) && n.type === \'detachedText\');'
)

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed onEdgesDelete!")
