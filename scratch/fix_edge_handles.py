import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

edge_creation = """        setEdges((eds) => eds.concat({
          id: `e_${newNodeId}-${popoutData.sourceId}`,
          source: newNodeId,
          target: popoutData.sourceId,
          sourceHandle: 'out',
          targetHandle: `popout-${popoutData.key}`,
          animated: true,
          style: { stroke: '#ec4899', strokeWidth: 2 }
        }));"""

# we need to replace the old edge creation
# Look for: setEdges((eds) => eds.concat({ id: `e_${newNodeId}-${popoutData.sourceId}`, source: newNodeId, target: popoutData.sourceId, animated: true, style: { stroke: '#ec4899', strokeWidth: 2 } }));
old_edge_pattern = re.compile(r'setEdges\(\(eds\) => eds\.concat\(\{\s*id: `e_\$\{newNodeId\}-\$\{popoutData\.sourceId\}`,\s*source: newNodeId,\s*target: popoutData\.sourceId,\s*animated: true,\s*style: \{ stroke: \'#ec4899\', strokeWidth: 2 \}\s*\}\)\);')

content = old_edge_pattern.sub(edge_creation, content)

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Edge creation updated")
