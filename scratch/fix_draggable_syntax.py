import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the missing parenthesis
# Search for {typeof value === 'object' ? JSON.stringify(value) : (value || "더블클릭하여 수정하세요... (드래그하여 밖으로 분리)"}
content = content.replace('{typeof value === \'object\' ? JSON.stringify(value) : (value || "더블클릭하여 수정하세요... (드래그하여 밖으로 분리)"}', '{typeof value === \'object\' ? JSON.stringify(value) : (value || "더블클릭하여 수정하세요... (드래그하여 밖으로 분리)")}')

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("DraggableTextarea parenthesis fixed")
