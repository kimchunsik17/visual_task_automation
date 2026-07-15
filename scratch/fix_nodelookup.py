import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace nodeInternals with nodeLookup
content = content.replace('nodeInternals.get', 'nodeLookup.get')

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("nodeInternals replaced with nodeLookup")
