import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Add onNodeDragStop definition
drag_stop_code = """
  const onNodeDragStop = useCallback((event, node) => {
    if (node.type === 'detachedText') {
      const sourceId = node.data.sourceId;
      const key = node.data.fieldKey;
      
      setNodes((nds) => {
        const parentNode = nds.find(n => n.id === sourceId);
        if (!parentNode) return nds;
        
        // Simple bounding box intersection (naive approach: just checking if center of dragged node is inside parent node)
        // Or checking if bounding boxes overlap.
        const px = parentNode.position.x;
        const py = parentNode.position.y;
        const pw = parentNode.measured?.width || parentNode.width || 250;
        const ph = parentNode.measured?.height || parentNode.height || 140;
        
        const cx = node.position.x + (node.measured?.width || 300) / 2;
        const cy = node.position.y + (node.measured?.height || 150) / 2;
        
        if (cx >= px && cx <= px + pw && cy >= py && cy <= py + ph) {
          // Re-attach
          setEdges((eds) => eds.filter(e => e.source !== node.id && e.target !== node.id));
          
          return nds.filter(n => n.id !== node.id).map(n => {
            if (n.id === sourceId) {
              const newData = { ...n.data };
              newData[`isDetached_${key}`] = false;
              // update the value
              newData[key] = node.data.value;
              return { ...n, data: newData };
            }
            return n;
          });
        }
        return nds;
      });
    }
  }, [setNodes, setEdges]);
"""

# Insert before return (
content = re.sub(r'(\s+)(return \(\s*<div className="editor-container">)', r'\1' + drag_stop_code + r'\1\2', content)

# Also ensure it's in the ReactFlow props, we saw it might already be there, but let's check
if 'onNodeDragStop={onNodeDragStop}' not in content:
    content = content.replace('onNodesChange={onNodesChange}', 'onNodesChange={onNodesChange}\n            onNodeDragStop={onNodeDragStop}')

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("onNodeDragStop added")
