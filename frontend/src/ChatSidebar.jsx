import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { MessageSquare, ArrowRight, Clock, Box, RefreshCw, Trash2, Plus } from 'lucide-react';
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
      await axios.delete(`/api/chat/sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      // 성공 시 목록 다시 불러오기
      fetchSessions();
      // 만약 현재 열려있는 세션이 삭제되었다면 메인 화면 상태로 돌리기 위해 선택 초기화 콜백 호출 가능
      // (현재는 에러를 방지하기 위해 undefined 변수 참조를 제거함)
    } catch (error) {
      console.error("Failed to delete session:", error);
      alert("삭제에 실패했습니다.");
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
        <div style={{ display: 'flex', gap: '8px' }}>
          <button 
            className="btn-refresh" 
            onClick={() => navigate('/', { state: { newChat: true } })} 
            title="새 채팅 시작"
          >
            <Plus size={16} />
          </button>
          <button className="btn-refresh" onClick={fetchSessions} title="새로고침">
            <RefreshCw size={14} className={loading ? "spin" : ""} />
          </button>
        </div>
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
                    navigate('/', { state: { session } });
                  }
                }}
                style={{ cursor: 'pointer' }}
              >
                <div className="session-header">
                  <MessageSquare size={14} color="var(--text-muted)" style={{ flexShrink: 0 }} />
                  <span className="session-title" title={session.title}>{session.title}</span>
                  {session.is_existing_project && <Box size={12} color="#10b981" title="앱 연동됨" style={{ flexShrink: 0 }} />}
                  
                  <div className="session-actions">
                    {session.is_existing_project && (
                      <button 
                        className="btn-go-project"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/editor/${session.project_id}`);
                        }}
                        title="해당 프로젝트 에디터로 이동"
                      >
                        <ArrowRight size={14} />
                      </button>
                    )}
                    <button 
                      className="btn-delete-session"
                      onClick={(e) => handleDeleteSession(e, session.id)}
                      title="대화 기록 삭제"
                    >
                      <Trash2 size={14} />
                    </button>
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
