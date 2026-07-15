import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# We need to inject onInput to <textarea
# Some <textarea might already have onInput, but let's assume they don't.
# They have onChange. We can inject an onLoad/onInput style directly.
# Alternatively, we can use a custom hook or just the inline onInput.

def repl(m):
    textarea_body = m.group(1)
    if 'onInput=' not in textarea_body:
        # insert onInput just before closing or onChange
        return f'<textarea {textarea_body} onInput={{(e) => {{ e.target.style.height = "auto"; e.target.style.height = e.target.scrollHeight + "px"; }}}} />'
    return m.group(0)

content = re.sub(r'<textarea\s+([^>]+?)/>', repl, content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

# Update index.css to set max-height and hidden overflow by default so it can grow
with open('frontend/src/index.css', 'r', encoding='utf-8') as f:
    css = f.read()

css = css.replace('min-height: 120px;', 'min-height: 60px;\n  max-height: 300px;\n  overflow-y: hidden;')
css = css.replace('resize: vertical;', 'resize: none; /* Auto-resizing handles this */')

with open('frontend/src/index.css', 'w', encoding='utf-8') as f:
    f.write(css)

print("Auto-resize added")
