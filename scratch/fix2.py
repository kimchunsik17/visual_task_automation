with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("import { Settings , ChevronDown, ChevronRight } from 'lucide-react';", "import { Settings } from 'lucide-react';")

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(text)
