import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { ArrowUpRight, Box, History, Plus, RefreshCw, Search, Trash2, X } from 'lucide-react';
import { customConfirm } from './CustomConfirm';
import { useAuth } from './AuthContext';
import './ChatSidebar.css';

function utcDate(value) {
  if (!value) return null;
  return new Date(value.endsWith?.('Z') ? value : `${value}Z`);
}

function relativeTime(value) {
  const date = utcDate(value);
  if (!date || Number.isNaN(date.getTime())) return '';
  const diff = Date.now() - date.getTime();
  if (diff < 3600000) return `${Math.max(1, Math.floor(diff / 60000))}분 전`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}시간 전`;
  return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
}

function groupLabel(value) {
  const date = utcDate(value);
  if (!date) return '이전 대화';
  const today = new Date();
  const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const days = Math.floor((startToday - startDate) / 86400000);
  if (days <= 0) return '오늘';
  if (days < 7) return '최근 7일';
  if (days < 30) return '최근 30일';
  return '이전 대화';
}

function sessionPreview(session) {
  const messages = Array.isArray(session.messages) ? session.messages : [];
  const last = [...messages].reverse().find((message) => message?.content);
  return last?.content?.replace(/\s+/g, ' ').trim() || '대화 내용을 확인해보세요.';
}

const ChatSidebar = ({ onSelectSession, currentSessionId, onSessionDeleted, onStartNewChat }) => {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [error, setError] = useState(null);

  const fetchSessions = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get('/api/chat/sessions', {
        headers: { Authorization: `Bearer ${token}` },
      });
      setSessions(response.data.sessions || []);
    } catch (requestError) {
      console.error('Failed to load chat sessions', requestError);
      setError('대화 기록을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchSessions(); }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  const groupedSessions = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const filtered = normalized ? sessions.filter((session) => (
      `${session.title || ''} ${sessionPreview(session)}`.toLowerCase().includes(normalized)
    )) : sessions;
    return filtered.reduce((groups, session) => {
      const label = groupLabel(session.updated_at);
      const group = groups.find((item) => item.label === label);
      if (group) group.sessions.push(session);
      else groups.push({ label, sessions: [session] });
      return groups;
    }, []);
  }, [query, sessions]);

  const selectSession = (session) => {
    if (onSelectSession) onSelectSession(session);
    else navigate('/', { state: { session } });
  };

  const startNewChat = () => {
    if (onStartNewChat) onStartNewChat();
    else navigate('/', { state: { newChat: true } });
  };

  const handleDeleteSession = async (sessionId) => {
    if (!(await customConfirm('이 대화 기록을 삭제할까요?'))) return;
    try {
      await axios.delete(`/api/chat/sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setSessions((current) => current.filter((session) => session.id !== sessionId));
      if (String(currentSessionId) === String(sessionId)) onSessionDeleted?.(sessionId);
    } catch (requestError) {
      console.error('Failed to delete session:', requestError);
      setError('대화 기록을 삭제하지 못했습니다.');
    }
  };

  return (
    <div className="chat-sidebar-container">
      <header className="chat-sidebar-header">
        <div><span className="chat-history-kicker">HISTORY</span><h2>대화 기록 <em>{sessions.length}</em></h2></div>
        <div className="chat-sidebar-actions">
          <button type="button" onClick={fetchSessions} title="대화 기록 새로고침" aria-label="대화 기록 새로고침" disabled={loading}><RefreshCw size={14} className={loading ? 'spin' : ''} /></button>
          <button type="button" className="new" onClick={startNewChat}><Plus size={14} /> 새 대화</button>
        </div>
      </header>

      <label className="chat-session-search">
        <Search size={14} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="대화 검색" />
        {query && <button type="button" onClick={() => setQuery('')} aria-label="검색어 지우기"><X size={13} /></button>}
      </label>

      {error && <p className="chat-session-error" role="alert">{error}</p>}

      <div className="chat-sidebar-content">
        {loading ? (
          <div className="chat-session-skeleton" aria-label="대화 기록을 불러오는 중">{[0, 1, 2, 3].map((item) => <span key={item} />)}</div>
        ) : groupedSessions.length === 0 ? (
          <div className="chat-session-empty">
            <History size={20} />
            <strong>{query ? '검색 결과가 없어요.' : '아직 대화 기록이 없어요.'}</strong>
            <span>{query ? '다른 제목이나 내용으로 찾아보세요.' : '홈에서 첫 자동화를 이야기해보세요.'}</span>
            {!query && <button type="button" onClick={startNewChat}><Plus size={13} /> 새 대화 시작</button>}
          </div>
        ) : groupedSessions.map((group) => (
          <section key={group.label} className="chat-session-group">
            <h3>{group.label}</h3>
            <div className="chat-session-list">
              {group.sessions.map((session) => {
                const active = String(currentSessionId) === String(session.id);
                return (
                  <article key={session.id} className={`chat-session-item${active ? ' active' : ''}`}>
                    <button type="button" className="session-select" onClick={() => selectSession(session)} aria-current={active ? 'true' : undefined}>
                      <span className="session-icon"><History size={13} /></span>
                      <span className="session-copy">
                        <span className="session-title-row"><strong title={session.title}>{session.title || '제목 없는 대화'}</strong><time>{relativeTime(session.updated_at)}</time></span>
                        <span className="session-preview">{sessionPreview(session)}</span>
                      </span>
                    </button>
                    <div className="session-actions">
                      {session.is_existing_project && <button type="button" className="btn-go-project" onClick={() => navigate(`/editor/${session.project_id}`)} title="연결된 워크플로우 열기"><Box size={12} /><ArrowUpRight size={11} /></button>}
                      <button type="button" className="btn-delete-session" onClick={() => handleDeleteSession(session.id)} title="대화 기록 삭제"><Trash2 size={12} /></button>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
};

export default ChatSidebar;
