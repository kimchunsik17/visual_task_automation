import React, { useState } from 'react';
import { Play, MessageSquare, BrainCircuit, Box, Terminal, Shuffle, LogOut, SplitSquareHorizontal, FileCode, Search, Variable, Network, Repeat, Keyboard, Globe, Mail, MessageCircle, Clock, Braces, Merge, ArrowRightLeft, Database, UserCheck, Users, ChevronDown, ChevronRight, Puzzle, CreditCard } from 'lucide-react';
import { NodeRegistry } from './nodeRegistry';

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
    { type: 'startNode', label: '시작', icon: <Play size={16} />, color: '#10b981', category: 'core' },
    { type: 'scheduleNode', label: '스케줄 (시작)', icon: <Clock size={16} />, color: '#8b5cf6', category: 'core' },
    { type: 'outputNode', label: '결과 출력', icon: <LogOut size={16} />, color: '#f97316', category: 'core' },
    
    { type: 'dynamicInputNode', label: '동적 입력', icon: <Keyboard size={16} />, color: '#d946ef', category: 'input' },
    { type: 'webhookNode', label: '웹훅 수신', icon: <Globe size={16} />, color: '#0ea5e9', category: 'input' },
    { type: 'valueNode', label: '변수 (값)', icon: <Variable size={16} />, color: '#ec4899', category: 'input' },
    
    { type: 'promptNode', label: '프롬프트', icon: <MessageSquare size={16} />, color: '#3b82f6', category: 'ai' },
          { type: 'llmNode', label: 'LLM', icon: <BrainCircuit size={16} />, color: '#8b5cf6', category: 'ai' },
      { type: 'multiAgentNode', label: 'Multi-Agent', icon: <Users size={16} />, color: '#6366f1', category: 'ai' },
    
    { type: 'conditionNode', label: '조건 분기', icon: <SplitSquareHorizontal size={16} />, color: '#0ea5e9', category: 'logic' },
    { type: 'loopNode', label: '반복 (Loop)', icon: <Repeat size={16} />, color: '#ca8a04', category: 'logic' },
    { type: 'breakNode', label: '반복 종료', icon: <LogOut size={16} style={{transform: 'rotate(180deg)'}}/>, color: '#dc2626', category: 'logic' },
    { type: 'delayNode', label: 'Delay (대기)', icon: <Clock size={16} />, color: '#3b82f6', category: 'logic' },
    { type: 'mergeNode', label: 'Merge (병합)', icon: <Merge size={16} />, color: '#ec4899', category: 'logic' },
    
    { type: 'pythonNode', label: '파이썬', icon: <Terminal size={16} />, color: '#eab308', category: 'code' },
    { type: 'jsonParserNode', label: 'JSON 파서', icon: <Braces size={16} />, color: '#eab308', category: 'code' },
    { type: 'tokenizerNode', label: '토크나이저', icon: <Box size={16} />, color: '#14b8a6', category: 'code' },
    { type: 'distributorNode', label: '분배기', icon: <Network size={16} />, color: '#6366f1', category: 'code' },
    { type: 'databaseNode', label: '데이터베이스', icon: <Database size={16} />, color: '#059669', category: 'code' },
    
    { type: 'webCrawlerNode', label: '웹 크롤러', icon: <Globe size={16} />, color: '#0ea5e9', category: 'integration' },
    { type: 'emailNode', label: '이메일 전송', icon: <Mail size={16} />, color: '#f43f5e', category: 'integration' },
    { type: 'kakaoNode', label: '카카오 알림톡', icon: <MessageCircle size={16} />, color: '#facc15', category: 'integration' },
    { type: 'discordNode', label: '디스코드 발송', icon: <MessageCircle size={16} />, color: '#5865F2', category: 'integration' },
    { type: 'tossNode', label: '토스페이먼츠', icon: <CreditCard size={16} />, color: '#3b82f6', category: 'integration' },
    { type: 'httpRequestNode', label: 'HTTP Request', icon: <ArrowRightLeft size={16} />, color: '#0ea5e9', category: 'integration' },
    
    { type: 'fileModifierNode', label: '자동 완성', icon: <FileCode size={16} />, color: '#f43f5e', category: 'advanced' },
    { type: 'templateAnalyzerNode', label: '템플릿 분석', icon: <FileCode size={16} />, color: '#8b5cf6', category: 'advanced' },
    { type: 'humanApprovalNode', label: '사용자 승인 (대기)', icon: <UserCheck size={16} />, color: '#f43f5e', category: 'advanced' },
  ];

  // Append dynamic nodes from registry
  Object.values(NodeRegistry).forEach(meta => {
    nodeTypes.push({
      type: meta.type,
      label: meta.label,
      icon: <Puzzle size={16} />, // Default icon for dynamic nodes
      color: meta.color,
      category: meta.category || 'integration'
    });
  });

  const categories = [
    { id: 'core', title: '기본 (Core)' },
    { id: 'input', title: '입력 (Input)' },
    { id: 'ai', title: 'AI 모델 (AI)' },
    { id: 'logic', title: '제어 로직 (Logic)' },
    { id: 'code', title: '코드 & 데이터 (Code & Data)' },
    { id: 'integration', title: '외부 연동 (Integration)' },
    { id: 'advanced', title: '고급 기능 (Advanced)' },
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
        <h2 className="sidebar-title">노드 목록</h2>
      </div>
      
      <div className="sidebar-search">
        <Search size={14} color="#64748b" />
        <input 
          type="text" 
          placeholder="노드 검색..." 
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>

      <div className="node-list">
        {isSearching ? (
          // 검색 중일 때는 카테고리 구분 없이 일치하는 모든 노드를 보여줌
          nodeTypes
            .filter(n => n.label.toLowerCase().includes(searchTerm.toLowerCase()))
            .map(renderNode)
        ) : (
          // 검색 중이 아닐 때는 카테고리별 아코디언으로 보여줌
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


