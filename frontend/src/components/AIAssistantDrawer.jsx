import { useEffect, useRef } from 'react';
import { Bot, Send, Sparkles, Square, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import AiThinking from './AiThinking';
import './AIAssistantDrawer.css';

function AIAssistantDrawer({
  isOpen,
  title,
  description,
  contextLabel,
  messages,
  input,
  onInputChange,
  onSend,
  onCancel,
  onClose,
  isLoading = false,
  loadingLabel = '요청을 반영하고 있어요',
  sendDisabled = false,
  placeholder = '수정할 내용을 입력하세요...',
  headerMeta,
  controls,
  suggestions = [],
  onSuggestion,
  // 입력란 안에 놓는 대상 핸들(백로그 28 POINT-1). `[{key, label, missing}]`.
  // 없으면 아무것도 그리지 않으므로 App Builder 등 다른 화면은 영향이 없다.
  mentions = [],
  onRemoveMention,
}) {
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    if (isOpen) messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading, isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const timer = window.setTimeout(() => textareaRef.current?.focus(), 220);
    return () => window.clearTimeout(timer);
  }, [isOpen]);

  const handleInput = (event) => {
    onInputChange(event.target.value);
    event.target.style.height = 'auto';
    event.target.style.height = `${Math.min(event.target.scrollHeight, 144)}px`;
  };

  const handleKeyDown = (event) => {
    // 입력이 비었을 때 Backspace 로 마지막 핸들을 지운다(메일 To: 칸과 같은 방식).
    // **한글 조합 중에는 건드리지 않는다** — 조합 중 Backspace 는 글자를 지우는 동작이라,
    // 여기서 가로채면 자모가 안 지워지고 핸들이 사라진다.
    if (event.key === 'Backspace' && !input && !event.nativeEvent?.isComposing
        && mentions.length > 0 && onRemoveMention) {
      event.preventDefault();
      onRemoveMention(mentions[mentions.length - 1]);
      return;
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      if (event.nativeEvent?.isComposing) return;   // 한글 조합 확정용 Enter 를 전송으로 읽지 않는다
      event.preventDefault();
      if (!sendDisabled && !isLoading && input.trim()) onSend();
    }
  };

  return (
    <aside className={`work-assistant-drawer ${isOpen ? 'open' : ''}`} aria-label={title} aria-hidden={!isOpen}>
      {isOpen && (
        <>
          <header className="work-assistant-header">
            <div className="work-assistant-identity">
              <span className="work-assistant-logo"><Sparkles size={17} /></span>
              <span className="work-assistant-title-group">
                <strong>{title}</strong>
                <span>{description}</span>
              </span>
            </div>
            <div className="work-assistant-header-actions">
              {headerMeta}
              <button type="button" className="work-assistant-icon-button" onClick={onClose} title="AI 패널 닫기" aria-label="AI 패널 닫기">
                <X size={18} />
              </button>
            </div>
          </header>

          <div className="work-assistant-context-bar">
            <span className={`work-assistant-status ${isLoading ? 'is-working' : ''}`} />
            <span>{isLoading ? '작업 중' : '준비됨'}</span>
            <span className="work-assistant-context-label">{contextLabel}</span>
          </div>

          {controls && <section className="work-assistant-controls">{controls}</section>}

          <div className="work-assistant-messages" aria-live="polite">
            {messages.map((message, index) => (
              <article key={`${message.role}-${index}`} className={`work-assistant-message ${message.role}`}>
                {message.role === 'assistant' && (
                  <span className="work-assistant-avatar" aria-hidden="true"><Bot size={14} /></span>
                )}
                <div className="work-assistant-bubble">
                  <ReactMarkdown>{message.content}</ReactMarkdown>
                </div>
              </article>
            ))}

            {suggestions.length > 0 && messages.length <= 1 && !isLoading && (
              <div className="work-assistant-suggestions" aria-label="추천 요청">
                {suggestions.map((suggestion) => (
                  <button key={suggestion} type="button" onClick={() => onSuggestion?.(suggestion)}>
                    {suggestion}
                  </button>
                ))}
              </div>
            )}

            {isLoading && <AiThinking label={loadingLabel} />}
            <div ref={messagesEndRef} />
          </div>

          <footer className="work-assistant-composer">
            <div className="work-assistant-input-shell">
              {mentions.length > 0 && (
                <div className="work-assistant-mentions" aria-label="AI에 첨부한 대상">
                  {mentions.map((m) => (
                    <button
                      key={m.key}
                      type="button"
                      className={`work-assistant-mention ${m.missing ? 'is-missing' : ''}`}
                      onClick={() => onRemoveMention?.(m)}
                      title={m.missing ? '삭제된 대상입니다. 눌러서 제거하세요.' : `${m.label} 첨부 해제`}
                      aria-label={m.missing ? '삭제된 대상 제거' : `${m.label} 첨부 해제`}
                    >
                      <span className="work-assistant-mention-at" aria-hidden="true">@</span>
                      <span className="work-assistant-mention-label">
                        {m.missing ? '삭제된 대상' : m.label}
                      </span>
                      <X size={10} aria-hidden="true" />
                    </button>
                  ))}
                </div>
              )}
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInput}
                onKeyDown={handleKeyDown}
                placeholder={placeholder}
                disabled={isLoading}
                rows={1}
              />
              {isLoading && onCancel ? (
                <button type="button" className="work-assistant-send is-cancel" onClick={onCancel} title="생성 취소" aria-label="생성 취소">
                  <Square size={15} fill="currentColor" />
                </button>
              ) : (
                <button
                  type="button"
                  className="work-assistant-send"
                  onClick={onSend}
                  disabled={sendDisabled || !input.trim()}
                  title="요청 보내기"
                  aria-label="요청 보내기"
                >
                  <Send size={17} />
                </button>
              )}
            </div>
          </footer>
        </>
      )}
    </aside>
  );
}

export default AIAssistantDrawer;
