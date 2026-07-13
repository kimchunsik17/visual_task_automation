import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import { Play, Plus, Sparkles, Wand2, Search } from 'lucide-react';
import MainSidebar from '../MainSidebar';
import './MainPage.css';

function MainPage() {
  const navigate = useNavigate();
  const { user, token } = useAuth();
  
  const [autoPrompt, setAutoPrompt] = useState('');
  const [isAutoGenerating, setIsAutoGenerating] = useState(false);
  const [messages, setMessages] = useState([]);

  const getAuthHeaders = () => token ? { headers: { Authorization: `Bearer ${token}` } } : {};


  const handleAutoGenerate = async () => {
    if (!autoPrompt.trim()) return;
    
    const userMessage = autoPrompt.trim();
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setAutoPrompt('');
    setIsAutoGenerating(true);

    // 딜레이를 주어 AI 응답을 시뮬레이션 (LLM 구현 보류)
    setTimeout(() => {
      setMessages(prev => [...prev, { role: 'ai', content: '현재 llm 업무 자동화 기능은 구현 중에 있습니다.' }]);
      setIsAutoGenerating(false);
    }, 800);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAutoGenerate();
    }
  };

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content">
        {messages.length === 0 ? (
          <div className="chat-hero-header">
            <h2>오늘은 어떤 업무를<br/>자동화해 볼까요?</h2>
            <p>원하시는 작업을 자연어로 입력해 보세요. AI가 즉시 실행 가능한 워크플로우를 알아서 생성해 드립니다.</p>
          </div>
        ) : (
          <div className="chat-history">
            {messages.map((msg, index) => (
              <div key={index} className={`chat-message ${msg.role}`}>
                {msg.role === 'ai' && (
                  <div className="chat-avatar ai-avatar">
                    <Sparkles size={16} />
                  </div>
                )}
                <div className="chat-bubble">
                  {msg.content}
                </div>
              </div>
            ))}
          </div>
        )}
        
        <div className="chat-input-wrapper">
          <div className="auto-gen-container">
            <textarea 
              className="auto-gen-input"
              value={autoPrompt} 
              onChange={(e) => setAutoPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="예: 매일 아침 8시에 해커뉴스 메인 페이지를 크롤링해서 상위 5개 기사를 요약해 줘."
            />
            <div className="auto-gen-actions">
              <div className="gen-hints">
                <span className="hint-chip" onClick={() => setAutoPrompt("기술 뉴스 요약해서 이메일로 보내줘")}>뉴스 요약</span>
                <span className="hint-chip" onClick={() => setAutoPrompt("경쟁사 웹사이트 변경사항 모니터링해 줘")}>웹 모니터링</span>
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
    </div>
  );
}

export default MainPage;

