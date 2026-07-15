import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# I need to properly wrap EditorPage default export or just fix the tags.
# Let's fix the specific error:
content = content.replace("<ErrorBoundary><ReactFlowProvider>", "<ErrorBoundary>\n    <ReactFlowProvider>")
content = content.replace("</ReactFlowProvider>", "</ReactFlowProvider>\n    </ErrorBoundary>")

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Syntax error fixed")
