import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

if 'ErrorBoundary' not in content:
    content = content.replace("import React, { useState, useCallback, useRef, useEffect } from 'react';", "import React, { useState, useCallback, useRef, useEffect } from 'react';\nimport { ErrorBoundary } from '../ErrorBoundary';")
    
    # Wrap ReactFlow in ErrorBoundary
    content = content.replace("<ReactFlow", "<ErrorBoundary><ReactFlow")
    content = content.replace("</ReactFlow>", "</ReactFlow></ErrorBoundary>")

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("ErrorBoundary injected")
