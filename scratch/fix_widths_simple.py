import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# We only want to replace `width: 'xxx'` or `minWidth: 'xxx'` that are inside `style={{ ... }}`.
# Since we know `customNodes.jsx` format, we can safely find and replace.

def replace_width(match):
    prefix = match.group(1) # width or minWidth
    value = match.group(2) # the px value
    return f"{prefix}: isExpanded ? '{value}' : undefined"

# Split by export const DetachedTextNode to avoid touching it
parts = content.split("export const DetachedTextNode =")
main_part = parts[0]
detached_part = "export const DetachedTextNode =" + parts[1] if len(parts) > 1 else ""

main_part = re.sub(r"(width):\s*['\"]([^'\"]+px)['\"]", replace_width, main_part)
main_part = re.sub(r"(minWidth):\s*['\"]([^'\"]+px)['\"]", replace_width, main_part)

# StartNode and OutputNode fix
main_part = re.sub(r"className=\{`custom-node \$\{isExpanded \? 'expanded' : 'collapsed'\} start \$\{isAIModified \? 'ai-highlight' : ''\}`\} onClick=\{handleNodeClick\} style=\{\{.*?\}\}", r"className={`custom-node collapsed start ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}", main_part)

main_part = re.sub(r"className=\{`custom-node \$\{isExpanded \? 'expanded' : 'collapsed'\} output \$\{isAIModified \? 'ai-highlight' : ''\}`\} onClick=\{handleNodeClick\} style=\{\{.*?\}\}", r"className={`custom-node collapsed output ${isAIModified ? 'ai-highlight' : ''}`} onClick={handleNodeClick}", main_part)

# Remove the headers and handles inside StartNode/OutputNode that rely on isExpanded
# We can just replace the whole components since they are small
start_node_new = """export const StartNode = ({ id, data }) => {
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

output_node_new = """export const OutputNode = ({ id, data }) => {
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

main_part = re.sub(r'export const StartNode = \(\{ id, data \}\) => \{[\s\S]*?return \([\s\S]*?\}\);?\s*\n\};', start_node_new, main_part)
main_part = re.sub(r'export const OutputNode = \(\{ id, data \}\) => \{[\s\S]*?return \([\s\S]*?\}\);?\s*\n\};', output_node_new, main_part)


with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(main_part + detached_part)

print("Widths and nodes fixed")
