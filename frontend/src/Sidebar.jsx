import React, { useState } from 'react';
import { Play, MessageSquare, BrainCircuit, Box, Terminal, Shuffle, LogOut, SplitSquareHorizontal, FileCode, Search, Variable, Network, Repeat, Keyboard, Globe, Mail, MessageCircle, Clock, Braces, Merge, ArrowRightLeft, Database, UserCheck, ChevronDown, ChevronRight } from 'lucide-react';

const Sidebar = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedCategories, setExpandedCategories] = useState({
    core: true,
    input: true,
    ai: true,
    logic: false,
    code: false,
    integration: false,
    advanced: false
  });

  const onDragStart = (event, nodeType, label) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.setData('application/reactflow-label', label);
    event.dataTransfer.effectAllowed = 'move';
  };

  const nodeTypes = [
    { type: 'startNode', label: '?úÏûë', icon: <Play size={16} />, color: '#10b981', category: 'core' },
    { type: 'outputNode', label: 'Í≤∞Í≥º Ï∂úÎ†•', icon: <LogOut size={16} />, color: '#f97316', category: 'core' },
    
    { type: 'dynamicInputNode', label: '?ôÏ†Å ?ÖÎ†•', icon: <Keyboard size={16} />, color: '#d946ef', category: 'input' },
    { type: 'valueNode', label: 'Î≥Ä??(Í∞?', icon: <Variable size={16} />, color: '#ec4899', category: 'input' },
    
    { type: 'promptNode', label: '?ÑÎ°¨?ÑÌä∏', icon: <MessageSquare size={16} />, color: '#3b82f6', category: 'ai' },
    { type: 'llmNode', label: 'LLM', icon: <BrainCircuit size={16} />, color: '#8b5cf6', category: 'ai' },
    
    { type: 'conditionNode', label: 'Ï°∞Í±¥ Î∂ÑÍ∏∞', icon: <SplitSquareHorizontal size={16} />, color: '#0ea5e9', category: 'logic' },
    { type: 'loopNode', label: 'Î∞òÎ≥µ (Loop)', icon: <Repeat size={16} />, color: '#ca8a04', category: 'logic' },
    { type: 'breakNode', label: 'Î∞òÎ≥µ Ï¢ÖÎ£å', icon: <LogOut size={16} style={{transform: 'rotate(180deg)'}}/>, color: '#dc2626', category: 'logic' },
    { type: 'delayNode', label: 'Delay (?ÄÍ∏?', icon: <Clock size={16} />, color: '#3b82f6', category: 'logic' },
    { type: 'mergeNode', label: 'Merge (Î≥ëÌï©)', icon: <Merge size={16} />, color: '#ec4899', category: 'logic' },
    
    { type: 'pythonNode', label: '?åÏù¥??, icon: <Terminal size={16} />, color: '#eab308', category: 'code' },
    { type: 'jsonParserNode', label: 'JSON ?åÏÑú', icon: <Braces size={16} />, color: '#eab308', category: 'code' },
    { type: 'tokenizerNode', label: '?†ÌÅ¨?òÏù¥?Ä', icon: <Box size={16} />, color: '#14b8a6', category: 'code' },
    { type: 'distributorNode', label: 'Î∂ÑÎ∞∞Í∏?, icon: <Network size={16} />, color: '#6366f1', category: 'code' },
    { type: 'databaseNode', label: '?∞Ïù¥?∞Î≤†?¥Ïä§', icon: <Database size={16} />, color: '#059669', category: 'code' },
    
    { type: 'webCrawlerNode', label: '???¨Î°§??, icon: <Globe size={16} />, color: '#0ea5e9', category: 'integration' },
    { type: 'emailNode', label: '?¥Î©î???ÑÏÜ°', icon: <Mail size={16} />, color: '#f43f5e', category: 'integration' },
    { type: 'kakaoNode', label: 'Ïπ¥Ïπ¥???åÎ¶º??, icon: <MessageCircle size={16} />, color: '#facc15', category: 'integration' },
    { type: 'httpRequestNode', label: 'HTTP Request', icon: <ArrowRightLeft size={16} />, color: '#0ea5e9', category: 'integration' },
    
    { type: 'fileModifierNode', label: '?êÎèô ?ÑÏÑ±', icon: <FileCode size={16} />, color: '#f43f5e', category: 'advanced' },
    { type: 'templateAnalyzerNode', label: '?úÌîåÎ¶?Î∂ÑÏÑù', icon: <FileCode size={16} />, color: '#8b5cf6', category: 'advanced' },
    { type: 'humanApprovalNode', label: '?¨Ïö©???πÏù∏ (?ÄÍ∏?', icon: <UserCheck size={16} />, color: '#f43f5e', category: 'advanced' },
  ];

  const categories = [
    { id: 'core', title: 'Í∏∞Î≥∏ (Core)' },
    { id: 'input', title: '?ÖÎ†• (Input)' },
    { id: 'ai', title: 'AI Î™®Îç∏ (AI)' },
    { id: 'logic', title: '?úÏñ¥ Î°úÏßÅ (Logic)' },
    { id: 'code', title: 'ÏΩîÎìú & ?∞Ïù¥??(Code & Data)' },
    { id: 'integration', title: '?∏Î? ?∞Îèô (Integration)' },
    { id: 'advanced', title: 'Í≥†Í∏â Í∏∞Îä• (Advanced)' },
  ];

  const toggleCategory = (catId) => {
    setExpandedCategories(prev => ({...prev, [catId]: !prev[catId]}));
  };

  const isSearching = searchTerm.trim() !== '';

  const renderNode = (node) => (
    <div
      key={node.type}
      className="dnd-node"
      onDragStart={(event) => onDragStart(event, node.type, node.label)}
      draggable
    >
      <div className="dnd-node-icon" style={{ backgroundColor: `${node.color}20`, color: node.color }}>
        {node.icon}
      </div>
      <span className="dnd-node-label">{node.label}</span>
    </div>
  );

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2 className="sidebar-title">?∏Îìú Î™©Î°ù</h2>
      </div>
      
      <div className="sidebar-search">
        <Search size={14} color="#64748b" />
        <input 
          type="text" 
          placeholder="?∏Îìú Í≤Ä??.." 
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>

      <div className="node-list">
        {isSearching ? (
          // Í≤Ä??Ï§ëÏùº ?åÎäî Ïπ¥ÌÖåÍ≥†Î¶¨ Íµ¨Î∂Ñ ?ÜÏù¥ ?ºÏπò?òÎäî Î™®Îì† ?∏ÎìúÎ•?Î≥¥Ïó¨Ï§?
          nodeTypes
            .filter(n => n.label.toLowerCase().includes(searchTerm.toLowerCase()))
            .map(renderNode)
        ) : (
          // Í≤Ä??Ï§ëÏù¥ ?ÑÎãê ?åÎäî Ïπ¥ÌÖåÍ≥†Î¶¨Î≥??ÑÏΩî?îÏñ∏?ºÎ°ú Î≥¥Ïó¨Ï§?
          categories.map(cat => {
            const catNodes = nodeTypes.filter(n => n.category === cat.id);
            if (catNodes.length === 0) return null;
            
            const isExpanded = expandedCategories[cat.id];
            
            return (
              <div key={cat.id} className="sidebar-category">
                <div 
                  className="sidebar-category-header" 
                  onClick={() => toggleCategory(cat.id)}
                  style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', padding: '8px 4px', color: 'var(--text-muted)', fontSize: '0.8rem', fontWeight: '600', userSelect: 'none' }}
                >
                  {isExpanded ? <ChevronDown size={14} style={{ marginRight: '4px' }}/> : <ChevronRight size={14} style={{ marginRight: '4px' }}/>}
                  {cat.title}
                </div>
                {isExpanded && (
                  <div className="sidebar-category-nodes" style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingBottom: '8px' }}>
                    {catNodes.map(renderNode)}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};

export default Sidebar;

