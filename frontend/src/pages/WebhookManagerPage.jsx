import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';
import { Icon } from '../icons';
import { customConfirm } from '../CustomConfirm';
import { useNavigate } from 'react-router-dom';
import MainSidebar from '../MainSidebar';
import SectionTabs from '../components/SectionTabs';
import { OPERATIONS_SECTION_TABS } from '../navigation';
import { formatManagementDateTime, shortResourceId } from './managementFormatters';
import { Copy, Play, Square, ExternalLink, RefreshCw, Trash2, FileText, MoreVertical } from 'lucide-react';
import './MainPage.css';
import './SchedulerPage.css'; // Use identical styles for consistency
import './WebhookManagerPage.css';
import './ManagementPage.css';

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

  const handleAction = async (id, projectId, action) => {
    try {
      const isLive = action === 'resume';
      const response = await fetch(`/api/projects/${projectId}/live`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ is_live: isLive })
      });
      if (response.ok) {
        setWebhooks(webhooks.map(wh => {
          if (wh.id === id) {
            return { ...wh, status: isLive ? 'Active' : 'Stopped' };
          }
          return wh;
        }));
      }
    } catch(err) {
      console.error(err);
    }
  };

  const handleDelete = async (id) => {
    if (!(await customConfirm('정말로 이 웹훅을 삭제하시겠습니까? (워크플로우에서 진입점이 사라집니다)'))) return;
    try {
      const response = await fetch(`/api/webhooks/${encodeURIComponent(id)}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        setWebhooks(webhooks.filter(wh => wh.id !== id));
      } else {
        alert('웹훅 삭제에 실패했습니다.');
      }
    } catch (err) {
      console.error(err);
      alert('웹훅 삭제 중 오류가 발생했습니다.');
    }
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
      const response = await fetch('/api/webhooks', {
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

  const activeWebhookCount = webhooks.filter((webhook) => webhook.status === 'Active').length;

  if (!user) {
    return (
      <div className="main-page-layout">
        <MainSidebar />
        <main className="main-page-content management-page has-tabs">
          <SectionTabs ariaLabel="운영 섹션" tabs={OPERATIONS_SECTION_TABS} />
          <div className="management-content">
            <div className="management-empty"><h2>로그인이 필요합니다</h2><p>웹훅을 관리하려면 먼저 로그인해주세요.</p></div>
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
              <span className="management-kicker">WEBHOOKS</span>
              <h1>웹훅</h1>
              <p>외부 서비스가 워크플로우를 호출하는 엔드포인트와 최근 수신 상태를 관리합니다.</p>
            </div>
            <div className="management-header-side" aria-label="웹훅 요약">
              <div className="management-stat"><span>전체</span><strong>{webhooks.length}</strong></div>
              <div className="management-stat"><span>수신 중</span><strong>{activeWebhookCount}</strong></div>
              <button className="management-button" onClick={fetchWebhooks} disabled={loading}><RefreshCw size={14} className={loading ? 'spinning' : ''} /> 새로고침</button>
            </div>
          </header>

          <div className="management-toolbar">
            <span className="management-toolbar-label">웹훅은 에디터의 웹훅 수신 노드에서 추가할 수 있습니다.</span>
            <button className="management-button" onClick={() => navigate('/editor')}><ExternalLink size={13} /> 에디터 열기</button>
          </div>

          {loading ? (
            <div className="management-loading" aria-label="웹훅 목록을 불러오는 중">{[0, 1, 2, 3].map(item => <span key={item} />)}</div>
          ) : webhooks.length === 0 ? (
            <div className="management-empty">
              <span className="management-empty-icon"><Icon name="nav-webhooks" size={20} /></span>
              <h2>등록된 웹훅이 없습니다</h2>
              <p>에디터에서 '웹훅 수신' 노드를 추가하여 외부 연동을 시작해보세요.</p>
              <button className="management-button primary" onClick={() => navigate('/editor')}>에디터에서 추가하기</button>
            </div>
          ) : (
            <div className="management-grid">
              {webhooks.map(wh => (
                <article key={wh.id} className={`management-card is-${wh.status.toLowerCase()}`}>
                  <div className="management-card-body">
                    <div className="management-card-top">
                      <span className="management-resource"><span className="management-resource-icon"><Icon name="nav-webhooks" size={14} /></span> ENDPOINT</span>
                      <span className={`management-status ${wh.status.toLowerCase()}`}><span className="management-status-dot" />{wh.status === 'Active' ? '수신 중' : '중지됨'}</span>
                    </div>
                    <h2 title={wh.title}>{wh.title || '제목 없는 웹훅'}</h2>
                    <div className="management-data-row">
                      <input type="text" readOnly value={wh.url} />
                      <button onClick={(e) => handleCopy(wh.url, e)} title="URL 복사">
                        <Copy size={14} />
                      </button>
                    </div>
                    <div className="management-meta-grid">
                      <span className="management-meta-item"><span>최근 수신</span><strong>{wh.lastTriggered || '기록 없음'}</strong></span>
                      <span className="management-meta-item"><span>허용 메서드</span><strong>{Array.isArray(wh.methods) ? wh.methods.join(' · ') : 'GET · POST'}</strong></span>
                      <span className="management-meta-item"><span>최근 수정</span><strong>{formatManagementDateTime(wh.updatedAt)}</strong></span>
                      <span className="management-meta-item"><span>프로젝트 ID</span><code>#{wh.projectId}</code></span>
                      <span className="management-meta-item"><span>노드 ID</span><code title={wh.nodeId}>{shortResourceId(wh.nodeId)}</code></span>
                      <span className="management-meta-item"><span>엔드포인트 ID</span><code title={wh.id}>{shortResourceId(wh.id)}</code></span>
                    </div>
                  </div>

                  <footer className="management-card-actions">
                    {wh.status === 'Active' ? (
                      <button className="management-button" onClick={() => handleAction(wh.id, wh.projectId, 'pause')}>
                        <Square size={14} /> 수신 중지
                      </button>
                    ) : (
                      <button className="management-button primary" onClick={() => handleAction(wh.id, wh.projectId, 'resume')}>
                        <Play size={14} /> 수신 재개
                      </button>
                    )}
                    <div className="management-menu-wrap">
                      <button className="management-icon-button" onClick={(e) => toggleDropdown(wh.id, e)} aria-label={`${wh.title} 메뉴`}>
                        <MoreVertical size={16} />
                      </button>
                      {activeDropdown === wh.id && (
                        <div className="management-menu">
                          <button onClick={() => navigate(`/editor/${wh.projectId}`)}>
                            <ExternalLink size={14} /> 에디터에서 열기
                          </button>
                          <button onClick={() => openLogs(wh.id)}>
                            <FileText size={14} /> 수신 로그
                          </button>
                          <div className="management-menu-divider"></div>
                          <button className="danger" onClick={() => handleDelete(wh.id)}>
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

      {logsModalOpen && (
        <div className="token-modal-overlay management-modal-overlay" onClick={() => setLogsModalOpen(false)}>
          <div className="token-modal-content logs-modal management-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '700px' }}>
            <div className="token-modal-header">
              <h3>웹훅 수신 로그</h3>
              <button className="close-btn" onClick={() => setLogsModalOpen(false)} aria-label="로그 닫기">&times;</button>
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
                    <div className="log-message" style={{ background: 'var(--btn-active-bg)', padding: '0.8rem', borderRadius: '6px', fontSize: '0.85rem', fontFamily: 'var(--font-mono)' }}>
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
