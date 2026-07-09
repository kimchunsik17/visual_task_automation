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
          className="dnd-node prompt"
          onDragStart={(event) => onDragStart(event, 'promptNode', 'Prompt')}
          draggable
        >
          Prompt Node
        </div>
        <div
          className="dnd-node llm"
          onDragStart={(event) => onDragStart(event, 'llmNode', 'LLM Node')}
          draggable
        >
          LLM Node
        </div>
        <div
          className="dnd-node value"
          onDragStart={(event) => onDragStart(event, 'valueNode', 'Value Node')}
          draggable
          style={{ background: 'linear-gradient(135deg, #ec4899, #be185d)' }}
        >
          Value
        </div>
        <div
          className="dnd-node python"
          onDragStart={(event) => onDragStart(event, 'pythonNode', 'Python Node')}
          draggable
          style={{ background: 'linear-gradient(135deg, #3b82f6, #2563eb)' }}
        >
          Python Node
        </div>
        <div
          className="dnd-node condition"
          onDragStart={(event) => onDragStart(event, 'conditionNode', 'Switch / Branch')}
          draggable
          style={{ background: 'linear-gradient(135deg, #0ea5e9, #0369a1)' }}
        >
          Switch / Branch
        </div>
        <div
          className="dnd-node output"
          onDragStart={(event) => onDragStart(event, 'outputNode', 'Output')}
          draggable
        >
          Output Node
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
          className="dnd-node loop"
          onDragStart={(event) => onDragStart(event, 'loopNode', 'Loop')}
          draggable
          style={{ background: 'linear-gradient(135deg, #ca8a04, #854d0e)' }}
        >
          Loop Node
        </div>
        <div
          className="dnd-node break"
          onDragStart={(event) => onDragStart(event, 'breakNode', 'Break')}
          draggable
          style={{ background: 'linear-gradient(135deg, #dc2626, #991b1b)' }}
        >
          Break Node
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
