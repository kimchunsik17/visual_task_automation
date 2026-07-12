import React, { useState } from 'react';
import { Play, MessageSquare, BrainCircuit, Box, Terminal, Shuffle, LogOut, SplitSquareHorizontal, FileCode, Search, Variable, Network, Repeat, Keyboard, Globe, Mail, MessageCircle, Clock, Braces, Merge, ArrowRightLeft, Database, UserCheck } from 'lucide-react';

const Sidebar = () => {
  const [searchTerm, setSearchTerm] = useState('');

  const onDragStart = (event, nodeType, label) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.setData('application/reactflow-label', label);
    event.dataTransfer.effectAllowed = 'move';
  };

  const nodeTypes = [
    { type: 'startNode', label: '시작', icon: <Play size={16} />, color: '#10b981' },
    { type: 'promptNode', label: '프롬프트', icon: <MessageSquare size={16} />, color: '#3b82f6' },
    { type: 'llmNode', label: 'LLM', icon: <BrainCircuit size={16} />, color: '#8b5cf6' },
    { type: 'valueNode', label: '변수 (값)', icon: <Variable size={16} />, color: '#ec4899' },
    { type: 'pythonNode', label: '파이썬', icon: <Terminal size={16} />, color: '#eab308' },
    { type: 'conditionNode', label: '조건 분기', icon: <SplitSquareHorizontal size={16} />, color: '#0ea5e9' },
    { type: 'outputNode', label: '결과 출력', icon: <LogOut size={16} />, color: '#f97316' },
    { type: 'tokenizerNode', label: '토크나이저', icon: <Box size={16} />, color: '#14b8a6' },
    { type: 'distributorNode', label: '분배기', icon: <Network size={16} />, color: '#6366f1' },
    { type: 'fileModifierNode', label: '자동 완성', icon: <FileCode size={16} />, color: '#f43f5e' },
    { type: 'templateAnalyzerNode', label: '템플릿 분석', icon: <FileCode size={16} />, color: '#8b5cf6' },
    { type: 'loopNode', label: '반복 (Loop)', icon: <Repeat size={16} />, color: '#ca8a04' },
    { type: 'breakNode', label: '반복 종료', icon: <LogOut size={16} style={{transform: 'rotate(180deg)'}}/>, color: '#dc2626' },
    { type: 'dynamicInputNode', label: '동적 입력', icon: <Keyboard size={16} />, color: '#d946ef' },
    { type: 'webCrawlerNode', label: '웹 크롤러', icon: <Globe size={16} />, color: '#0ea5e9' },
    { type: 'emailNode', label: '이메일 전송', icon: <Mail size={16} />, color: '#f43f5e' },
    { type: 'kakaoNode', label: '카카오 알림톡', icon: <MessageCircle size={16} />, color: '#facc15' },
    { type: 'delayNode', label: 'Delay (대기)', icon: <Clock size={16} />, color: '#3b82f6' },
    { type: 'jsonParserNode', label: 'JSON 파서', icon: <Braces size={16} />, color: '#eab308' },
    { type: 'mergeNode', label: 'Merge (병합)', icon: <Merge size={16} />, color: '#ec4899' },
    { type: 'httpRequestNode', label: 'HTTP Request', icon: <ArrowRightLeft size={16} />, color: '#0ea5e9' },
    { type: 'databaseNode', label: '데이터베이스', icon: <Database size={16} />, color: '#059669' },
    { type: 'humanApprovalNode', label: '사용자 승인 (대기)', icon: <UserCheck size={16} />, color: '#f43f5e' },
  ];

  const filteredNodes = nodeTypes.filter(n => n.label.toLowerCase().includes(searchTerm.toLowerCase()));

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
        {filteredNodes.map((node) => (
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
        ))}
      </div>
    </aside>
  );
};

export default Sidebar;
