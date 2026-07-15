import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace `if (isDetached) { return null; }` with a Handle component.
# Wait, DraggableTextarea needs to import Position, Handle if it doesn't already have it in scope.
# But DraggableTextarea is in customNodes.jsx where Handle and Position are already imported from 'reactflow'.

new_detached_logic = """
  if (isDetached) {
    return (
      <div style={{ position: 'relative', height: '0px', width: '100%' }}>
        <Handle 
          className="popout-handle"
          type="target" 
          position={Position.Right} 
          id={`popout-${fieldKey}`} 
          style={{ right: '-20px', top: '10px', background: '#ec4899', width: '10px', height: '10px', border: '2px solid white' }} 
        />
      </div>
    );
  }
"""

content = re.sub(r'if \(isDetached\) \{\s*return null;\s*\}', new_detached_logic, content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("DraggableTextarea updated with popout handle")
