import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

detached_node_regex = re.compile(r'export const DetachedTextNode = \(\{ id, data \}\) => \{[\s\S]*?return \([\s\S]*?\}\);?\s*\n\};')

new_detached_node = """export const DetachedTextNode = ({ id, data }) => {
  const [localValue, setLocalValue] = useState(data.value || '');
  
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
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};"""

content = detached_node_regex.sub(new_detached_node, content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("DetachedTextNode fixed")
