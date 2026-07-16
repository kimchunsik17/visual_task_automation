import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import axios from 'axios';
import { Plus, LayoutGrid, Sparkles, Wand2, ArrowRight, Zap, Bot, LibraryBig, Key, BarChart } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import MainSidebar from '../MainSidebar';
import './MainPage.css';

function MainPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, token } = useAuth();
  const [autoPrompt, setAutoPrompt] = useState('');
  const [complexityLevel, setComplexityLevel] = useState('low');

  const [isAutoGenerating, setIsAutoGenerating] = useState(false);
  const [messages, setMessages] = useState([]);
  const messagesEndRef = useRef(null);
  const draftIdRef = useRef(`draft-${Date.now()}`);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isAutoGenerating]);

  useEffect(() => {
    if (location.state?.session) {
      handleSelectSession(location.state.session);
      window.history.replaceState({}, document.title);
    } else if (location.state?.newChat) {
      setMessages([]);
      draftIdRef.current = `draft-${Date.now()}`;
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

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
        setMessages(prev => [...prev, { role: 'ai', content: reply, graph_data, prompt: userMessage }]);
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
    // Load messages into MainPage regardless of whether it's an existing project or draft
    draftIdRef.current = session.project_id;
    setMessages(session.messages || []);
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
    {
      icon: <Key size={28} color="#f59e0b" />,
      title: 'API 센터',
      desc: '각종 외부 서비스의 API 키를 통합 관리합니다.',
      action: () => navigate('/apicenter'),
      color: '#f59e0b',
    },
    {
      icon: <BarChart size={28} color="#10b981" />,
      title: '통계',
      desc: '토큰 사용량 및 앱 실행 통계를 확인합니다.',
      action: () => navigate('/statistics'),
      color: '#10b981',
    },
  ];

  const hints = [
    '기술 뉴스 요약해서 이메일로 보내줘',
    '경쟁사 웹사이트 변경사항 모니터링해 줘',
    '매일 날씨 정보를 슬랙으로 알려줘',
  ];

  const renderInputBox = () => (
    <div className="auto-gen-container-minimal" style={{ marginBottom: '0.5rem', width: '100%' }}>
      <div className="auto-gen-input-wrapper-minimal">
        <textarea
          className="auto-gen-input-minimal"
          value={autoPrompt}
          onChange={(e) => setAutoPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="메시지를 입력하세요..."
          rows={1}
          style={{ 
            resize: 'none', 
            overflow: 'hidden', 
            minHeight: '24px', 
            maxHeight: '200px',
            width: '100%'
          }}
          onInput={(e) => {
            e.target.style.height = 'auto';
            e.target.style.height = (e.target.scrollHeight) + 'px';
          }}
        />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.5rem' }}>
        <button style={{ 
          background: 'transparent', 
          border: 'none', 
          color: 'var(--text-muted)', 
          cursor: 'pointer', 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          padding: '0.2rem'
        }}
        onMouseOver={(e) => e.currentTarget.style.color = 'var(--text-color)'}
        onMouseOut={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
        >
          <Plus size={22} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginRight: '0.25rem', fontWeight: 500 }}>모델 설정:</span>
            {['low', 'medium', 'high'].map(level => (
              <label key={level} style={{
                fontSize: '0.75rem',
                color: complexityLevel === level ? '#fff' : 'var(--text-muted)',
                background: complexityLevel === level ? 'var(--primary-color)' : 'transparent',
                padding: '0.2rem 0.5rem',
                borderRadius: '6px',
                cursor: 'pointer',
                transition: 'all 0.2s',
                fontWeight: complexityLevel === level ? 600 : 400
              }}>
                <input 
                  type="radio" 
                  name="main_complexity" 
                  value={level} 
                  checked={complexityLevel === level} 
                  onChange={() => setComplexityLevel(level)} 
                  style={{ display: 'none' }} 
                />
                {level === 'low' ? '빠름' : level === 'medium' ? '기본' : '정밀'}
              </label>
            ))}
          </div>
          
          <button
            className="btn-generate-minimal"
            onClick={handleAutoGenerate}
            disabled={isAutoGenerating || !autoPrompt.trim()}
          >
            <ArrowRight size={18} />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="main-page-layout" style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <MainSidebar 
        isCollapsed={false}
        onSelectSession={handleSelectSession}
      />

      <div className="main-page-content" style={{ flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--bg-color)', position: 'relative' }}>
        
        {messages.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', width: '100%', padding: '2rem' }}>
            <div style={{ width: '100%', maxWidth: '768px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              
              <div style={{ marginBottom: '2.5rem', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <h1 style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '2.5rem', fontWeight: 500, color: 'var(--text-color)', marginBottom: '0.5rem', letterSpacing: '-0.02em' }}>
                  <Sparkles color="#f59e0b" size={32} /> 무엇을 함께 생각해볼까요?
                </h1>
                <p style={{ color: 'var(--text-muted)', fontSize: '1.1rem' }}>
                  {user ? `${user.name.split(' ')[0]}님, ` : ''}오늘 어떤 도움을 드릴까요?
                </p>
              </div>

              {renderInputBox()}
              
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'center', marginTop: '0.5rem' }}>
                {quickActions.map((qa, i) => (
                  <button key={`qa-${i}`} onClick={qa.action} style={{ 
                    display: 'flex', alignItems: 'center', gap: '0.4rem', 
                    background: 'transparent', border: '1px solid var(--border-color)', 
                    color: 'var(--text-muted)', padding: '0.4rem 0.8rem', 
                    borderRadius: '16px', fontSize: '0.85rem', cursor: 'pointer', transition: 'all 0.2s' 
                  }}
                  onMouseOver={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; e.currentTarget.style.color = 'var(--text-color)'; }}
                  onMouseOut={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-muted)'; }}
                  >
                     {React.cloneElement(qa.icon, { size: 14 })} {qa.title}
                  </button>
                ))}
                {hints.map((hint, i) => (
                  <button key={`hint-${i}`} onClick={() => setAutoPrompt(hint)} style={{ 
                    display: 'flex', alignItems: 'center', gap: '0.4rem', 
                    background: 'transparent', border: '1px solid var(--border-color)', 
                    color: 'var(--text-muted)', padding: '0.4rem 0.8rem', 
                    borderRadius: '16px', fontSize: '0.85rem', cursor: 'pointer', transition: 'all 0.2s' 
                  }}
                  onMouseOver={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; e.currentTarget.style.color = 'var(--text-color)'; }}
                  onMouseOut={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-muted)'; }}
                  >
                    <Sparkles size={14} /> {hint.slice(0, 10)}...
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%', overflowY: 'auto' }}>
              <div style={{ width: '100%', maxWidth: '768px', padding: '2rem 2rem 2rem 2rem', display: 'flex', flexDirection: 'column' }}>
                <div className="chat-history" style={{ paddingBottom: '2rem' }}>
                  {messages.map((msg, idx) => (
                    <div key={idx} className={`chat-message ${msg.role}`}>
                      <div className={`chat-avatar ${msg.role === 'ai' ? 'ai-avatar' : ''}`} style={msg.role !== 'ai' ? { background: '#4b5563', color: '#fff' } : {}}>
                        {msg.role === 'ai' ? <Bot size={18} /> : (user?.name?.[0] || 'U')}
                      </div>
                      <div className="chat-bubble">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                        {msg.graph_data?.nodes?.length > 0 && (
                          <div style={{ marginTop: '1rem' }}>
                            <button 
                              onClick={() => navigate('/editor', { state: { initialGraph: msg.graph_data, prompt: msg.prompt || '' } })}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.5rem',
                                padding: '0.6rem 1.2rem',
                                background: 'var(--primary-color)',
                                color: '#fff',
                                border: 'none',
                                borderRadius: '8px',
                                fontSize: '0.9rem',
                                cursor: 'pointer',
                                fontWeight: 600,
                                boxShadow: '0 4px 12px rgba(99,102,241,0.3)',
                                transition: 'all 0.2s'
                              }}
                            >
                              에디터로 이동하기 <ArrowRight size={16} />
                            </button>
                          </div>
                        )}
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
                  <div ref={messagesEndRef} />
                </div>
              </div>
            </div>

            <div style={{ width: '100%', display: 'flex', justifyContent: 'center', padding: '0 2rem 2rem 2rem' }}>
              <div style={{ width: '100%', maxWidth: '768px' }}>
                {renderInputBox()}
                <div style={{ textAlign: 'center', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Auto Flow는 AI이며 실수할 수 있습니다. 응답을 다시 한번 확인해 주세요.
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default MainPage;
