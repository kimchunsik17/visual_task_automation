import re

with open('frontend/src/pages/MainPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix imports conflict
conflict1 = re.compile(r"<<<<<<< HEAD\nimport \{ useState, useEffect, useRef \} from 'react';\n=======\nimport \{ useState \} from 'react';\n>>>>>>> origin/feature/visibility-friends-system", re.MULTILINE)
content = conflict1.sub("import { useState, useEffect, useRef } from 'react';", content)

# Fix API conflict
conflict2 = re.compile(r"<<<<<<< HEAD\n(.*?)=======\n.*?>>>>>>> origin/feature/visibility-friends-system", re.DOTALL)
def replacement2(match):
    return match.group(1).rstrip('\n')

content = conflict2.sub(replacement2, content)

with open('frontend/src/pages/MainPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
