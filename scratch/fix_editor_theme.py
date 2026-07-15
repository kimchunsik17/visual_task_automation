import re

with open('frontend/src/pages/EditorPage.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Add theme state inside FlowContent
hook_str = """
  const [appTheme, setAppTheme] = useState(document.documentElement.getAttribute('data-theme') || 'dark');
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setAppTheme(document.documentElement.getAttribute('data-theme') || 'dark');
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  }, []);
"""

content = content.replace("const reactFlowWrapper = useRef(null);", "const reactFlowWrapper = useRef(null);\n" + hook_str)

# Change colorMode="system" to colorMode={appTheme}
content = content.replace('colorMode="system"', 'colorMode={appTheme}')

with open('frontend/src/pages/EditorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
