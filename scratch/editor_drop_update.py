import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

popout_handling = """
      const popoutDataStr = event.dataTransfer.getData('application/reactflow-popout');
      if (popoutDataStr) {
        const popoutData = JSON.parse(popoutDataStr);
        const position = screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        });
        
        const newNodeId = `popout_${popoutData.sourceId}_${popoutData.key}`;
        
        // Find source node to get initial text
        setNodes((nds) => {
          const sourceNode = nds.find(n => n.id === popoutData.sourceId);
          if (!sourceNode) return nds;
          
          const initialValue = sourceNode.data[popoutData.key];
          
          // Add new node
          const newNode = {
            id: newNodeId,
            type: 'detachedText',
            position,
            data: { 
              label: '분리된 텍스트', 
              onChange: onNodeDataChange, 
              sourceId: popoutData.sourceId,
              fieldKey: popoutData.key,
              value: initialValue
            },
          };
          
          // Mark source as detached
          const updatedNodes = nds.map(n => {
             if (n.id === popoutData.sourceId) {
                return { ...n, data: { ...n.data, [`isDetached_${popoutData.key}`]: true } };
             }
             return n;
          });
          
          return updatedNodes.concat(newNode);
        });
        
        // Add edge
        setEdges((eds) => eds.concat({
          id: `e_${newNodeId}-${popoutData.sourceId}`,
          source: newNodeId,
          target: popoutData.sourceId,
          animated: true,
          style: { stroke: '#ec4899', strokeWidth: 2 }
        }));
        
        return;
      }
"""

content = content.replace("const type = event.dataTransfer.getData('application/reactflow');", popout_handling + "\n      const type = event.dataTransfer.getData('application/reactflow');")

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Drop logic updated")
