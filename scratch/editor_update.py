import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Add DetachedTextNode to imports from customNodes
content = re.sub(r'import \{(.*?)\} from \'\.\./customNodes\';', r'import {\1, DetachedTextNode} from \'../customNodes\';', content)

# Register detachedText in nodeTypes
if 'detachedText:' not in content:
    content = re.sub(r'const nodeTypes = \{', r'const nodeTypes = {\n  detachedText: DetachedTextNode,', content)

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
