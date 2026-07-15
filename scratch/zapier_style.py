with open('frontend/src/index.css', 'r', encoding='utf-8') as f:
    text = f.read()

# Modify .custom-node
text = text.replace('border-radius: 12px;', 'border-radius: 16px;')
text = text.replace('min-width: 220px;', 'min-width: 280px;\n  max-width: 350px;')
text = text.replace('box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);', 'box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);')
text = text.replace('transition: box-shadow 0.2s;', 'transition: box-shadow 0.2s, transform 0.2s;')

# Modify .custom-node:hover
text = text.replace('box-shadow: 0 12px 24px rgba(0, 0, 0, 0.4);', 'box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);\n  transform: translateY(-2px);')

# Modify .node-header
text = text.replace('padding: 0.6rem 1rem;', 'padding: 1rem 1.25rem;')
text = text.replace('font-size: 0.85rem;', 'font-size: 0.95rem;\n  color: var(--text-color);')
text = text.replace('border-radius: 12px 12px 0 0;', 'border-radius: 16px 16px 0 0;')
text = text.replace('background: var(--btn-active-bg);', 'background: var(--card-bg);')
text = text.replace('gap: 0.5rem;', 'gap: 0.75rem;')

# Modify node-body
text = text.replace('padding: 1rem;', 'padding: 1.25rem;\n  padding-top: 0.5rem;')

# Change top borders to left borders
import re
text = re.sub(r'\.custom-node\.([a-zA-Z0-9-]+) \.node-header \{ border-top: 3px solid ([#a-zA-Z0-9]+); \}', r'.custom-node.\1 { border-left: 4px solid \2; }', text)

with open('frontend/src/index.css', 'w', encoding='utf-8') as f:
    f.write(text)

print("Zapier style applied")
