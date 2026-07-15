with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

bad = """<<<<<<< HEAD
    const handleSave = async () => {
      if (!user) {
        alert("프로젝트를 저장하려면 로그인이 필요합니다. 왼쪽 메뉴에서 구글 계정으로 로그인해주세요.");
        return null;
      }
=======
    const handleSave = async (overrideVisibility = null) => {
>>>>>>> origin/feature/visibility-friends-system"""

good = """    const handleSave = async (overrideVisibility = null) => {
      if (!user) {
        alert("프로젝트를 저장하려면 로그인이 필요합니다. 왼쪽 메뉴에서 구글 계정으로 로그인해주세요.");
        return null;
      }"""

content = content.replace(bad, good)

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
