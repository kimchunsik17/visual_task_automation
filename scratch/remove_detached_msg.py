import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

msg_regex = re.compile(r'if \(isDetached\) \{\s*return \(\s*<div.*?텍스트가 분리되었습니다.*?</div>\s*\);\s*\}', re.DOTALL)
content = msg_regex.sub('if (isDetached) { return null; }', content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
