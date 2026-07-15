import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

edges_delete_code = """
  const onEdgesDelete = useCallback((edgesToDelete) => {
    setNodes((nds) => {
      let updatedNodes = [...nds];
      let nodesToDelete = new Set();
      
      edgesToDelete.forEach(edge => {
        const detachedNode = updatedNodes.find(n => n.id === edge.source && n.type === 'detachedText');
        if (detachedNode) {
          nodesToDelete.add(detachedNode.id);
          
          updatedNodes = updatedNodes.map(n => {
            if (n.id === detachedNode.data.sourceId) {
              const newData = { ...n.data };
              newData[`isDetached_${detachedNode.data.fieldKey}`] = false;
              return { ...n, data: newData };
            }
            return n;
          });
        }
      });
      
      return updatedNodes.filter(n => !nodesToDelete.has(n.id));
    });
  }, [setNodes]);
"""

# Insert before `const onConnect`
content = content.replace("const onConnect = useCallback", edges_delete_code + "\n  const onConnect = useCallback")

# Add onEdgesDelete to ReactFlow props
content = content.replace("onEdgesChange={onEdgesChange}", "onEdgesChange={onEdgesChange}\n              onEdgesDelete={onEdgesDelete}")

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
