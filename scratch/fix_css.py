import re

with open('frontend/src/index.css', 'r', encoding='utf-8') as f:
    content = f.read()

# I want to make sure the popout-handle is not overridden by the top: 70px !important
content = content.replace("top: auto !important;", "")

with open('frontend/src/index.css', 'w', encoding='utf-8') as f:
    f.write(content)
