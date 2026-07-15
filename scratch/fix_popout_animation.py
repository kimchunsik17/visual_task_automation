import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the Handle style in DraggableTextarea to use left exclusively
old_style_block = """style={isOnLeft 
            ? { left: '-10px', top: '10px', background: '#ec4899', width: '10px', height: '10px', border: '2px solid white', transition: 'all 0.3s ease-in-out' }
            : { right: '-10px', top: '10px', background: '#ec4899', width: '10px', height: '10px', border: '2px solid white', transition: 'all 0.3s ease-in-out' }
          } """

new_style_block = """style={{ 
            left: isOnLeft ? '-10px' : 'calc(100% + 10px)', 
            top: '10px', 
            background: '#ec4899', 
            width: '10px', 
            height: '10px', 
            border: '2px solid white', 
            transition: 'all 0.3s ease-in-out',
            transform: isOnLeft ? 'translateX(0)' : 'translateX(-100%)'
          }} """

content = content.replace(old_style_block, new_style_block)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Animation updated")
