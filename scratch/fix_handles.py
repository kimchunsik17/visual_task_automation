import re

with open('frontend/src/index.css', 'r', encoding='utf-8') as f:
    content = f.read()

handle_css = """
/* Force Left/Right handles to align with the 140px square header vertically */
.custom-node .react-flow__handle-left,
.custom-node .react-flow__handle-right {
  top: 70px !important;
  transform: translateY(-50%) !important;
}

/* Allow custom positioning for the popout specific handles if needed */
.custom-node .react-flow__handle.popout-handle {
  top: auto !important;
  transform: translateY(-50%) !important;
}
"""

if '.react-flow__handle-left' not in content:
    content += "\n" + handle_css

with open('frontend/src/index.css', 'w', encoding='utf-8') as f:
    f.write(content)
