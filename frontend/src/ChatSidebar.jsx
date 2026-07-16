import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { MessageSquare, ArrowRight, Clock, Box, RefreshCw, Trash2 } from 'lucide-react';
import './ChatSidebar.css';

const ChatSidebar = ({ isOpen, onClose, onExpand, onSelectSession }) => {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    if (isOpen) {
      fetchSessions();
    }
  }, [isOpen]);

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/chat/sessions', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      setSessions(res.data.sessions || []);
    } catch (error) {
      console.error("Failed to load chat sessions", error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    if (!window.confirm("이 대화 기록을 삭제하시겠습니까?")) return;
    try {
      await axios.delete(`/api/chat/sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      fetchSessions();
    } catch (error) {
      console.error("Failed to delete session", error);
      alert("삭제에 실패했습니다.");
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    const utcDateString = dateString.endsWith('Z') ? dateString : dateString + 'Z';
    const date = new Date(utcDateString);
    return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    if (!window.confirm('이 대화 기록을 정말 삭제하시겠습니까?')) {
      return;
    }
    
    try {
      await axios.delete(`/api/chat/session/${sessionId}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      setSessions(prev => prev.filter(s => s.id !== sessionId));
    } catch (error) {
      console.error("Failed to delete session", error);
      alert('삭제에 실패했습니다.');
    }
  };


  return (
    <div 
      className={`chat-sidebar-container ${isOpen ? 'open' : ''}`}
      onClick={(e) => {
        if (!isOpen && onExpand) {
          onExpand();
        }
      }}
    >
      <div className="chat-sidebar-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <MessageSquare size={18} color="#a78bfa" />
          <h2 style={{ fontSize: '1.1rem', margin: 0, color: 'var(--text-color)' }}>대화 기록</h2>
        </div>
        <button className="btn-refresh" onClick={fetchSessions} title="새로고침">
          <RefreshCw size={14} className={loading ? "spin" : ""} />
        </button>
      </div>
      
      <div className="chat-sidebar-content">
        {loading ? (
          <div style={{ padding: '20px', textAlign: 'center', color: '#666' }}>로딩 중...</div>
        ) : sessions.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', color: '#666' }}>대화 기록이 없습니다.</div>
        ) : (
          <div className="chat-session-list">
            {sessions.map(session => (
              <div 
                key={session.id} 
                className="chat-session-item"
                onClick={() => {
                  if (onSelectSession) {
                    onSelectSession(session);
                  } else {
                    if (session.is_existing_project) {
                      navigate(`/editor/${session.project_id}`);
                    } else {
                      navigate(`/`);
                    }
                  }
                }}
                style={{ cursor: 'pointer' }}
              >
                <div className="session-header">
                  <span className="session-title">{session.title}</span>
                  <span className="session-date"><Clock size={12}/> {formatDate(session.updated_at)}</span>
                </div>
                <div className="session-footer">
                  <div className="session-meta">
                    <MessageSquare size={12}/> 메시지 {session.messages?.length || 0}개
                    {session.is_existing_project && (
                      <span className="project-badge"><Box size={12}/> 연결됨</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: '4px' }}>
                    <button 
                      className="btn-delete-session"
                      onClick={(e) => handleDeleteSession(e, session.id)}
                      title="대화 기록 삭제"
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--text-muted)',
                        cursor: 'pointer',
                        padding: '4px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        borderRadius: '4px',
                        transition: 'background 0.2s, color 0.2s'
                      }}
                      onMouseOver={(e) => { e.currentTarget.style.color = '#ef4444'; e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)'; }}
                      onMouseOut={(e) => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.background = 'transparent'; }}
                    >
                      <Trash2 size={14} />
                    </button>
                    {session.is_existing_project && (
                      <button 
                        className="btn-go-project"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/editor/${session.project_id}`);
                        }}
                        title="해당 프로젝트 에디터로 이동"
                      >
                        에디터 열기 <ArrowRight size={14} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatSidebar;
