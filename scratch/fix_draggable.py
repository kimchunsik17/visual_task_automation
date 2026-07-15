with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(
"""  const onDragStart = (event) => {
    event.dataTransfer.setData('application/reactflow-popout', JSON.stringify({ type: 'popout', sourceId: id, key: fieldKey }));
    event.dataTransfer.effectAllowed = 'move';
  };""",
"""  const onDragStart = (event) => {
    event.stopPropagation();
    event.dataTransfer.setData('application/reactflow-popout', JSON.stringify({ type: 'popout', sourceId: id, key: fieldKey }));
    event.dataTransfer.effectAllowed = 'move';
  };""")

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(text)
