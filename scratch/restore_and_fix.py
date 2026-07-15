import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix nodeInternals
content = re.sub(
    r'useStore\(\(s\)\s*=>\s*{\s*const\s+node\s*=\s*s\.nodeInternals\.get\(',
    r'useStore((s) => {\n      const map = s.nodeLookup || s.nodeInternals;\n      if (!map) return 0;\n      const node = map.get(',
    content
)

# 2. Fix JSON stringify in DraggableTextarea
content = content.replace(
    'value={value || \'\'}',
    'value={typeof value === \'object\' ? JSON.stringify(value, null, 2) : (value || \'\')}'
)
content = content.replace(
    '{value || "더블클릭하여 수정하세요... (드래그하여 밖으로 분리)"}',
    '{typeof value === \'object\' ? JSON.stringify(value) : (value || "더블클릭하여 수정하세요... (드래그하여 밖으로 분리)")}'
)

# 3. Fix Handle type in DraggableTextarea
# We need to change type="target" to type="source" in DraggableTextarea's handle.
content = content.replace(
    '<Handle \n          className="popout-handle"\n          type="target"',
    '<Handle \n          className="popout-handle"\n          type="source"'
)

# 4. Fix DetachedTextNode
# It has `<Handle type="source" position={isOnLeft ? Position.Right : Position.Left} id="out"`
# Needs to be `<Handle type="target" position={isOnLeft ? Position.Right : Position.Left} id={`in-${data.fieldKey}`}`
content = re.sub(
    r'<Handle\s+type="source"\s+position=\{isOnLeft \? Position\.Right : Position\.Left\}\s+id="out"\s+style=\{\{([^}]+)\}\}\s*/>',
    r'<Handle type="target" position={isOnLeft ? Position.Right : Position.Left} id={`in-${data.fieldKey}`} style={{\1}} />',
    content
)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Restored and fixed!")
