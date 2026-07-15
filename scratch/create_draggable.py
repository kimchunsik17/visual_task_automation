with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

draggable_comp = """
export const DraggableTextarea = ({ id, fieldKey, value, onChange, placeholder, isDetached }) => {
  const [isEditing, setIsEditing] = useState(false);
  
  const onDragStart = (event) => {
    event.dataTransfer.setData('application/reactflow-popout', JSON.stringify({ type: 'popout', sourceId: id, key: fieldKey }));
    event.dataTransfer.effectAllowed = 'move';
  };

  if (isDetached) {
    return (
      <div style={{ padding: '1rem', fontStyle: 'italic', color: '#888', textAlign: 'center', background: 'var(--bg-color)', borderRadius: '4px' }}>
        텍스트가 분리되었습니다.
      </div>
    );
  }

  return isEditing ? (
    <textarea 
      className="nodrag"
      autoFocus
      onBlur={() => setIsEditing(false)}
      value={value || ''}
      onChange={(e) => onChange(id, fieldKey, e.target.value)}
      placeholder={placeholder || "입력하세요..."}
      onInput={(e) => { e.target.style.height = "auto"; e.target.style.height = e.target.scrollHeight + "px"; }}
      style={{ minHeight: '120px', resize: 'none', width: '100%', padding: '8px', fontSize: '13px', lineHeight: '1.5', boxSizing: 'border-box' }}
    />
  ) : (
    <div
      className="nodrag"
      draggable
      onDragStart={onDragStart}
      onDoubleClick={() => setIsEditing(true)}
      style={{
        minHeight: '120px',
        border: '1px solid var(--border-color)',
        borderRadius: '4px',
        padding: '8px',
        backgroundColor: 'var(--bg-color)',
        cursor: 'grab',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        fontSize: '13px',
        lineHeight: '1.5',
        overflow: 'hidden',
        color: value ? 'var(--text-color)' : 'var(--text-muted)'
      }}
    >
      {value || '더블클릭하여 수정하세요... (드래그하여 밖으로 분리)'}
    </div>
  );
};
"""

if 'export const DraggableTextarea' not in content:
    # Insert after imports
    content = content.replace("export const StartNode", draggable_comp + "\nexport const StartNode")

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("DraggableTextarea component added")
