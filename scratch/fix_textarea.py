with open('frontend/src/index.css', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace min-height: 40px; with min-height: 120px !important;
import re
text = re.sub(r'min-height: 40px;', r'min-height: 120px;', text)

# Also let's ensure .node-body textarea has resize: vertical
text = text.replace('resize: vertical;', 'resize: vertical;\n  font-size: 13px;\n  line-height: 1.5;')

with open('frontend/src/index.css', 'w', encoding='utf-8') as f:
    f.write(text)

print("Textarea fixed")
