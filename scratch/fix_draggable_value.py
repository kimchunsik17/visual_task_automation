import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Make value a string safely
def safe_value(match):
    return match.group(0).replace('value={value || \'\'}', 'value={typeof value === \'object\' ? JSON.stringify(value, null, 2) : (value || \'\')}').replace('{value ||', '{typeof value === \'object\' ? JSON.stringify(value) : (value ||')

content = re.sub(r'export const DraggableTextarea[\s\S]*?(?=export const StartNode)', safe_value, content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("DraggableTextarea value fixed")
