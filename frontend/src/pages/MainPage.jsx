import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import axios from 'axios';
import { Plus, LayoutGrid, Sparkles, Wand2, ArrowRight, Zap, Bot, LibraryBig, Key, BarChart, Check, ChevronDown, Paperclip, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import MainSidebar from '../MainSidebar';
import logoImg from '../logo.png';
import './MainPage.css';

function MainPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, token } = useAuth();
  const [autoPrompt, setAutoPrompt] = useState('');
  const [complexityLevel, setComplexityLevel] = useState('medium'); // Set medium as default like screenshot
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);
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
    if (!autoPrompt.trim() && selectedFiles.length === 0) return;

    const userMessage = autoPrompt.trim();
    setMessages(prev => [...prev, { role: 'user', content: userMessage || '문서를 첨부했습니다.' }]);
    setAutoPrompt('');
    setIsAutoGenerating(true);

    try {
      if (selectedFiles.length > 0) {
        setIsUploading(true);
        const formData = new FormData();
        formData.append('project_id', draftIdRef.current);
        selectedFiles.forEach(f => formData.append('files', f));
        
        const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};
        await axios.post('/api/chat/upload_context', formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
            ...authHeaders
          }
        });
        setSelectedFiles([]);
        setIsUploading(false);
      }
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

  const hints = [
    '뉴스 요약 이메일 전송 루틴 만들기',
    '네이버 스토어와 카카오톡 알림 연동 ',
    '디스코드 챗봇에 llm 연결하기',
  ];

  const renderInputBox = () => (
    <div className="auto-gen-container-minimal" style={{ marginBottom: '0.5rem', width: '100%' }}>
      {selectedFiles.length > 0 && (
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', padding: '0.5rem 1rem 0' }}>
          {selectedFiles.map((f, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', background: 'rgba(255,255,255,0.1)', padding: '0.3rem 0.6rem', borderRadius: '16px', fontSize: '0.85rem', color: '#fff' }}>
              <Paperclip size={12} />
              <span style={{ maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
              <button onClick={() => setSelectedFiles(selectedFiles.filter((_, idx) => idx !== i))} style={{ background: 'none', border: 'none', color: '#ccc', cursor: 'pointer', padding: 0, display: 'flex', marginLeft: '0.2rem' }}><X size={14} /></button>
            </div>
          ))}
        </div>
      )}
      <div className="auto-gen-input-wrapper-minimal">
        <textarea
          className="auto-gen-input-minimal"
          value={autoPrompt}
          onChange={(e) => setAutoPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="메시지를 입력하거나 문서를 첨부하세요..."
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
        <input 
          type="file" 
          multiple 
          ref={fileInputRef} 
          style={{ display: 'none' }} 
          accept=".pdf,.doc,.docx,.txt"
          onChange={(e) => setSelectedFiles(prev => [...prev, ...Array.from(e.target.files)])}
        />
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
          onClick={() => fileInputRef.current?.click()}
          onMouseOver={(e) => e.currentTarget.style.color = 'var(--text-color)'}
          onMouseOut={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
        >
          <Paperclip size={20} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }} ref={dropdownRef}>
            <button
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                fontSize: '0.9rem',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.25rem',
                padding: '0.2rem 0.5rem',
                fontWeight: 500
              }}
            >
              {complexityLevel === 'low' ? '빠름' : complexityLevel === 'medium' ? '기본' : '정밀'}
              <ChevronDown size={14} />
            </button>

            {isDropdownOpen && (
              <div style={{
                position: 'absolute',
                bottom: '100%',
                right: 0,
                marginBottom: '0.5rem',
                background: '#1e1e1e',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '12px',
                padding: '0.5rem',
                width: '280px',
                boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
                zIndex: 10
              }}>
                {[
                  { id: 'low', title: '빠름', desc: '가장 빠르게 workflow를 생성' },
                  { id: 'medium', title: '기본', desc: '상세하고 정확한 workflow를 생성' },
                  { id: 'high', title: '정밀', desc: '전문가용 workflow를 생성' }
                ].map((opt, index) => (
                  <React.Fragment key={opt.id}>
                    <div
                      onClick={() => {
                        setComplexityLevel(opt.id);
                        setIsDropdownOpen(false);
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        padding: '0.75rem 1rem',
                        cursor: 'pointer',
                        borderRadius: '8px',
                        background: complexityLevel === opt.id ? 'rgba(255,255,255,0.05)' : 'transparent',
                        transition: 'background 0.2s'
                      }}
                      onMouseOver={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.08)'}
                      onMouseOut={(e) => e.currentTarget.style.background = complexityLevel === opt.id ? 'rgba(255,255,255,0.05)' : 'transparent'}
                    >
                      <div style={{ width: '24px', flexShrink: 0, display: 'flex', justifyContent: 'center', marginTop: '2px' }}>
                        {complexityLevel === opt.id && <Check size={16} color="#e2e8f0" />}
                      </div>
                      <div>
                        <div style={{ color: '#e2e8f0', fontSize: '0.95rem', fontWeight: 500, marginBottom: '0.1rem' }}>{opt.title}</div>
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{opt.desc}</div>
                      </div>
                    </div>
                  </React.Fragment>
                ))}
              </div>
            )}
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
                <h1 style={{ fontFamily: "'Noto Sans KR', sans-serif", display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '2.5rem', fontWeight: 500, color: 'var(--text-color)', marginBottom: '0.5rem', letterSpacing: '-0.02em' }}>
                  <img src={logoImg} alt="Logo" style={{ width: '65px', height: '65px', objectFit: 'contain' }} />
                  쉽고 빠른 업무 자동화 시작하기
                </h1>
                <p style={{ fontFamily: "'Noto Sans KR', sans-serif", color: 'var(--text-muted)', fontSize: '1.1rem' }}>
                  {user ? `${user.name.split(' ')[0]}님, ` : ''}오늘은 어떤 Workflow를 자동화해볼까요?
                </p>
              </div>

              {renderInputBox()}

              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'center', marginTop: '0.5rem' }}>

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
                    {hint}
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
                      <div className={`chat-avatar ${msg.role === 'ai' ? 'ai-avatar' : ''}`} style={msg.role !== 'ai' ? { display: 'none' } : {}}>

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
