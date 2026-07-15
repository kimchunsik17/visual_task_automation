import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# We need to use useStore in DetachedTextNode to find the parent node and compute isOnLeft
detached_node_regex = re.compile(r'export const DetachedTextNode = \(\{ id, data \}\) => \{([\s\S]*?)return \([\s\S]*?<Handle type="source" position=\{Position.Right\} id="out" />[\s\S]*?\);\s*\}')

def replace_detached(match):
    return """export const DetachedTextNode = ({ id, data }) => {
  const [localValue, setLocalValue] = useState(data.value || '');
  
  const parentNodeX = useStore((s) => {
    const node = s.nodeInternals.get(data.sourceId);
    return node ? (node.positionAbsolute?.x ?? node.position?.x ?? 0) : 0;
  });
  
  const myNodeX = useStore((s) => {
    const node = s.nodeInternals.get(id);
    return node ? (node.positionAbsolute?.x ?? node.position?.x ?? 0) : 0;
  });
  
  // If myNodeX is less than parentNodeX, I am on the left. So my handle should be on my RIGHT.
  // If I am on the right, my handle should be on my LEFT.
  const isOnLeft = myNodeX < parentNodeX;
  
  const handleChange = (e) => {
    const val = e.target.value;
    setLocalValue(val);
    data.onChange(data.sourceId, data.fieldKey, val);
  };

  return (
    <div className={`custom-node expanded detached-text-node`} style={{ minWidth: '300px' }}>
      <div className="node-header" style={{ padding: '0.5rem 1rem', background: 'var(--btn-active-bg)', cursor: 'grab' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem' }}>
          <span>{data.label || 'Detached Text'}</span>
        </div>
      </div>
      <div className="node-body">
        <textarea
          className="nodrag"
          value={localValue}
          onChange={handleChange}
          placeholder="텍스트를 입력하세요..."
          style={{ minHeight: '150px' }}
        />
      </div>
      <Handle 
        type="source" 
        position={isOnLeft ? Position.Right : Position.Left} 
        id="out" 
        style={{
          transition: 'left 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          left: isOnLeft ? '100%' : '0%',
        }}
      />
    </div>
  );
}"""

content = detached_node_regex.sub(replace_detached, content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("DetachedTextNode updated")
