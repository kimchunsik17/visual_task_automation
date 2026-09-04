import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import { customConfirm } from '../CustomConfirm';
import { useNavigate } from 'react-router-dom';
import MainSidebar from '../MainSidebar';
import SectionTabs from '../components/SectionTabs';
import { OPERATIONS_SECTION_TABS } from '../navigation';
import { formatManagementDateTime, shortResourceId } from './managementFormatters';
import { GoogleLogin } from '@react-oauth/google';
import { Bot, Play, Square, ExternalLink, RefreshCw, Trash2, Key, FileText, MoreVertical, Edit } from 'lucide-react';
import './MainPage.css';
import './BotManagerPage.css';
import './ManagementPage.css';

export default function BotManagerPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  const [bots, setBots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedProjectForToken, setSelectedProjectForToken] = useState(null);
  const [reAuthToken, setReAuthToken] = useState(null);
  const [editingDiscordToken, setEditingDiscordToken] = useState('');
  const [logsModalOpen, setLogsModalOpen] = useState(false);
  const [botLogs, setBotLogs] = useState([]);
  const [activeDropdown, setActiveDropdown] = useState(null);

  useEffect(() => {
    const closeDropdown = () => setActiveDropdown(null);
    document.addEventListener('click', closeDropdown);
    return () => document.removeEventListener('click', closeDropdown);
  }, []);

  const openLogs = async (projectId) => {
    setLogsModalOpen(true);
    setBotLogs([]);
    try {
      const res = await axios.get(`/api/bots/${projectId}/logs`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setBotLogs(res.data);
    } catch (err) {
      console.error(err);
      alert('로그를 불러오는 데 실패했습니다.');
    }
  };
  
  const toggleDropdown = (projectId, e) => {
    e.stopPropagation();
    setActiveDropdown(activeDropdown === projectId ? null : projectId);
  };

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

  const onlineBotCount = bots.filter((bot) => bot.status === 'online').length;

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
    if (!(await customConfirm('정말로 이 디스코드 봇 연결을 삭제하시겠습니까? 봇이 정지되며 토큰이 삭제됩니다.'))) {
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
        <main className="main-page-content management-page has-tabs">
          <SectionTabs ariaLabel="운영 섹션" tabs={OPERATIONS_SECTION_TABS} />
          <div className="management-content">
            <div className="management-empty"><h2>로그인이 필요합니다</h2><p>봇을 관리하려면 먼저 로그인해주세요.</p></div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <main className="main-page-content management-page has-tabs">
        <SectionTabs ariaLabel="운영 섹션" tabs={OPERATIONS_SECTION_TABS} />
        <div className="management-content">
          <header className="management-header">
            <div className="management-heading">
              <span className="management-kicker">CONNECTED BOTS</span>
              <h1>봇</h1>
              <p>디스코드와 텔레그램에 연결한 봇의 실행 상태, 인증 정보와 처리 로그를 관리합니다.</p>
            </div>
            <div className="management-header-side" aria-label="봇 요약">
              <div className="management-stat"><span>전체</span><strong>{bots.length}</strong></div>
              <div className="management-stat"><span>온라인</span><strong>{onlineBotCount}</strong></div>
              <button className="management-button" onClick={fetchBots} disabled={loading}><RefreshCw size={14} className={loading ? 'spinning' : ''} /> 새로고침</button>
            </div>
          </header>

          <div className="management-toolbar">
            <span className="management-toolbar-label">봇 연결은 에디터의 디스코드·텔레그램 시작 노드에서 추가할 수 있습니다.</span>
            <button className="management-button" onClick={() => navigate('/editor')}><ExternalLink size={13} /> 에디터 열기</button>
          </div>

          {loading ? (
            <div className="management-loading" aria-label="봇 목록을 불러오는 중">{[0, 1, 2, 3].map(item => <span key={item} />)}</div>
          ) : bots.length === 0 ? (
            <div className="management-empty">
              <span className="management-empty-icon"><Bot size={20} /></span>
              <h2>연결된 봇이 없습니다</h2>
              <p>에디터에서 '디스코드 수신' 또는 '텔레그램 수신' 노드를 추가한 프로젝트가 여기에 표시됩니다.</p>
              <button className="management-button primary" onClick={() => navigate('/editor')}>에디터에서 추가하기</button>
            </div>
          ) : (
            <div className="management-grid">
              {bots.map(bot => (
                <article key={bot.project_id} className={`management-card is-${bot.status}`}>
                  <div className="management-card-body">
                    <div className="management-card-top">
                      <span className="management-resource"><span className="management-resource-icon"><Bot size={14} /></span> CONNECTED BOT</span>
                      <div className="management-card-tools">
                        <span className={`management-status ${bot.status}`}><span className="management-status-dot" />{bot.status === 'online' ? '온라인' : bot.status === 'connecting' ? '연결 중' : '오프라인'}</span>
                      </div>
                    </div>
                    <h2 title={bot.project_title}>{bot.project_title || '제목 없는 봇'}</h2>
                    <p className="management-card-description">{bot.bot_name || '연결된 봇 이름을 확인할 수 없습니다.'}</p>
                    <div className="management-meta-grid">
                      <span className="management-meta-item"><span>플랫폼</span><strong>{bot.platform === 'telegram' ? '텔레그램' : '디스코드'}</strong></span>
                      <span className="management-meta-item"><span>봇 계정</span><strong>{bot.bot_name || '확인되지 않음'}</strong></span>
                      <span className="management-meta-item"><span>최근 수정</span><strong>{formatManagementDateTime(bot.updated_at)}</strong></span>
                      <span className="management-meta-item"><span>프로젝트 ID</span><code>#{bot.project_id}</code></span>
                      <span className="management-meta-item"><span>트리거 노드</span><code title={bot.trigger_node_id}>{shortResourceId(bot.trigger_node_id)}</code></span>
                    </div>
                  </div>

                  <footer className="management-card-actions">
                    {bot.status === 'online' || bot.status === 'connecting' ? (
                      <button className="management-button" onClick={() => handleAction(bot.project_id, 'stop')}>
                        <Square size={14} /> 정지
                      </button>
                    ) : (
                      <button className="management-button primary" onClick={() => handleAction(bot.project_id, 'start')}>
                        <Play size={14} /> 시작
                      </button>
                    )}
                    <div className="management-menu-wrap">
                      <button className="management-icon-button" onClick={(e) => toggleDropdown(bot.project_id, e)} aria-label={`${bot.project_title} 메뉴`}>
                        <MoreVertical size={16} />
                      </button>
                      {activeDropdown === bot.project_id && (
                        <div className="management-menu">
                          <button onClick={() => navigate(`/editor/${bot.project_id}`)}>
                            <Edit size={14} /> 워크플로우 수정
                          </button>
                          {bot.platform !== 'telegram' && (
                            <button onClick={() => openTokenManager(bot.project_id)}>
                              <Key size={14} /> 토큰 관리
                            </button>
                          )}
                          <button onClick={() => openLogs(bot.project_id)}>
                            <FileText size={14} /> 로그 보기
                          </button>
                          <div className="management-menu-divider"></div>
                          <button className="danger" onClick={() => handleDelete(bot.project_id)}>
                            <Trash2 size={14} /> 삭제
                          </button>
                        </div>
                      )}
                    </div>
                  </footer>
                </article>
              ))}
            </div>
          )}
        </div>
      </main>

      {selectedProjectForToken && (
        <div className="token-modal-overlay management-modal-overlay" onClick={closeTokenManager}>
          <div className="token-modal-content management-modal" onClick={(e) => e.stopPropagation()}>
            <div className="token-modal-header">
              <h3>디스코드 봇 토큰 관리</h3>
              <button className="close-btn" onClick={closeTokenManager} aria-label="토큰 관리 닫기">&times;</button>
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

      {logsModalOpen && (
        <div className="token-modal-overlay management-modal-overlay" onClick={() => setLogsModalOpen(false)}>
          <div className="token-modal-content logs-modal management-modal" onClick={(e) => e.stopPropagation()}>
            <div className="token-modal-header">
              <h3>디스코드 봇 로그</h3>
              <button className="close-btn" onClick={() => setLogsModalOpen(false)} aria-label="로그 닫기">&times;</button>
            </div>
            <div className="logs-container">
              {botLogs.length === 0 ? (
                <p className="no-logs">표시할 로그가 없습니다.</p>
              ) : (
                botLogs.map(log => (
                  <div key={log.id} className="log-item">
                    <div className="log-header">
                      <span className="log-user">{log.username}</span>
                      <span className="log-time">{new Date(log.created_at).toLocaleString()}</span>
                    </div>
                    <div className="log-message"><strong>Q:</strong> {log.message}</div>
                    <div className="log-response"><strong>A:</strong> {log.response}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
