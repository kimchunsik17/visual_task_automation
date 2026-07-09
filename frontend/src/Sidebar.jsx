import React from 'react';

const Sidebar = () => {
  const onDragStart = (event, nodeType, label) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.setData('application/reactflow-label', label);
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-title">Nodes</div>
      <div className="sidebar-description">Drag and drop nodes to build your AI workflow.</div>

      <div className="node-list">
        <div
          className="dnd-node start"
          onDragStart={(event) => onDragStart(event, 'startNode', 'Start')}
          draggable
          style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)', fontWeight: 'bold' }}
        >
          🏁 Start
        </div>
        <div
          className="dnd-node prompt"
          onDragStart={(event) => onDragStart(event, 'promptNode', 'Prompt')}
          draggable
        >
          Prompt
        </div>
        <div
          className="dnd-node llm"
          onDragStart={(event) => onDragStart(event, 'llmNode', 'LLM')}
          draggable
        >
          LLM
        </div>
        <div
          className="dnd-node value"
          onDragStart={(event) => onDragStart(event, 'valueNode', 'Value')}
          draggable
          style={{ background: 'linear-gradient(135deg, #ec4899, #be185d)' }}
        >
          Value
        </div>
        <div
          className="dnd-node python"
          onDragStart={(event) => onDragStart(event, 'pythonNode', 'Python')}
          draggable
          style={{ background: 'linear-gradient(135deg, #3b82f6, #2563eb)' }}
        >
          Python
        </div>
        <div
          className="dnd-node condition"
          onDragStart={(event) => onDragStart(event, 'conditionNode', 'Switch / Branch')}
          draggable
          style={{ background: 'linear-gradient(135deg, #0ea5e9, #0369a1)' }}
        >
          Switch
        </div>
        <div
          className="dnd-node output"
          onDragStart={(event) => onDragStart(event, 'outputNode', 'Output')}
          draggable
        >
          Output
        </div>
        <div
          className="dnd-node tokenizer"
          onDragStart={(event) => onDragStart(event, 'tokenizerNode', 'Tokenizer')}
          draggable
          style={{ background: 'linear-gradient(135deg, #10b981, #059669)' }}
        >
          Tokenizer
        </div>
        <div
          className="dnd-node distributor"
          onDragStart={(event) => onDragStart(event, 'distributorNode', 'Distributor')}
          draggable
          style={{ background: 'linear-gradient(135deg, #8b5cf6, #7c3aed)' }}
        >
          Distributor
        </div>
        <div
          className="dnd-node file-modifier"
          onDragStart={(event) => onDragStart(event, 'fileModifierNode', 'Auto Fill')}
          draggable
          style={{ background: 'linear-gradient(135deg, #f97316, #ea580c)' }}
        >
          Auto Fill
        </div>
        <div
          className="dnd-node template-analyzer"
          onDragStart={(event) => onDragStart(event, 'templateAnalyzerNode', 'Template Analyzer')}
          draggable
          style={{ background: 'linear-gradient(135deg, #14b8a6, #0d9488)' }}
        >
          Template
        </div>
        <div
          className="dnd-node loop"
          onDragStart={(event) => onDragStart(event, 'loopNode', 'Loop')}
          draggable
          style={{ background: 'linear-gradient(135deg, #ca8a04, #854d0e)' }}
        >
          Loop
        </div>
        <div
          className="dnd-node break"
          onDragStart={(event) => onDragStart(event, 'breakNode', 'Break')}
          draggable
          style={{ background: 'linear-gradient(135deg, #dc2626, #991b1b)' }}
        >
          Break
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
