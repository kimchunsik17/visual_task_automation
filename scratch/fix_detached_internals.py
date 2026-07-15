import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix DraggableTextarea
draggable_pattern = r"(export const DraggableTextarea = \(\{ id, fieldKey, value, onChange, placeholder, isDetached \}\) => \{\n  const \[isEditing, setIsEditing\] = useState\(false\);)"
draggable_replacement = r"\1\n  const updateNodeInternals = useUpdateNodeInternals();"
content = re.sub(draggable_pattern, draggable_replacement, content, count=1)

draggable_effect_pattern = r"(const isOnLeft = isDetached && detachedNodeX < parentNodeX;)"
draggable_effect_replacement = r"\1\n\n  useEffect(() => {\n    if (isDetached) updateNodeInternals(id);\n  }, [isOnLeft, isDetached, id, updateNodeInternals]);"
content = re.sub(draggable_effect_pattern, draggable_effect_replacement, content, count=1)


# Fix DetachedTextNode
detached_pattern = r"(export const DetachedTextNode = \(\{ id, data \}\) => \{\n  const \[localValue, setLocalValue\] = useState\(data\.value \|\| ''\);)"
detached_replacement = r"\1\n  const updateNodeInternals = useUpdateNodeInternals();"
content = re.sub(detached_pattern, detached_replacement, content, count=1)

detached_effect_pattern = r"(const isOnLeft = myNodeX < parentNodeX;)"
detached_effect_replacement = r"\1\n\n  useEffect(() => {\n    updateNodeInternals(id);\n  }, [isOnLeft, id, updateNodeInternals]);"
content = re.sub(detached_effect_pattern, detached_effect_replacement, content, count=1)


with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed updateNodeInternals!")
