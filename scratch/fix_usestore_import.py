import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Add useStore to the @xyflow/react import if missing
if 'useStore' not in content.split("from '@xyflow/react'")[0] and "import " in content:
    content = content.replace("import { Handle, Position, useUpdateNodeInternals, NodeResizer } from '@xyflow/react';", "import { Handle, Position, useUpdateNodeInternals, NodeResizer, useStore } from '@xyflow/react';")

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
