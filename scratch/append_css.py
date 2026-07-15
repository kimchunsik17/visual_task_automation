css_to_add = """

/* AI Highlight Effect */
.custom-node.ai-highlight {
  box-shadow: 0 0 0 2px #10b981, 0 0 15px rgba(16, 185, 129, 0.4) !important;
  border-color: #10b981 !important;
  transition: box-shadow 0.3s ease, border-color 0.3s ease;
}

/* Collapsed Badge */
.node-collapsed-badge {
  padding: 8px 12px;
  background-color: var(--btn-active-bg);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-color);
  opacity: 0.8;
  margin-top: 4px;
  font-style: italic;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Expanded Textareas for Prompt and Value nodes */
.custom-node.prompt textarea,
.custom-node.value textarea {
  min-height: 120px !important;
  resize: vertical;
  font-size: 13px;
  line-height: 1.4;
  padding: 8px;
}
"""

with open('frontend/src/index.css', 'a', encoding='utf-8') as f:
    f.write(css_to_add)

print("CSS added")
