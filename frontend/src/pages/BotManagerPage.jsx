import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import { useNavigate } from 'react-router-dom';
import MainSidebar from '../MainSidebar';
import { Bot, Play, Square, ExternalLink, RefreshCw } from 'lucide-react';
import './MainPage.css';
import './BotManagerPage.css';

export default function BotManagerPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  const [bots, setBots] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchBots = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await axios.get('/api/bots', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setBots(res.data);
    } catch (err) {
      console.error('Failed to fetch bots:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBots();
  }, [token]);

  const handleAction = async (projectId, action) => {
    try {
      await axios.post(`/api/bots/${projectId}/${action}`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchBots();
    } catch (err) {
      console.error(`Failed to ${action} bot:`, err);
      alert(`${action === 'start' ? '시작' : '정지'} 중 오류가 발생했습니다: ` + (err.response?.data?.detail || err.message));
    }
  };

  if (!user) {
    return (
      <div className="main-page-layout">
        <MainSidebar />
        <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
          <div className="content-area centered" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto', padding: '2rem' }}>
            <h2>로그인이 필요합니다</h2>
            <p>봇을 관리하려면 먼저 로그인해주세요.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <div className="content-area" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto', padding: '2rem' }}>
          <div className="page-header">
            <div>
              <h1 className="page-title"><Bot className="title-icon" /> 봇 관리</h1>
              <p className="page-subtitle">디스코드로 배포된 챗봇들의 상태를 확인하고 관리하세요.</p>
            </div>
            <button className="btn-refresh" onClick={fetchBots} disabled={loading}>
              <RefreshCw size={18} className={loading ? 'spinning' : ''} /> 새로고침
            </button>
          </div>

          {loading ? (
            <div className="loading-state">
              <RefreshCw size={32} className="spinning" />
              <p>봇 목록을 불러오는 중...</p>
            </div>
          ) : bots.length === 0 ? (
            <div className="empty-state">
              <Bot size={48} className="empty-icon" />
              <h3>활성화된 봇이 없습니다</h3>
              <p>에디터에서 '디스코드 봇' 모드로 배포한 프로젝트가 여기에 표시됩니다.</p>
            </div>
          ) : (
            <div className="bot-grid">
              {bots.map(bot => (
                <div key={bot.project_id} className={`bot-card ${bot.status}`}>
                  <div className="bot-card-header">
                    <div className="bot-status-indicator">
                      <span className={`status-dot ${bot.status}`}></span>
                      <span className="status-text">
                        {bot.status === 'online' ? '온라인' : bot.status === 'connecting' ? '연결 중' : '오프라인'}
                      </span>
                    </div>
                  </div>
                  
                  <div className="bot-card-body">
                    <h3 className="project-title">{bot.project_title}</h3>
                    <p className="bot-name">
                      {bot.bot_name ? bot.bot_name : '연결 정보 없음'}
                    </p>
                    <p className="update-time">
                      마지막 업데이트: {new Date(bot.updated_at).toLocaleDateString()}
                    </p>
                  </div>

                  <div className="bot-card-actions">
                    {bot.status === 'online' || bot.status === 'connecting' ? (
                      <button className="btn-action stop" onClick={() => handleAction(bot.project_id, 'stop')}>
                        <Square size={16} /> 정지
                      </button>
                    ) : (
                      <button className="btn-action start" onClick={() => handleAction(bot.project_id, 'start')}>
                        <Play size={16} /> 시작
                      </button>
                    )}
                    <button className="btn-action view" onClick={() => navigate(`/editor/${bot.project_id}`)}>
                      <ExternalLink size={16} /> 에디터로
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
