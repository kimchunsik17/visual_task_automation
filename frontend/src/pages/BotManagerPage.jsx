import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import { useNavigate } from 'react-router-dom';
import MainSidebar from '../MainSidebar';
import { GoogleLogin } from '@react-oauth/google';
import { Bot, Play, Square, ExternalLink, RefreshCw, Trash2, Key } from 'lucide-react';
import './MainPage.css';
import './BotManagerPage.css';

export default function BotManagerPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  const [bots, setBots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedProjectForToken, setSelectedProjectForToken] = useState(null);
  const [reAuthToken, setReAuthToken] = useState(null);
  const [editingDiscordToken, setEditingDiscordToken] = useState('');

  const openTokenManager = (projectId) => {
    setSelectedProjectForToken(projectId);
    setReAuthToken(null);
    setEditingDiscordToken('');
  };

  const closeTokenManager = () => {
    setSelectedProjectForToken(null);
    setReAuthToken(null);
    setEditingDiscordToken('');
  };

  const handleGoogleSuccess = async (credentialResponse) => {
    try {
      setReAuthToken(credentialResponse.credential);
      const res = await axios.post(`/api/bots/${selectedProjectForToken}/reveal-token`, 
        { google_token: credentialResponse.credential },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setEditingDiscordToken(res.data.token || '');
    } catch (err) {
      console.error(err);
      alert('인증에 실패했습니다. 본인 계정인지 확인해주세요.');
      closeTokenManager();
    }
  };

  const handleSaveToken = async () => {
    try {
      await axios.put(`/api/bots/${selectedProjectForToken}/update-token`, 
        { google_token: reAuthToken, new_discord_token: editingDiscordToken },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      alert('토큰이 성공적으로 저장되었습니다.');
      closeTokenManager();
      fetchBots();
    } catch (err) {
      console.error(err);
      alert('토큰 저장에 실패했습니다.');
    }
  };

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

  const handleDelete = async (projectId) => {
    if (!window.confirm('정말로 이 디스코드 봇 연결을 삭제하시겠습니까? 봇이 정지되며 토큰이 삭제됩니다.')) {
      return;
    }
    try {
      await axios.delete(`/api/bots/${projectId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchBots();
    } catch (err) {
      console.error('Failed to delete bot:', err);
      alert('삭제 중 오류가 발생했습니다: ' + (err.response?.data?.detail || err.message));
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
                    <button className="btn-action key" onClick={() => openTokenManager(bot.project_id)}>
                      <Key size={16} /> 토큰 관리
                    </button>
                    <button className="btn-action delete" onClick={() => handleDelete(bot.project_id)} style={{ color: '#ef4444' }}>
                      <Trash2 size={16} /> 삭제
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {selectedProjectForToken && (
        <div className="token-modal-overlay" onClick={closeTokenManager}>
          <div className="token-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="token-modal-header">
              <h3>디스코드 봇 토큰 관리</h3>
              <button className="close-btn" onClick={closeTokenManager}>&times;</button>
            </div>
            
            <div className="token-modal-body">
              {!reAuthToken ? (
                <div className="auth-step">
                  <p>보안을 위해 구글 계정으로 다시 한번 인증해주세요.</p>
                  <div className="google-login-wrapper">
                    <GoogleLogin
                      onSuccess={handleGoogleSuccess}
                      onError={() => alert('구글 로그인에 실패했습니다.')}
                      useOneTap={false}
                    />
                  </div>
                </div>
              ) : (
                <div className="token-edit-step">
                  <p>토큰을 확인하고 수정할 수 있습니다.</p>
                  <input 
                    type="text" 
                    className="token-input" 
                    value={editingDiscordToken} 
                    onChange={(e) => setEditingDiscordToken(e.target.value)} 
                    placeholder="Discord Bot Token"
                  />
                  <div className="token-modal-actions">
                    <button className="btn-cancel" onClick={closeTokenManager}>취소</button>
                    <button className="btn-save" onClick={handleSaveToken}>저장</button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
