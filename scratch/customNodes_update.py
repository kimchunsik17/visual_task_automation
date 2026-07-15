import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add DetachedTextNode
detached_node_code = """
export const DetachedTextNode = ({ id, data }) => {
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
          value={data.value || ''}
          onChange={(e) => data.onChange(data.sourceId, data.fieldKey, e.target.value)}
          placeholder="텍스트를 입력하세요..."
          style={{ minHeight: '150px' }}
        />
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  );
};
"""

if 'DetachedTextNode' not in content:
    content = content + "\n" + detached_node_code

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("DetachedTextNode added")
