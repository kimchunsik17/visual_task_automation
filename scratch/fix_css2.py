import re

with open('frontend/src/index.css', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the previous block with the :not selector
old_css = """.custom-node .react-flow__handle-left,
.custom-node .react-flow__handle-right {
  top: 70px !important;
  transform: translateY(-50%) !important;
}"""

new_css = """.custom-node .react-flow__handle-left:not(.popout-handle),
.custom-node .react-flow__handle-right:not(.popout-handle) {
  top: 70px !important;
  transform: translateY(-50%) !important;
}"""

content = content.replace(old_css, new_css)

with open('frontend/src/index.css', 'w', encoding='utf-8') as f:
    f.write(content)
