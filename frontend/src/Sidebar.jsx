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
      <div className="sidebar-description">Drag and drop nodes to the canvas.</div>
      
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
          style={{background: 'linear-gradient(135deg, #ec4899, #be185d)'}}
        >
          Value
        </div>
        <div 
          className="dnd-node condition" 
          onDragStart={(event) => onDragStart(event, 'conditionNode', 'Switch / Branch')} 
          draggable 
          style={{background: 'linear-gradient(135deg, #0ea5e9, #0369a1)'}}
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
      </div>
    </aside>
  );
};

export default Sidebar;
