with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Add expanded/collapsed classes
content = content.replace("className={`custom-node ", "className={`custom-node ${isExpanded ? 'expanded' : 'collapsed'} ")

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

with open('frontend/src/index.css', 'r', encoding='utf-8') as f:
    css = f.read()

# Remove the fixed widths from .custom-node
css = css.replace('min-width: 280px;\n  max-width: 350px;', '')

# Add the dynamic width classes
css_to_add = """
.custom-node.collapsed {
  min-width: 220px;
  max-width: 260px;
}
.custom-node.expanded {
  min-width: 300px;
  max-width: 380px;
}
.custom-node {
  transition: box-shadow 0.2s, transform 0.2s, min-width 0.2s, max-width 0.2s;
}
"""

with open('frontend/src/index.css', 'a', encoding='utf-8') as f:
    f.write(css_to_add)

print("Width fix applied")
