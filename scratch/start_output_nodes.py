import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# StartNode
start_node_regex = re.compile(r'export const StartNode = \(\{ id, data \}\) => \{[\s\S]*?return \([\s\S]*?\}\);?\s*\n\};')
new_start_node = """export const StartNode = ({ id, data }) => {
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node collapsed start ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <div className="node-header" style={{ cursor: 'default' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Play size={16} color="#10b981"/> 시작점</div>
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};"""

# OutputNode
output_node_regex = re.compile(r'export const OutputNode = \(\{ id, data \}\) => \{[\s\S]*?return \([\s\S]*?\}\);?\s*\n\};')
new_output_node = """export const OutputNode = ({ id, data }) => {
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };

  return (
    <div className={`custom-node collapsed output ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="node-header" style={{ cursor: 'default' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><ArrowRightToLine size={16} color="#f97316"/> 최종 출력</div>
      </div>
    </div>
  );
};"""

content = start_node_regex.sub(new_start_node, content)
content = output_node_regex.sub(new_output_node, content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("StartNode and OutputNode minimized")
