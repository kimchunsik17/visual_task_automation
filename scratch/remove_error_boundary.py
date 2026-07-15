import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("import { ErrorBoundary } from '../ErrorBoundary';", "")
content = content.replace("<ErrorBoundary><ReactFlowProvider>", "<ReactFlowProvider>")
content = content.replace("<ErrorBoundary>\n    <ReactFlowProvider>", "<ReactFlowProvider>")
content = content.replace("</ReactFlowProvider>\n    </ErrorBoundary>", "</ReactFlowProvider>")
content = content.replace("</ReactFlowProvider></ErrorBoundary>", "</ReactFlowProvider>")
content = content.replace("<ErrorBoundary>\n      <ReactFlowProvider>", "<ReactFlowProvider>")
content = content.replace("</ErrorBoundary>", "")
content = content.replace("<ErrorBoundary><ReactFlow", "<ReactFlow")

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("ErrorBoundary removed")
