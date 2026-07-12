import re
with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "import { Handle, Position, useUpdateNodeInternals, NodeResizer } from '@xyflow/react';",
    "import { Handle, Position, useUpdateNodeInternals, NodeResizer } from '@xyflow/react';\nimport { Play, MessageSquare, BrainCircuit, Box, Terminal, Shuffle, LogOut, SplitSquareHorizontal, FileCode, Variable, Network, Repeat } from 'lucide-react';"
)

replacements = [
    ('startNode', 'start', '<Play size={16} color="#10b981"/>', 'Start', '10b981'),
    ('promptNode', 'prompt', '<MessageSquare size={16} color="#3b82f6"/>', 'Prompt Node', '3b82f6'),
    ('llmNode', 'llm', '<BrainCircuit size={16} color="#8b5cf6"/>', 'LLM Node', '8b5cf6'),
    ('valueNode', 'value', '<Variable size={16} color="#ec4899"/>', 'Value Node', 'ec4899'),
    ('pythonNode', 'python', '<Terminal size={16} color="#eab308"/>', 'Python Node', 'eab308'),
    ('conditionNode', 'condition', '<SplitSquareHorizontal size={16} color="#0ea5e9"/>', 'Condition Node', '0ea5e9'),
    ('outputNode', 'output', '<LogOut size={16} color="#f97316"/>', 'Output Node', 'f97316'),
    ('tokenizerNode', 'tokenizer', '<Box size={16} color="#14b8a6"/>', 'Tokenizer', '14b8a6'),
    ('distributorNode', 'distributor', '<Network size={16} color="#6366f1"/>', 'Distributor', '6366f1'),
    ('fileModifierNode', 'file-modifier', '<FileCode size={16} color="#f43f5e"/>', 'Auto Fill Node', 'f43f5e'),
    ('templateAnalyzerNode', 'template-analyzer', '<FileCode size={16} color="#8b5cf6"/>', 'Template Analyzer', '8b5cf6'),
    ('loopNode', 'loop', '<Repeat size={16} color="#ca8a04"/>', 'Loop Node', 'ca8a04'),
    ('breakNode', 'break', "<LogOut size={16} color=\"#dc2626\" style={{transform: 'rotate(180deg)'}}/>", 'Break Node', 'dc2626'),
]

# For startNode specifically
content = re.sub(
    r'<div className="node-header" style={{ background: \'linear-gradient.*?\' }}>\s*🏁 Start\s*<button',
    '<div className="node-header">\n        <div style={{ display: \'flex\', alignItems: \'center\', gap: \'6px\' }}><Play size={16} color="#10b981"/> Start</div>\n        <button',
    content, flags=re.DOTALL
)
content = re.sub(
    r'<div className="custom-node start" style={{ borderColor: \'#22c55e\', minWidth: \'150px\' }}>',
    '<div className="custom-node start" style={{ minWidth: \'150px\' }}>',
    content
)

for node_type, cls, icon, label, color in replacements[1:]:
    # Find the header and replace
    pattern = r'<div className="node-header">\s*' + label + r'\s*<button'
    replacement = f'<div className="node-header">\n        <div style={{ display: \'flex\', alignItems: \'center\', gap: \'6px\' }}>{icon} {label}</div>\n        <button'
    content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Refactoring customNodes.jsx complete.")
