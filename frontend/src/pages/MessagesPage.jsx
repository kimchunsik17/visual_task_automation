// 친구 간 1:1 쪽지 (ADR-0022, 우선 백로그 24).
// 연결이 끊기면 Last-Event-ID로 이어 붙이고, UI는 실시간 상태와 읽기 상태를 분리해 보여준다.
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import {
  AlertCircle, ArrowLeft, Loader2, MessageCircle, Plus, Search, Send, Trash2,
  Users, Wifi, WifiOff, X,
} from 'lucide-react';
import MainSidebar from '../MainSidebar';
import EmptyState from '../components/EmptyState';
import { useAuth } from '../AuthContext';
import './MainPage.css';
import './MessagesPage.css';

const auth = (token) => (token ? { headers: { Authorization: `Bearer ${token}` } } : {});

function avatarLetter(handle) {
  return (handle || '?').slice(0, 1).toUpperCase();
}

function dateKey(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

function formatDateDivider(value) {
  const date = new Date(value);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (dateKey(date) === dateKey(today)) return '오늘';
  if (dateKey(date) === dateKey(yesterday)) return '어제';
  return date.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });
}

function formatMessageTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' });
}

function formatConversationTime(conversation) {
  const value = conversation.lastMessageAt || conversation.updatedAt || conversation.createdAt;
  if (!value) return '';
  const date = new Date(value);
  const days = Math.floor((Date.now() - date.getTime()) / 86400000);
  if (days === 0) return formatMessageTime(value);
  if (days === 1) return '어제';
  return date.toLocaleDateString('ko-KR', { month: 'numeric', day: 'numeric' });
}

export default function MessagesPage() {
  const { token } = useAuth();
  const [conversations, setConversations] = useState([]);
  const [active, setActive] = useState(null);
  const [thread, setThread] = useState(null);
  const [draft, setDraft] = useState('');
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  const [openHandle, setOpenHandle] = useState('');
  const [query, setQuery] = useState('');
  const [showNew, setShowNew] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [threadLoading, setThreadLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const lastEventId = useRef(0);
  const bottomRef = useRef(null);

  const loadConversations = useCallback(async () => {
    try {
      const res = await axios.get('/api/messages/conversations', auth(token));
      setConversations(res.data.conversations || []);
    } finally {
      setListLoading(false);
    }
  }, [token]);

  const loadThread = useCallback(async (conversationId) => {
    if (!conversationId) return;
    setThreadLoading(true);
    setError(null);
    try {
      const res = await axios.get(`/api/messages/conversations/${conversationId}`, auth(token));
      setThread(res.data);
      const messages = res.data.messages || [];
      if (messages.length) lastEventId.current = Math.max(lastEventId.current, messages[messages.length - 1].id);
      await axios.post(`/api/messages/conversations/${conversationId}/read`, {}, auth(token));
      loadConversations().catch(() => {});
    } catch (e) {
      setError(e.response?.data?.detail || '대화를 불러오지 못했습니다.');
    } finally {
      setThreadLoading(false);
    }
  }, [token, loadConversations]);

  useEffect(() => {
    setListLoading(true);
    loadConversations().catch(() => setError('대화 목록을 불러오지 못했습니다.'));
  }, [loadConversations]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [thread]);

  // EventSource는 Authorization 헤더를 붙일 수 없어 fetch 스트림을 사용한다.
  useEffect(() => {
    if (!token) return undefined;
    const controller = new AbortController();
    let stopped = false;

    const connect = async () => {
      while (!stopped) {
        try {
          const res = await fetch(`/api/messages/stream?last_event_id=${lastEventId.current}`, {
            headers: { Authorization: `Bearer ${token}`, 'Last-Event-ID': String(lastEventId.current) },
            signal: controller.signal,
          });
          if (!res.ok || !res.body) throw new Error('stream unavailable');
          setConnected(true);
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const frames = buffer.split('\n\n');
            buffer = frames.pop() || '';
            for (const frame of frames) {
              if (!frame.includes('event: message')) continue;
              const idLine = frame.split('\n').find((line) => line.startsWith('id: '));
              const dataLine = frame.split('\n').find((line) => line.startsWith('data: '));
              if (idLine) lastEventId.current = Math.max(lastEventId.current, Number(idLine.slice(4)));
              if (!dataLine) continue;
              const message = JSON.parse(dataLine.slice(6));
              setThread((current) => (current && message.conversationId === active
                ? { ...current, messages: [...current.messages, message] } : current));
              loadConversations().catch(() => {});
            }
          }
        } catch {
          if (stopped) return;
        }
        setConnected(false);
        await new Promise((resolve) => setTimeout(resolve, 3000));
      }
    };
    connect();
    return () => { stopped = true; controller.abort(); };
  }, [token, active, loadConversations]);

  const openWith = async () => {
    const handle = openHandle.trim().replace(/^@/, '');
    if (!handle) return;
    setError(null);
    try {
      const res = await axios.post('/api/messages/conversations', { handle }, auth(token));
      setOpenHandle('');
      setShowNew(false);
      setActive(res.data.conversationId);
      await loadThread(res.data.conversationId);
      loadConversations().catch(() => {});
    } catch (e) {
      setError(e.response?.data?.detail || '대화를 열지 못했습니다.');
    }
  };

  const selectConversation = (conversationId) => {
    setActive(conversationId);
    setThread(null);
    loadThread(conversationId);
  };

  const send = async () => {
    if (!draft.trim() || !active || sending) return;
    const body = draft.trimEnd();
    setDraft('');
    setError(null);
    setSending(true);
    try {
      await axios.post(`/api/messages/conversations/${active}/messages`, { body }, auth(token));
      await loadThread(active);
    } catch (e) {
      setDraft(body);
      setError(e.response?.data?.detail || '보내지 못했습니다.');
    } finally {
      setSending(false);
    }
  };

  const removeForMe = async (messageId) => {
    try {
      await axios.delete(`/api/messages/${messageId}`, auth(token));
      loadThread(active);
    } catch (e) {
      setError(e.response?.data?.detail || '메시지를 삭제하지 못했습니다.');
    }
  };

  const filteredConversations = useMemo(() => {
    const normalized = query.trim().toLowerCase().replace(/^@/, '');
    if (!normalized) return conversations;
    return conversations.filter((item) => (item.other?.handle || '').toLowerCase().includes(normalized)
      || (item.lastMessage || '').toLowerCase().includes(normalized));
  }, [conversations, query]);

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <main className="main-page-content msg-page" style={{ justifyContent: 'flex-start' }}>
        <header className="msg-page-head">
          <div>
            <span className="msg-eyebrow"><MessageCircle size={13} /> DIRECT MESSAGES</span>
            <h1>쪽지</h1>
            <p>친구와 이어서 이야기하고 워크플로우의 맥락을 나눠보세요.</p>
          </div>
          <span className={`msg-live ${connected ? 'on' : ''}`} title={connected ? '실시간 연결됨' : '재연결 중'}>
            {connected ? <Wifi size={13} /> : <WifiOff size={13} />}
            {connected ? '실시간 연결' : '연결 대기'}
          </span>
        </header>

        <div className={`msg-layout${active ? ' has-active' : ''}`}>
          <aside className="msg-list" aria-label="대화 목록">
            <div className="msg-list-head">
              <div><h2>대화</h2><span>{conversations.length}</span></div>
              <button type="button" className="msg-new-toggle" onClick={() => setShowNew((value) => !value)}
                      aria-expanded={showNew} aria-label="새 대화 열기">
                {showNew ? <X size={16} /> : <Plus size={16} />}
              </button>
            </div>

            {showNew && (
              <form className="msg-open" onSubmit={(event) => { event.preventDefault(); openWith(); }}>
                <div><strong>새 대화</strong><span>친구의 핸들을 입력하세요.</span></div>
                <label><span>@</span><input value={openHandle} onChange={(event) => setOpenHandle(event.target.value)} placeholder="handle" autoFocus /></label>
                <button type="submit" disabled={!openHandle.trim()}>대화 열기</button>
                <p><Users size={12} /> 친구끼리만 쪽지를 주고받을 수 있어요.</p>
              </form>
            )}

            <label className="msg-search">
              <Search size={14} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="대화 검색" />
              {query && <button type="button" onClick={() => setQuery('')} aria-label="검색어 지우기"><X size={13} /></button>}
            </label>

            <div className="msg-list-label"><span>최근 대화</span><span>{filteredConversations.length}</span></div>
            <div className="msg-list-scroll">
              {listLoading ? (
                <div className="msg-list-skeleton" aria-label="대화 목록을 불러오는 중">{[0, 1, 2].map((item) => <span key={item} />)}</div>
              ) : filteredConversations.length === 0 ? (
                <div className="msg-list-empty">
                  <MessageCircle size={18} />
                  <strong>{query ? '검색 결과가 없어요.' : '아직 대화가 없어요.'}</strong>
                  <span>{query ? '다른 이름이나 메시지를 검색해보세요.' : '상단 + 버튼으로 첫 대화를 시작하세요.'}</span>
                </div>
              ) : filteredConversations.map((conversation) => {
                const handle = conversation.other?.handle || '알 수 없음';
                return (
                  <button key={conversation.id} type="button"
                          className={`msg-item${active === conversation.id ? ' active' : ''}`}
                          onClick={() => selectConversation(conversation.id)}>
                    <span className="msg-avatar" aria-hidden="true">{avatarLetter(handle)}</span>
                    <span className="msg-item-copy">
                      <span className="msg-item-row"><strong>@{handle}</strong><time>{formatConversationTime(conversation)}</time></span>
                      <span className="msg-item-row"><span className="msg-item-preview">{conversation.lastMessage || '대화를 시작해보세요.'}</span>{conversation.unread > 0 && <span className="msg-badge">{conversation.unread > 99 ? '99+' : conversation.unread}</span>}</span>
                    </span>
                  </button>
                );
              })}
            </div>
            {error && !active && <p className="msg-error msg-list-error" role="alert"><AlertCircle size={13} /> {error}</p>}
          </aside>

          <section className="msg-thread" aria-label="선택한 대화">
            {threadLoading ? (
              <div className="msg-thread-loading"><Loader2 size={21} /> 대화를 불러오는 중</div>
            ) : !thread ? (
              <EmptyState className="msg-thread-empty" illustration="empty-templates" title="대화를 선택하세요"
                          description="친구와 나눈 메시지가 이곳에 시간 순서대로 표시됩니다."
                          action={<button className="btn-primary" onClick={() => setShowNew(true)}><Plus size={14} /> 새 대화</button>} />
            ) : (
              <>
                <div className="msg-thread-head">
                  <button type="button" className="msg-mobile-back" onClick={() => { setActive(null); setThread(null); }} aria-label="대화 목록으로 돌아가기"><ArrowLeft size={17} /></button>
                  <span className="msg-avatar large" aria-hidden="true">{avatarLetter(thread.other?.handle)}</span>
                  <div><strong>@{thread.other?.handle}</strong><span><span className="msg-presence-dot" /> 친구와의 1:1 대화</span></div>
                </div>

                <div className="msg-scroll" aria-live="polite">
                  {(thread.messages || []).length === 0 && (
                    <div className="msg-thread-start"><MessageCircle size={20} /><strong>대화를 시작해보세요.</strong><span>첫 메시지는 짧은 인사여도 충분해요.</span></div>
                  )}
                  {(thread.messages || []).map((message, index) => {
                    const previous = thread.messages[index - 1];
                    const showDivider = !previous || dateKey(previous.createdAt) !== dateKey(message.createdAt);
                    return (
                      <Fragment key={message.id}>
                        {showDivider && <div className="msg-date-divider"><span>{formatDateDivider(message.createdAt)}</span></div>}
                        <div className={`msg-bubble${message.mine ? ' mine' : ''}${message.removed ? ' removed' : ''}`}>
                          <p>{message.body}</p>
                          <div className="msg-meta">
                            <time dateTime={message.createdAt}>{formatMessageTime(message.createdAt)}</time>
                            {!message.removed && (
                              <button type="button" onClick={() => removeForMe(message.id)} title="내 화면에서만 삭제" aria-label="내 화면에서 메시지 삭제">
                                <Trash2 size={11} />
                              </button>
                            )}
                          </div>
                        </div>
                      </Fragment>
                    );
                  })}
                  <div ref={bottomRef} />
                </div>

                {thread.canSend ? (
                  <div className="msg-compose">
                    <div className="msg-compose-box">
                      <textarea value={draft} rows={2} onChange={(event) => setDraft(event.target.value)}
                                onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send(); } }}
                                placeholder={`@${thread.other?.handle}에게 메시지 보내기`} />
                      <span>Shift + Enter로 줄바꿈</span>
                    </div>
                    <button className="btn-primary" type="button" onClick={send} disabled={!draft.trim() || sending} aria-label="메시지 보내기">
                      {sending ? <Loader2 size={16} /> : <Send size={16} />}<span>{sending ? '전송 중' : '보내기'}</span>
                    </button>
                  </div>
                ) : (
                  <p className="msg-readonly"><AlertCircle size={14} /> 지금은 메시지를 보낼 수 없습니다. 지난 대화는 계속 볼 수 있어요.</p>
                )}
              </>
            )}
            {error && active && <p className="msg-error" role="alert"><AlertCircle size={13} /> {error}</p>}
          </section>
        </div>
      </main>
    </div>
  );
}
