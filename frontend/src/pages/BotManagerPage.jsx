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
      alert(`${action === 'start' ? '?œì‘' : '?•ì?'} ì¤??¤ë¥˜ê°€ ë°œìƒ?ˆìŠµ?ˆë‹¤: ` + (err.response?.data?.detail || err.message));
    }
  };

  if (!user) {
    return (
      <div className="main-page-layout">
        <MainSidebar />
        <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
          <div className="content-area centered" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto', padding: '2rem' }}>
            <h2>ë¡œê·¸?¸ì´ ?„ìš”?©ë‹ˆ??/h2>
            <p>ë´‡ì„ ê´€ë¦¬í•˜?¤ë©´ ë¨¼ì? ë¡œê·¸?¸í•´ì£¼ì„¸??</p>
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
              <h1 className="page-title"><Bot className="title-icon" /> ë´?ê´€ë¦?/h1>
              <p className="page-subtitle">?”ìŠ¤ì½”ë“œë¡?ë°°í¬??ì±—ë´‡?¤ì˜ ?íƒœë¥??•ì¸?˜ê³  ê´€ë¦¬í•˜?¸ìš”.</p>
            </div>
            <button className="btn-refresh" onClick={fetchBots} disabled={loading}>
              <RefreshCw size={18} className={loading ? 'spinning' : ''} /> ?ˆë¡œê³ ì¹¨
            </button>
          </div>

          {loading ? (
            <div className="loading-state">
              <RefreshCw size={32} className="spinning" />
              <p>ë´?ëª©ë¡??ë¶ˆëŸ¬?¤ëŠ” ì¤?..</p>
            </div>
          ) : bots.length === 0 ? (
            <div className="empty-state">
              <Bot size={48} className="empty-icon" />
              <h3>?œì„±?”ëœ ë´‡ì´ ?†ìŠµ?ˆë‹¤</h3>
              <p>?ë””?°ì—??'?”ìŠ¤ì½”ë“œ ë´? ëª¨ë“œë¡?ë°°í¬???„ë¡œ?íŠ¸ê°€ ?¬ê¸°???œì‹œ?©ë‹ˆ??</p>
            </div>
          ) : (
            <div className="bot-grid">
              {bots.map(bot => (
                <div key={bot.project_id} className={`bot-card ${bot.status}`}>
                  <div className="bot-card-header">
                    <div className="bot-status-indicator">
                      <span className={`status-dot ${bot.status}`}></span>
                      <span className="status-text">
                        {bot.status === 'online' ? '?¨ë¼?? : bot.status === 'connecting' ? '?°ê²° ì¤? : '?¤í”„?¼ì¸'}
                      </span>
                    </div>
                  </div>
                  
                  <div className="bot-card-body">
                    <h3 className="project-title">{bot.project_title}</h3>
                    <p className="bot-name">
                      {bot.bot_name ? bot.bot_name : '?°ê²° ?•ë³´ ?†ìŒ'}
                    </p>
                    <p className="update-time">
                      ë§ˆì?ë§??…ë°?´íŠ¸: {new Date(bot.updated_at).toLocaleDateString()}
                    </p>
                  </div>

                  <div className="bot-card-actions">
                    {bot.status === 'online' || bot.status === 'connecting' ? (
                      <button className="btn-action stop" onClick={() => handleAction(bot.project_id, 'stop')}>
                        <Square size={16} /> ?•ì?
                      </button>
                    ) : (
                      <button className="btn-action start" onClick={() => handleAction(bot.project_id, 'start')}>
                        <Play size={16} /> ?œì‘
                      </button>
                    )}
                    <button className="btn-action view" onClick={() => navigate(`/editor/${bot.project_id}`)}>
                      <ExternalLink size={16} /> ?ë””?°ë¡œ
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
