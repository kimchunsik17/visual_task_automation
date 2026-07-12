const fs = require('fs');
const path = require('path');

const content = fs.readFileSync(path.join(__dirname, 'frontend/src/TemplateModal.jsx'), 'utf-8');
const match = content.match(/const BUILT_IN_TEMPLATES = (\[[\s\S]*?\]);\s*export default/);

if (!match) {
  console.log("Could not extract templates");
  process.exit(1);
}

let templates;
try {
  templates = eval(match[1]);
} catch (e) {
  console.error("Failed to eval templates:", e);
  process.exit(1);
}

async function testCompile() {
  let allSuccess = true;
  for (const template of templates) {
    if (template.id.startsWith('builtin-') && parseInt(template.id.split('-')[1]) >= 6) {
      console.log(`Testing compile for ${template.id}: ${template.name}`);
      try {
        const payload = {
          nodes: template.data.nodes,
          edges: template.data.edges
        };
        const res = await fetch('http://localhost:8000/api/compile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
          console.log(`  -> SUCCESS! Script length: ${data.code.length} chars`);
        } else {
          console.error(`  -> ERROR for ${template.id}:`, data);
          allSuccess = false;
        }
      } catch (err) {
        console.error(`  -> ERROR for ${template.id}:`, err.message);
        allSuccess = false;
      }
    }
  }
  if (allSuccess) {
    console.log("\nAll 10 templates compiled successfully!");
  } else {
    console.log("\nSome templates failed to compile.");
  }
}

testCompile();
