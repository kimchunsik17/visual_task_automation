import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

nodes_delete_code = """
  const onNodesDelete = useCallback((nodesToDelete) => {
    setNodes((nds) => {
      let updatedNodes = [...nds];
      
      nodesToDelete.forEach(node => {
        if (node.type === 'detachedText') {
          updatedNodes = updatedNodes.map(n => {
            if (n.id === node.data.sourceId) {
              const newData = { ...n.data };
              newData[`isDetached_${node.data.fieldKey}`] = false;
              return { ...n, data: newData };
            }
            return n;
          });
        }
      });
      
      return updatedNodes;
    });
  }, [setNodes]);
"""

# Insert before `const onEdgesDelete`
content = content.replace("const onEdgesDelete = useCallback", nodes_delete_code + "\n  const onEdgesDelete = useCallback")

# Add onNodesDelete to ReactFlow props
content = content.replace("onEdgesDelete={onEdgesDelete}", "onEdgesDelete={onEdgesDelete}\n              onNodesDelete={onNodesDelete}")

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
