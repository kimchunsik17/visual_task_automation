with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace {isExpanded ? ( with {isExpanded && (
# BUT wait! We should only replace it if the matching : ( was removed.
# Actually, since we removed the badge from all of them, they are ALL missing the `:`.
# So we can just replace `{isExpanded ? (` with `{isExpanded && (` everywhere.
text = text.replace("{isExpanded ? (", "{isExpanded && (")

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(text)
