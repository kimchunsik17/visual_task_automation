import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import axios from 'axios';
import { Plus, LayoutGrid, Sparkles, Wand2, ArrowRight, Zap, Bot, LibraryBig } from 'lucide-react';
import MainSidebar from '../MainSidebar';
import './MainPage.css';

function MainPage() {
  const navigate = useNavigate();
  const { user, token } = useAuth();
  const [autoPrompt, setAutoPrompt] = useState('');
  const [complexityLevel, setComplexityLevel] = useState('low');

  const [isAutoGenerating, setIsAutoGenerating] = useState(false);
  const [messages, setMessages] = useState([]);
  const draftIdRef = useRef(`draft-${Date.now()}`);

  const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return token ? { headers: { Authorization: `Bearer ${token}` } } : {};
  };

  const handleAutoGenerate = async () => {
    if (!autoPrompt.trim()) return;

    const userMessage = autoPrompt.trim();
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setAutoPrompt('');
    setIsAutoGenerating(true);

    try {
      const payload = {
        project_id: draftIdRef.current,
        message: userMessage,
        graph_data: { nodes: [], edges: [] },
        complexity_level: complexityLevel,
      };
      const authHeaders = token ? { headers: { Authorization: `Bearer ${token}` } } : {};
      const res = await axios.post('/api/chat', payload, authHeaders);
      const { reply, graph_data } = res.data;

      if (reply) {
        setMessages(prev => [...prev, { role: 'ai', content: reply }]);
      }

      if (graph_data?.nodes?.length > 0) {
        navigate('/editor', { state: { initialGraph: graph_data, prompt: userMessage } });
      }
    } catch (error) {
      console.error(error);
      setMessages(prev => [
        ...prev,
        { role: 'ai', content: '오류가 발생했습니다: ' + (error.response?.data?.detail || error.message) }
      ]);
    } finally {
      setIsAutoGenerating(false);
    }
  };

  const handleSelectSession = (session) => {
    if (session.is_existing_project) {
      navigate(`/editor/${session.project_id}`);
    } else {
      // Draft session: load messages into MainPage and use its draftId
      draftIdRef.current = session.project_id;
      setMessages(session.messages || []);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAutoGenerate();
    }
  };

  const quickActions = [
    {
      icon: <Plus size={28} color="#60a5fa" />,
      title: '새 워크플로우 만들기',
      desc: '빈 캔버스에서 직접 노드를 조합해 워크플로우를 설계합니다.',
      action: () => navigate('/editor'),
      color: '#60a5fa',
    },
    {
      icon: <LayoutGrid size={28} color="#c084fc" />,
      title: '내 워크플로우',
      desc: '저장된 워크플로우를 관리하고 앱으로 실행합니다.',
      action: () => navigate('/workflows'),
      color: '#c084fc',
    },
    {
      icon: <LibraryBig size={28} color="#34d399" />,
      title: '커뮤니티 템플릿',
      desc: '다른 사용자가 공개한 워크플로우를 불러와 바로 사용합니다.',
      action: () => navigate('/templates'),
      color: '#34d399',
    },
    {
      icon: <Bot size={28} color="#f472b6" />,
      title: '봇 관리',
      desc: '디스코드·카카오 등에 연결된 봇을 관리합니다.',
      action: () => navigate('/bots'),
      color: '#f472b6',
    },
  ];

  const hints = [
    '기술 뉴스 요약해서 이메일로 보내줘',
    '경쟁사 웹사이트 변경사항 모니터링해 줘',
    '매일 날씨 정보를 슬랙으로 알려줘',
  ];

  return (
    <div className="main-page-layout" style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <MainSidebar 
        isCollapsed={false}
        onSelectSession={handleSelectSession}
      />

      <div className="main-page-content" style={{ flex: 1, display: 'flex', flexDirection: 'row', overflowY: 'auto', background: 'var(--bg-color)' }}>
        
        {/* 중앙: 대화 및 메인 기능 (가운데 정렬) */}
        <div style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
          <div style={{ width: '100%', maxWidth: '900px', padding: '2.5rem 3rem', display: 'flex', flexDirection: 'column' }}>
          {messages.length === 0 && (
            <div style={{ marginBottom: '2.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
                <Wand2 size={28} color="#60a5fa" />
                <span style={{ fontSize: '0.9rem', fontWeight: 600, color: '#60a5fa', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Auto Flow</span>
              </div>
              <h1 style={{ margin: '0 0 0.75rem 0', fontSize: '2.4rem', fontWeight: 800, lineHeight: 1.2, color: 'var(--text-color)' }}>
                안녕하세요{user ? `, ${user.name.split(' ')[0]}님` : ''}! 👋<br />
                <span style={{ background: 'linear-gradient(135deg, #60a5fa, #a78bfa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                  무엇을 자동화할까요?
                </span>
              </h1>
              <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '1.05rem', lineHeight: 1.6 }}>
                노드를 연결하여 반복 업무를 워크플로우로 만들고, 한 번의 클릭으로 실행하세요.
              </p>
            </div>
          )}

          {/* 채팅 내역 렌더링 */}
          {(messages.length > 0 || isAutoGenerating) && (
            <div className="chat-history" style={{ marginBottom: '2rem' }}>
              {messages.map((msg, idx) => (
                <div key={idx} className={`chat-message ${msg.role}`}>
                  <div className={`chat-avatar ${msg.role === 'ai' ? 'ai-avatar' : ''}`} style={msg.role !== 'ai' ? { background: '#4b5563', color: '#fff' } : {}}>
                    {msg.role === 'ai' ? <Bot size={18} /> : (user?.name?.[0] || 'U')}
                  </div>
                  <div className="chat-bubble">
                    {msg.content}
                  </div>
                </div>
              ))}
              {isAutoGenerating && (
                <div className="chat-message ai">
                  <div className="chat-avatar ai-avatar">
                    <Bot size={18} />
                  </div>
                  <div className="typing-indicator">
                    <div className="typing-dot"></div>
                    <div className="typing-dot"></div>
                    <div className="typing-dot"></div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* AI 입력창 */}
          <div className="auto-gen-container" style={{ marginBottom: '2.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <Sparkles size={16} color="#a78bfa" />
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#a78bfa' }}>AI 워크플로우 생성</span>
              <span style={{ fontSize: '0.7rem', padding: '0.15rem 0.5rem', background: 'rgba(167,139,250,0.15)', color: '#a78bfa', border: '1px solid rgba(167,139,250,0.3)', borderRadius: '50px' }}>구현 중</span>
              
              <div style={{ display: 'flex', gap: '0.5rem', marginLeft: 'auto' }}>
                {['low', 'medium', 'high'].map(level => (
                  <label key={level} style={{
                    fontSize: '0.75rem',
                    color: complexityLevel === level ? '#fff' : 'var(--text-muted)',
                    background: complexityLevel === level ? 'var(--primary-color)' : 'transparent',
                    padding: '0.2rem 0.6rem',
                    borderRadius: '12px',
                    cursor: 'pointer',
                    border: `1px solid ${complexityLevel === level ? 'var(--primary-color)' : 'var(--border-color)'}`,
                    transition: 'all 0.2s'
                  }}>
                    <input 
                      type="radio" 
                      name="main_complexity" 
                      value={level} 
                      checked={complexityLevel === level} 
                      onChange={() => setComplexityLevel(level)} 
                      style={{ display: 'none' }} 
                    />
                    {level === 'low' ? '빠름' : level === 'medium' ? '확장' : '정밀'}
                  </label>
                ))}
              </div>
            </div>
            <textarea
              className="auto-gen-input"
              value={autoPrompt}
              onChange={(e) => setAutoPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="예: 매일 아침 8시에 해커뉴스 상위 5개 기사를 요약해서 이메일로 보내줘"
              style={{ minHeight: '60px' }}
            />
            <div className="auto-gen-actions">
              <div className="gen-hints">
                {hints.map((hint, i) => (
                  <span key={i} className="hint-chip" onClick={() => setAutoPrompt(hint)}>{hint.slice(0, 10)}...</span>
                ))}
              </div>
              <button
                className="btn-generate"
                onClick={handleAutoGenerate}
                disabled={isAutoGenerating || !autoPrompt.trim()}
              >
                <Sparkles size={18} /> {isAutoGenerating ? '생성 중...' : '워크플로우 생성'}
              </button>
            </div>
          </div>
        </div>
        </div>
        {/* 우측 사이드바: 빠른 시작 */}
        <div style={{ 
          width: '280px', 
          borderLeft: '1px solid var(--border-color)', 
          padding: '1.5rem',
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--card-bg)'
        }}>
          <div style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Zap size={18} color="#f59e0b" />
            <span style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-color)' }}>빠른 시작</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {quickActions.map((qa, i) => (
              <button
                key={i}
                onClick={qa.action}
                style={{
                  background: 'var(--bg-color)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '10px',
                  padding: '0.75rem 1rem',
                  textAlign: 'left',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.borderColor = qa.color;
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = `0 4px 12px ${qa.color}20`;
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border-color)';
                  e.currentTarget.style.transform = 'none';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                <div style={{ padding: '0.4rem', background: `${qa.color}15`, borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  {React.cloneElement(qa.icon, { size: 20 })}
                </div>
                <div style={{ fontWeight: 600, color: 'var(--text-color)', fontSize: '0.9rem' }}>
                  {qa.title}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default MainPage;
