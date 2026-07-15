import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace inline width/minWidth with conditional ones based on isExpanded
# We look for something like: style={{ border: '1px solid #3b82f6', width: '300px' }}
# or style={{ minWidth: '150px' }}
# This regex targets width: '...' and minWidth: '...' inside style={{...}}
# Only if it's on a div with custom-node

def style_replacer(match):
    full_str = match.group(0)
    # Don't replace if it already has a ternary or it's DetachedTextNode (which has no isExpanded)
    if '?' in full_str or 'detached-text-node' in full_str:
        return full_str
        
    new_str = re.sub(r"(width:\s*['\"][\w]+['\"])", r"\1.replace(/'|\"/g, '')", full_str) # Just an intermediate mental step
    # We can just replace the width literal with a ternary
    new_str = re.sub(r"width:\s*['\"]([^'\"]+)['\"]", r"width: isExpanded ? '\1' : undefined", full_str)
    new_str = re.sub(r"minWidth:\s*['\"]([^'\"]+)['\"]", r"minWidth: isExpanded ? '\1' : undefined", new_str)
    return new_str

content = re.sub(r'<div className=\{`custom-node[^>]*style=\{\{.*?\}\}[^>]*>', style_replacer, content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Widths updated")
