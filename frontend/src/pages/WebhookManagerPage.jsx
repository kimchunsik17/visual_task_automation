import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';
import { useNavigate } from 'react-router-dom';
import MainSidebar from '../MainSidebar';
import { Globe, Copy, Play, Square, Activity, ExternalLink, RefreshCw, Trash2, FileText, MoreVertical } from 'lucide-react';
import './MainPage.css';
import './SchedulerPage.css'; // Use identical styles for consistency
import './WebhookManagerPage.css';

export default function WebhookManagerPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  
  const [loading, setLoading] = useState(false);
  const [activeDropdown, setActiveDropdown] = useState(null);
  const [logsModalOpen, setLogsModalOpen] = useState(false);
  const [webhookLogs, setWebhookLogs] = useState([]);

  const [webhooks, setWebhooks] = useState([]);

  useEffect(() => {
    const closeDropdown = () => setActiveDropdown(null);
    document.addEventListener('click', closeDropdown);
    return () => document.removeEventListener('click', closeDropdown);
  }, []);

  const handleCopy = (url, e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(url);
    alert('웹훅 URL이 클립보드에 복사되었습니다!');
  };

  const toggleDropdown = (id, e) => {
    e.stopPropagation();
    setActiveDropdown(activeDropdown === id ? null : id);
  };

  const handleAction = (id, action) => {
    setWebhooks(webhooks.map(wh => {
      if (wh.id === id) {
        return { ...wh, status: action === 'resume' ? 'Active' : 'Stopped' };
      }
      return wh;
    }));
  };

  const handleDelete = (id) => {
    if (!window.confirm('정말로 이 웹훅을 삭제하시겠습니까? (워크플로우에서 진입점이 사라집니다)')) return;
    setWebhooks(webhooks.filter(wh => wh.id !== id));
  };

  const openLogs = (id) => {
    setLogsModalOpen(true);
    // Mock logs for presentation
    setWebhookLogs([
      { id: 101, created_at: new Date().toISOString(), message: 'POST request received', payload: '{"orderId": "20240812-001", "amount": 45000}', result: 'Success (200)' },
      { id: 102, created_at: new Date(Date.now() - 600000).toISOString(), message: 'POST request received', payload: '{"orderId": "20240812-002", "amount": 120000}', result: 'Success (200)' }
    ]);
  };

  const fetchWebhooks = async () => {
    if (!user) return;
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/webhooks', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setWebhooks(data);
      } else {
        console.error('Failed to fetch webhooks');
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWebhooks();
  }, [user]);

  if (!user) {
    return (
      <div className="main-page-layout">
        <MainSidebar />
        <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
          <div className="content-area centered" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto', padding: '2rem' }}>
            <h2>로그인이 필요합니다</h2>
            <p>웹훅을 관리하려면 먼저 로그인해주세요.</p>
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
              <h1 className="page-title"><Globe className="title-icon" /> 웹훅 관리</h1>
              <p className="page-subtitle">외부 서비스에서 워크플로우를 호출하는 엔드포인트를 모니터링합니다.</p>
            </div>
            <button className="btn-refresh" onClick={fetchWebhooks} disabled={loading}>
              <RefreshCw size={18} className={loading ? 'spinning' : ''} /> 새로고침
            </button>
          </div>

          {loading ? (
            <div className="loading-state">
              <RefreshCw size={32} className="spinning" />
              <p>웹훅 목록을 불러오는 중...</p>
            </div>
          ) : webhooks.length === 0 ? (
            <div className="empty-state">
              <Globe size={48} className="empty-icon" />
              <h3>등록된 웹훅이 없습니다</h3>
              <p>에디터에서 '웹훅 수신' 노드를 추가하여 외부 연동을 시작해보세요.</p>
            </div>
          ) : (
            <div className="scheduler-grid">
              {webhooks.map(wh => (
                <div key={wh.id} className={`scheduler-card ${wh.status.toLowerCase()}`}>
                  <div className="scheduler-card-header">
                    <div className="scheduler-status-indicator">
                      <span className={`status-dot ${wh.status.toLowerCase()}`}></span>
                      <span className="status-text">
                        {wh.status === 'Active' ? '활성 (수신 중)' : '중지됨 (거부)'}
                      </span>
                    </div>
                  </div>
                  
                  <div className="scheduler-card-body">
                    <h3 className="project-title">{wh.title}</h3>
                    <div className="webhook-url-box" style={{ marginTop: '1rem', marginBottom: '1rem' }}>
                      <input type="text" readOnly value={wh.url} />
                      <button onClick={(e) => handleCopy(wh.url, e)} title="URL 복사">
                        <Copy size={14} />
                      </button>
                    </div>
                    <p className="next-run-time" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <Activity size={14} /> 최근 수신: {wh.lastTriggered}
                    </p>
                  </div>

                  <div className="scheduler-card-actions">
                    {wh.status === 'Active' ? (
                      <button className="btn-primary-action stop" onClick={() => handleAction(wh.id, 'pause')}>
                        <Square size={16} /> 수신 중지
                      </button>
                    ) : (
                      <button className="btn-primary-action start" onClick={() => handleAction(wh.id, 'resume')}>
                        <Play size={16} /> 수신 재개
                      </button>
                    )}
                    
                    <div className="dropdown-container">
                      <button className="btn-icon" onClick={(e) => toggleDropdown(wh.id, e)}>
                        <MoreVertical size={20} />
                      </button>
                      
                      {activeDropdown === wh.id && (
                        <div className="dropdown-menu">
                          <button className="dropdown-item" onClick={() => navigate(`/editor/${wh.projectId}`)}>
                            <ExternalLink size={16} /> 에디터로
                          </button>
                          <button className="dropdown-item" onClick={() => openLogs(wh.id)}>
                            <FileText size={16} /> 수신 로그
                          </button>
                          <div className="dropdown-divider"></div>
                          <button className="dropdown-item danger" onClick={() => handleDelete(wh.id)}>
                            <Trash2 size={16} /> 삭제
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {logsModalOpen && (
        <div className="token-modal-overlay" onClick={() => setLogsModalOpen(false)}>
          <div className="token-modal-content logs-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '700px' }}>
            <div className="token-modal-header">
              <h3>웹훅 수신 로그</h3>
              <button className="close-btn" onClick={() => setLogsModalOpen(false)}>&times;</button>
            </div>
            <div className="logs-container">
              {webhookLogs.length === 0 ? (
                <p className="no-logs">최근 수신된 웹훅 요청이 없습니다.</p>
              ) : (
                webhookLogs.map(log => (
                  <div key={log.id} className="log-item" style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem', marginBottom: '1rem' }}>
                    <div className="log-header" style={{ marginBottom: '0.5rem' }}>
                      <span className="log-user" style={{ color: '#0ea5e9' }}>{log.message}</span>
                      <span className="log-time" style={{ fontSize: '0.85rem' }}>{new Date(log.created_at).toLocaleString()}</span>
                    </div>
                    <div className="log-message" style={{ background: 'var(--btn-active-bg)', padding: '0.8rem', borderRadius: '6px', fontSize: '0.85rem', fontFamily: 'monospace' }}>
                      {log.payload}
                    </div>
                    <div className="log-response" style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: '#10b981' }}>
                      <strong>Result:</strong> {log.result}
                    </div>
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
