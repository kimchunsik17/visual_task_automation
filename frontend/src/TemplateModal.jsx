import React, { useState, useEffect } from 'react';
import { Save, Folder, X, Play } from 'lucide-react';
import './TemplateModal.css';

const BUILT_IN_TEMPLATES = [
  {
    id: 'builtin-1',
    name: '📝 Document Auto Fill (Resume)',
    description: 'Extracts data from unstructured text and auto-fills an HWP/Excel/PPT template.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_1', type: 'templateAnalyzerNode', position: { x: 300, y: 150 }, data: { label: 'Template Analyzer', template_path: 'C:\\Users\\kimchunsik\\Desktop\\업무자동화 비주얼화\\backend\\uploads\\입사 지원서 .hwp', filename: '입사 지원서 .hwp' } },
        { id: 'node_info', type: 'valueNode', position: { x: 550, y: 150 }, data: { label: 'Applicant Info', value: '홍길동은 네이버에서 3년간 마케팅 기획자로 일했습니다. 연락처는 010-1234-5678이며 마케팅 팀에 지원합니다.' } },
        { id: 'node_2', type: 'promptNode', position: { x: 850, y: 150 }, data: { label: 'Prompt', userPrompt: '다음 JSON 형식(keys)에 맞게 텍스트에서 정보를 추출해 줘. 반드시 JSON 형식으로만 대답해.' } },
        { id: 'node_3', type: 'llmNode', position: { x: 1200, y: 150 }, data: { label: 'LLM', model: 'gemini-3.5-flash', systemPrompt: 'You are a precise data extraction assistant.' } },
        { id: 'node_4', type: 'fileModifierNode', position: { x: 1550, y: 150 }, data: { label: 'Auto Fill', template_path: 'C:\\Users\\kimchunsik\\Desktop\\업무자동화 비주얼화\\backend\\uploads\\입사 지원서 .hwp', filename: '입사 지원서 .hwp', output_path: 'output_filled.hwp' } }
      ],
      edges: [
        { id: 'e_start-1', source: 'node_start', target: 'node_1', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e1-info', source: 'node_1', target: 'node_info', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_info-2', source: 'node_info', target: 'node_2', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e2-3', source: 'node_2', target: 'node_3', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e3-4', source: 'node_3', target: 'node_4', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-2',
    name: '🌐 Simple Translation Flow',
    description: 'Basic flow to translate input text into another language.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_1', type: 'valueNode', position: { x: 300, y: 150 }, data: { label: 'Value', value: 'Hello, how are you?' } },
        { id: 'node_2', type: 'llmNode', position: { x: 650, y: 150 }, data: { label: 'LLM', model: 'gpt-4o-mini', systemPrompt: 'You are a professional translator. Translate the given text to Korean.' } },
        { id: 'node_3', type: 'outputNode', position: { x: 1000, y: 150 }, data: { label: 'Output' } }
      ],
      edges: [
        { id: 'e_start-1', source: 'node_start', target: 'node_1', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e1-2', source: 'node_1', target: 'node_2', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e2-3', source: 'node_2', target: 'node_3', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  }
];

export default function TemplateModal({ isOpen, onClose, onSave, onLoad, currentFlowData }) {
  const [savedTemplates, setSavedTemplates] = useState([]);
  const [newTemplateName, setNewTemplateName] = useState('');

  useEffect(() => {
    if (isOpen) {
      const stored = localStorage.getItem('user_templates');
      if (stored) {
        try {
          setSavedTemplates(JSON.parse(stored));
        } catch (e) {
          console.error('Failed to parse templates', e);
        }
      }
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = () => {
    if (!newTemplateName.trim()) return alert('Please enter a template name.');
    
    const newTemplate = {
      id: `usr-${Date.now()}`,
      name: newTemplateName.trim(),
      description: 'User saved template',
      data: currentFlowData()
    };
    
    const updated = [...savedTemplates, newTemplate];
    localStorage.setItem('user_templates', JSON.stringify(updated));
    setSavedTemplates(updated);
    setNewTemplateName('');
  };

  const handleDelete = (id) => {
    if (!window.confirm('Delete this template?')) return;
    const updated = savedTemplates.filter(t => t.id !== id);
    localStorage.setItem('user_templates', JSON.stringify(updated));
    setSavedTemplates(updated);
  };

  const loadTemplate = (template) => {
    if (window.confirm(`Load template "${template.name}"? This will overwrite your current canvas.`)) {
      onLoad(template.data);
      onClose();
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2><Folder size={20} /> Templates Manager</h2>
          <button className="btn-icon" onClick={onClose}><X size={20}/></button>
        </div>

        <div className="modal-body">
          <div className="template-section">
            <h3>Save Current Flow</h3>
            <div className="save-flow-row">
              <input 
                type="text" 
                placeholder="Enter template name..." 
                value={newTemplateName}
                onChange={e => setNewTemplateName(e.target.value)}
              />
              <button className="btn-primary" onClick={handleSave}>
                <Save size={16} /> Save
              </button>
            </div>
          </div>

          <div className="template-section">
            <h3>Built-in Templates</h3>
            <div className="template-grid">
              {BUILT_IN_TEMPLATES.map(t => (
                <div key={t.id} className="template-card">
                  <h4>{t.name}</h4>
                  <p>{t.description}</p>
                  <button className="btn-load" onClick={() => loadTemplate(t)}>
                    <Play size={16} /> Load
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="template-section">
            <h3>My Saved Templates</h3>
            {savedTemplates.length === 0 ? (
              <p className="empty-text">No saved templates yet.</p>
            ) : (
              <div className="template-grid">
                {savedTemplates.map(t => (
                  <div key={t.id} className="template-card user-template">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <h4>{t.name}</h4>
                      <button className="btn-icon delete" onClick={() => handleDelete(t.id)}><X size={16}/></button>
                    </div>
                    <p>{t.description}</p>
                    <button className="btn-load" onClick={() => loadTemplate(t)}>
                      <Play size={16} /> Load
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
