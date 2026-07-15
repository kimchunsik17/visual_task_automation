with open('frontend/src/index.css', 'r', encoding='utf-8') as f:
    css = f.read()

# Replace the collapsed rule
import re
css = re.sub(r'\.custom-node\.collapsed \{[\s\S]*?\}', '', css)

new_collapsed_css = """
.custom-node.collapsed {
  min-width: 140px;
  max-width: 140px;
  height: 140px;
  display: flex;
  flex-direction: column;
}

.custom-node.collapsed .node-header {
  height: 100%;
  border-radius: 16px;
  border-bottom: none;
  flex-direction: column;
  justify-content: center;
  position: relative;
  padding: 1rem;
}

.custom-node.collapsed .node-header > svg:first-child {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%) rotate(90deg);
  opacity: 0.5;
  transition: opacity 0.2s;
}

.custom-node.collapsed .node-header:hover > svg:first-child {
  opacity: 1;
}

.custom-node.collapsed .node-header .btn-delete {
  position: absolute;
  top: 12px;
  right: 12px;
}

.custom-node.collapsed .node-header > div {
  flex-direction: column !important;
  gap: 12px !important;
  text-align: center;
  white-space: pre-wrap;
  word-break: keep-all;
  line-height: 1.3;
  font-size: 0.9rem;
}

.custom-node.collapsed .node-header > div > svg {
  width: 32px !important;
  height: 32px !important;
}
"""

with open('frontend/src/index.css', 'w', encoding='utf-8') as f:
    f.write(css + new_collapsed_css)

print("Square styling applied")
