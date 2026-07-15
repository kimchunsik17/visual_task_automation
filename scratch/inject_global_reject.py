import re

with open('frontend/src/main.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

global_reject = """
window.addEventListener('unhandledrejection', function(event) {
  const div = document.createElement('div');
  div.style.position = 'fixed';
  div.style.top = '0';
  div.style.left = '0';
  div.style.width = '100vw';
  div.style.height = '100vh';
  div.style.backgroundColor = 'darkred';
  div.style.color = 'white';
  div.style.zIndex = '999999';
  div.style.padding = '20px';
  div.style.whiteSpace = 'pre-wrap';
  div.style.overflow = 'auto';
  div.innerHTML = '<h1>FATAL PROMISE ERROR</h1><pre>' + (event.reason?.stack || event.reason) + '</pre>';
  document.body.appendChild(div);
});
"""

if "FATAL PROMISE ERROR" not in content:
    content = global_reject + "\n" + content
    with open('frontend/src/main.jsx', 'w', encoding='utf-8') as f:
        f.write(content)

print("Global rejection handler injected")
