import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

conflict_pattern = re.compile(r"<<<<<<< HEAD.*?=======\n(.*?)\n>>>>>>> origin/feature/visibility-friends-system", re.DOTALL)

def replacement(match):
    return """      alert("프로젝트를 저장하려면 로그인이 필요합니다. 왼쪽 메뉴에서 구글 계정으로 로그인해주세요.");
      return null;
    }"""

content = conflict_pattern.sub(replacement, content, count=1)

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
