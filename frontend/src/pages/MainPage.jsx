import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { Plus, LayoutGrid, Sparkles, Wand2, ArrowRight, Zap, Bot, LibraryBig } from 'lucide-react';
import axios from 'axios';
import MainSidebar from '../MainSidebar';
import './MainPage.css';

function MainPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [autoPrompt, setAutoPrompt] = useState('');

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
      };
      const res = await axios.post('/api/chat', payload, getAuthHeaders());
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
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start', overflowY: 'auto' }}>
        {/* Hero */}
        <div style={{ width: '100%', maxWidth: '900px', margin: '0 auto', padding: '2.5rem 2rem 0' }}>
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

          {/* AI 입력창 */}
          <div className="auto-gen-container" style={{ marginBottom: '2.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <Sparkles size={16} color="#a78bfa" />
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#a78bfa' }}>AI 워크플로우 생성</span>
              <span style={{ fontSize: '0.7rem', padding: '0.15rem 0.5rem', background: 'rgba(167,139,250,0.15)', color: '#a78bfa', border: '1px solid rgba(167,139,250,0.3)', borderRadius: '50px' }}>구현 중</span>
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

          {/* 빠른 액션 카드 */}
          <div style={{ marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Zap size={16} color="var(--text-muted)" />
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>빠른 시작</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '3rem' }}>
            {quickActions.map((qa, i) => (
              <button
                key={i}
                onClick={qa.action}
                style={{
                  background: 'var(--card-bg)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '14px',
                  padding: '1.5rem',
                  textAlign: 'left',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.75rem',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.borderColor = qa.color;
                  e.currentTarget.style.transform = 'translateY(-3px)';
                  e.currentTarget.style.boxShadow = `0 8px 20px ${qa.color}20`;
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border-color)';
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: `${qa.color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  {qa.icon}
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.3rem' }}>
                    <span style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-color)' }}>{qa.title}</span>
                    <ArrowRight size={14} color="var(--text-muted)" />
                  </div>
                  <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>{qa.desc}</p>
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
