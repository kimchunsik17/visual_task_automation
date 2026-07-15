import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add NodeDetachedHandles component before DraggableTextarea
new_components = """
const DetachedHandleRenderer = ({ id, fieldKey }) => {
  const updateNodeInternals = useUpdateNodeInternals();
  const detachedNodeId = `popout_${id}_${fieldKey}`;
  const detachedNodeX = useStore((s) => {
    const map = s.nodeLookup || s.nodeInternals;
    if (!map) return 0;
    const node = map.get(detachedNodeId);
    return node ? (node.positionAbsolute?.x ?? node.position?.x ?? 0) : 0;
  });
  const parentNodeX = useStore((s) => {
    const map = s.nodeLookup || s.nodeInternals;
    if (!map) return 0;
    const node = map.get(id);
    return node ? (node.positionAbsolute?.x ?? node.position?.x ?? 0) : 0;
  });

  const isOnLeft = detachedNodeX < parentNodeX;

  useEffect(() => {
    updateNodeInternals(id);
  }, [isOnLeft, id, updateNodeInternals]);

  return (
    <Handle
      className="popout-handle"
      type="target"
      position={isOnLeft ? Position.Left : Position.Right}
      id={`popout-${fieldKey}`}
      style={{
        left: isOnLeft ? '-10px' : '100%',
        top: '20px',
        background: '#ec4899',
        width: '10px',
        height: '10px',
        border: '2px solid white',
        borderRadius: '50%',
        transition: 'left 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        zIndex: 10
      }}
    />
  );
};

export const NodeDetachedHandles = ({ id, data }) => {
  if (!data) return null;
  const detachedKeys = Object.keys(data).filter(k => k.startsWith('isDetached_') && data[k]);
  return (
    <>
      {detachedKeys.map(k => {
        const fieldKey = k.replace('isDetached_', '');
        return <DetachedHandleRenderer key={fieldKey} id={id} fieldKey={fieldKey} />;
      })}
    </>
  );
};

"""

content = content.replace("export const DraggableTextarea", new_components + "export const DraggableTextarea")

# 2. Modify DraggableTextarea to return null if detached
# Currently it is:
#  if (isDetached) {
#    return (
#      <div style={{ position: 'relative', height: '0px', width: '100%', transition: 'all 0.3s ease-in-out' }}>
#        <Handle
#          className="popout-handle"
#          ...
#        />
#      </div>
#    );
#  }
draggable_regex = re.compile(r"if \(isDetached\) \{\n\s*return \(\n\s*<div style=\{\{ position: 'relative'.*?</div>\n\s*\);\n\s*\}", re.DOTALL)
content = draggable_regex.sub("if (isDetached) return null;", content)

# Remove the useEffect about isOnLeft from DraggableTextarea
use_effect_regex = re.compile(r"const isOnLeft = isDetached && detachedNodeX < parentNodeX;\n\n\s*useEffect\(\(\) => \{\n\s*if \(isDetached\) updateNodeInternals\(id\);\n\s*\}, \[isOnLeft, isDetached, id, updateNodeInternals\]\);", re.DOTALL)
content = use_effect_regex.sub("", content)

# 3. Inject NodeDetachedHandles into all nodes
content = re.sub(r"(\s*)(</div\s*>)\s*\n(\s*\);\s*\n\};)", r"\1  <NodeDetachedHandles id={id} data={data} />\n\1\2\n\3", content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
