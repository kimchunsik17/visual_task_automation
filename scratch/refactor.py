import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add ChevronDown, ChevronRight to imports
if 'ChevronDown' not in content:
    content = content.replace("from 'lucide-react';", ", ChevronDown, ChevronRight } from 'lucide-react';")
    content = content.replace("} ,", ",")

components = re.split(r'^(export const \w+\s*=\s*\(\{.*?\}\)\s*=>\s*\{)', content, flags=re.MULTILINE)

new_content = components[0]
for i in range(1, len(components), 2):
    header = components[i]
    body = components[i+1]
    
    if '<div className="node-header"' in body and '<div className="node-body"' in body:
        # inject state
        state_injection = '''
  const [isExpanded, setIsExpanded] = useState(false);
  const isAIModified = data.isAIModified;
  const handleNodeClick = () => {
    if (data.isAIModified && data.onClearAIHighlight) {
      data.onClearAIHighlight(id);
    }
  };
'''
        body = state_injection + body
        
        # update custom-node div
        body = re.sub(r'<div className="(custom-node [^"]+)"([^>]*)>', r'<div className={`\1 ${isAIModified ? \'ai-highlight\' : \'\'}`} onClick={handleNodeClick}\2>', body, count=1)
        
        # update node-header
        def header_repl(m):
            header_div = m.group(1)
            inner = m.group(2)
            if '<div style={{ display: \'flex\'' in inner:
                inner = inner.replace('<div style={{ display: \'flex\', alignItems: \'center\', gap: \'6px\' }}>', '<div style={{ display: \'flex\', alignItems: \'center\', gap: \'6px\' }}>{isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}')
            else:
                inner = '{isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />} ' + inner
            return f'<div className="node-header" onClick={{() => setIsExpanded(!isExpanded)}} style={{{{ cursor: \'pointer\' }}}}>{inner}</div>'
        
        body = body.replace('<div className="node-header">', '<div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{ cursor: \'pointer\' }}>\n        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}\n        ')
        body = re.sub(r'<div className="node-header" style={{([^}]+)}}>', r'<div className="node-header" onClick={() => setIsExpanded(!isExpanded)} style={{\1, cursor: \'pointer\' }}>\n        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}\n        ', body)
        
        # Now wrap node-body with {isExpanded && ( ... )}
        body_start_match = re.search(r'<div className="node-body"[^>]*>', body)
        if body_start_match:
            start_idx = body_start_match.start()
            div_count = 0
            end_idx = -1
            i_idx = start_idx
            while i_idx < len(body):
                if body.startswith('<div', i_idx):
                    div_count += 1
                elif body.startswith('</div', i_idx):
                    div_count -= 1
                    if div_count == 0:
                        end_idx = i_idx + 6
                        break
                i_idx += 1
            
            if end_idx != -1:
                wrapped = "{isExpanded ? (\n        " + body[start_idx:end_idx] + "\n      ) : (\n        <div className=\"node-collapsed-badge\">{data.label || 'Collapsed'}</div>\n      )}"
                body = body[:start_idx] + wrapped + body[end_idx:]

    new_content += header + body

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Done")
