import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace newData[node.data.fieldKey] = node.data.value; with just removing it.
content = content.replace("newData[node.data.fieldKey] = node.data.value;", "")

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
