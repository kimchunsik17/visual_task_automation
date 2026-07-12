import re
with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("<div style={ display: 'flex', alignItems: 'center', gap: '6px' }>", "<div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>")

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed JSX syntax error.")
