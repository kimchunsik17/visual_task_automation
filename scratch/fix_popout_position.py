import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Make sure useStore is imported from reactflow
if 'useStore' not in content:
    content = content.replace("import { Handle, Position } from 'reactflow';", "import { Handle, Position, useStore } from 'reactflow';")
    content = content.replace('import { Handle, Position } from "reactflow";', 'import { Handle, Position, useStore } from "reactflow";')

# Now update DraggableTextarea to use useStore for dynamic position
draggable_regex = re.compile(r'export const DraggableTextarea = \(\{ id, fieldKey, value, onChange, placeholder, isDetached \}\) => \{([\s\S]*?)return \([\s\S]*?className="popout-handle"[\s\S]*?/>[\s\S]*?\);\s*\}')

def replace_draggable(match):
    inner = match.group(1)
    # the entire DraggableTextarea
    new_comp = """export const DraggableTextarea = ({ id, fieldKey, value, onChange, placeholder, isDetached }) => {
  const [isEditing, setIsEditing] = useState(false);
  
  const detachedNodeId = `popout_${id}_${fieldKey}`;
  const detachedNodeX = useStore((s) => {
    const node = s.nodeInternals.get(detachedNodeId);
    return node ? (node.positionAbsolute?.x ?? node.position?.x ?? 0) : 0;
  });
  const parentNodeX = useStore((s) => {
    const node = s.nodeInternals.get(id);
    return node ? (node.positionAbsolute?.x ?? node.position?.x ?? 0) : 0;
  });
  
  const isOnLeft = isDetached && detachedNodeX < parentNodeX;

  const handleDragStart = (e) => {
    e.stopPropagation();
    e.dataTransfer.setData('application/reactflow-popout', JSON.stringify({ sourceId: id, key: fieldKey }));
    e.dataTransfer.effectAllowed = 'move';
  };

  if (isDetached) {
    return (
      <div style={{ position: 'relative', height: '0px', width: '100%' }}>
        <Handle 
          className="popout-handle"
          type="target" 
          position={isOnLeft ? Position.Left : Position.Right} 
          id={`popout-${fieldKey}`} 
          style={isOnLeft 
            ? { left: '-20px', top: '10px', background: '#ec4899', width: '10px', height: '10px', border: '2px solid white' }
            : { right: '-20px', top: '10px', background: '#ec4899', width: '10px', height: '10px', border: '2px solid white' }
          } 
        />
      </div>
    );
  }

  return isEditing ? (
    <textarea 
      className="nodrag"
      value={value || ''}
      onChange={(e) => onChange(id, fieldKey, e.target.value)}
      onBlur={() => setIsEditing(false)}
      autoFocus
      placeholder={placeholder || "텍스트를 입력하세요..."}
      style={{ minHeight: '80px', width: '100%' }}
    />
  ) : (
    <div 
      className="nodrag"
      onDoubleClick={() => setIsEditing(true)}
      draggable
      onDragStart={handleDragStart}
      style={{
        minHeight: '80px',
        width: '100%',
        padding: '0.5rem',
        border: '1px dashed var(--border-color)',
        borderRadius: '4px',
        backgroundColor: 'var(--btn-active-bg)',
        color: value ? 'var(--text-color)' : 'var(--text-muted)',
        cursor: 'grab',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
        fontSize: '0.85rem'
      }}
    >
      {value || "더블클릭하여 수정하세요... (드래그하여 밖으로 분리)"}
    </div>
  );
}"""
    return new_comp

content = re.sub(r'export const DraggableTextarea = \(\{ id, fieldKey, value, onChange, placeholder, isDetached \}\) => \{[\s\S]*?return isEditing \? \([\s\S]*?\);\s*\}', replace_draggable, content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("DraggableTextarea position updated")
