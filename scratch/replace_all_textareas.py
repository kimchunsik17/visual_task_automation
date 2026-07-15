import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Don't replace inside DraggableTextarea itself!
# We can just split by "export const DraggableTextarea" and only process the second part (or find its end).
# But wait, there is only one textarea in DraggableTextarea, which has `autoFocus` and `onBlur`.
# We can just skip textareas that have `onBlur` or `autoFocus` or are inside DraggableTextarea.

def textarea_replacer(match):
    body = match.group(0)
    
    # Skip DraggableTextarea's internal textarea
    if 'autoFocus' in body or 'onBlur' in body:
        return body
        
    # Extract field key from onChange
    # e.g., onChange={(e) => data.onChange(id, 'systemPrompt', e.target.value)}
    field_match = re.search(r"data\.onChange\(\s*id\s*,\s*['\"]([^'\"]+)['\"]", body)
    if not field_match:
        # Maybe it's a dynamic node or something we can't easily parse
        return body
        
    field_key = field_match.group(1)
    
    # Extract placeholder
    placeholder_match = re.search(r"placeholder=['\"]([^'\"]*)['\"]", body)
    placeholder = placeholder_match.group(1) if placeholder_match else ""
    
    # Also extract default fallback from defaultValue if placeholder is missing
    # e.g., defaultValue={data.systemPrompt || 'You are a helpful assistant.'}
    default_fallback_match = re.search(r"defaultValue=\{[^\}]+\|\|\s*['\"]([^'\"]+)['\"]\s*\}", body)
    if default_fallback_match and not placeholder:
        placeholder = default_fallback_match.group(1)
        
    # Replace with DraggableTextarea
    return f'<DraggableTextarea id={{id}} fieldKey="{field_key}" value={{data.{field_key}}} onChange={{data.onChange}} placeholder="{placeholder}" isDetached={{data.isDetached_{field_key}}} />'

# Find <textarea ... /> or <textarea> ... </textarea>
# Usually they are self closing <textarea ... /> or <textarea ... ></textarea>
new_content = re.sub(r'<textarea[\s\S]*?(?:/>|></textarea>)', textarea_replacer, content)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("All textareas replaced")
