import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the duplicated onNodeDragStop at the bottom
# It starts with "const onNodeDragStop = useCallback((event, node) => {\n    if (node.type === 'detachedText') {"
bad_drag_stop = re.compile(r'const onNodeDragStop = useCallback\(\(event, node\) => \{\s*if \(node\.type === \'detachedText\'\) \{[\s\S]*?\}, \[setNodes, setEdges\]\);')
content = bad_drag_stop.sub('', content)

# Inject the logic into the first onNodeDragStop
good_drag_stop_regex = re.compile(r'(const onNodeDragStop = useCallback\(\(event, node\) => \{\s*)(if \(node\.type === \'loopNode\'\) return;)')

detached_logic = """
    if (node.type === 'detachedText') {
      const intersections = getIntersectingNodes(node);
      const parentNode = intersections.find(n => n.id === node.data.sourceId);
      
      if (parentNode) {
        setEdges((eds) => eds.filter(e => e.source !== node.id && e.target !== node.id));
        setNodes((nds) => nds.filter(n => n.id !== node.id).map(n => {
          if (n.id === parentNode.id) {
            const newData = { ...n.data };
            newData[`isDetached_${node.data.fieldKey}`] = false;
            newData[node.data.fieldKey] = node.data.value;
            return { ...n, data: newData };
          }
          return n;
        }));
      }
      return;
    }
"""

content = good_drag_stop_regex.sub(r'\1' + detached_logic + r'\n    \2', content)

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Drag stop fixed")
