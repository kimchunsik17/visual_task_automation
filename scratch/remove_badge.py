import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace:
#       ) : (
#         <div className="node-collapsed-badge">{data.label || 'Collapsed'}</div>
#       )}
# With:
#       )}

content = re.sub(r'\)\s*:\s*\(\s*<div className="node-collapsed-badge">[^<]+</div>\s*\)', ')', content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Badge removed")
