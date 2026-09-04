import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import { customConfirm } from '../CustomConfirm';
import { useNavigate } from 'react-router-dom';
import MainSidebar from '../MainSidebar';
import SectionTabs from '../components/SectionTabs';
import { OPERATIONS_SECTION_TABS } from '../navigation';
import { readListCache, writeListCache } from '../listCache';
import { executionOutcomeLabel, formatManagementDateTime, shortResourceId } from './managementFormatters';
import { Clock, Play, Square, ExternalLink, RefreshCw, Trash2, FileText, MoreVertical, Calendar } from 'lucide-react';
import './MainPage.css';
import './SchedulerPage.css';
import './ManagementPage.css';

export default function SchedulerPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  // 재방문 첫 프레임부터 마지막 목록을 그린다(listCache.js) — 매번 스켈레톤부터
  // 그리면 탭을 옮길 때마다 내용 높이가 출렁인다. 백그라운드 재조회로 따라잡는다.
  const cacheKey = `schedules:${user?.id ?? user?.email ?? 'anon'}`;
  const [schedules, setSchedules] = useState(() => readListCache(cacheKey) ?? []);
  const [loading, setLoading] = useState(() => readListCache(cacheKey) === null);
  const [logsModalOpen, setLogsModalOpen] = useState(false);
  const [scheduleLogs, setScheduleLogs] = useState([]);
  const [activeDropdown, setActiveDropdown] = useState(null);

  useEffect(() => {
    const closeDropdown = () => setActiveDropdown(null);
    document.addEventListener('click', closeDropdown);
    return () => document.removeEventListener('click', closeDropdown);
  }, []);

  const openLogs = async (projectId) => {
    setLogsModalOpen(true);
    setScheduleLogs([]);
    try {
      const res = await axios.get(`/api/schedules/${projectId}/logs`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setScheduleLogs(res.data);
    } catch (err) {
      console.error(err);
      alert('로그를 불러오는 데 실패했습니다.');
    }
  };
  
  const toggleDropdown = (projectId, e) => {
    e.stopPropagation();
    setActiveDropdown(activeDropdown === projectId ? null : projectId);
  };

  const fetchSchedules = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await axios.get('/api/schedules', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setSchedules(res.data);
      writeListCache(cacheKey, res.data);
    } catch (err) {
      console.error('Failed to fetch schedules:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSchedules();
  }, [token]);

  const activeScheduleCount = schedules.filter((schedule) => schedule.status === 'Active').length;

  const handleAction = async (projectId, action) => {
    try {
      await axios.post(`/api/schedules/${projectId}/${action}`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchSchedules();
    } catch (err) {
      console.error(`Failed to ${action} schedule:`, err);
      alert(`${action === 'resume' ? '시작' : '정지'} 중 오류가 발생했습니다: ` + (err.response?.data?.detail || err.message));
    }
  };

  const handleDelete = async (projectId) => {
    if (!(await customConfirm('정말로 이 스케줄을 삭제하시겠습니까? (워크플로우에서 스케줄 노드가 제거됩니다)'))) {
      return;
    }
    try {
      await axios.delete(`/api/schedules/${projectId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchSchedules();
    } catch (err) {
      console.error('Failed to delete schedule:', err);
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
            <div className="management-empty"><h2>로그인이 필요합니다</h2><p>스케줄을 관리하려면 먼저 로그인해주세요.</p></div>
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
              <span className="management-kicker">SCHEDULES</span>
              <h1>스케줄</h1>
              <p>예약된 워크플로우의 실행 주기와 다음 실행 시각, 최근 처리 결과를 관리합니다.</p>
            </div>
            <div className="management-header-side" aria-label="스케줄 요약">
              <div className="management-stat"><span>전체</span><strong>{schedules.length}</strong></div>
              <div className="management-stat"><span>실행 중</span><strong>{activeScheduleCount}</strong></div>
              <button className="management-button" onClick={fetchSchedules} disabled={loading}><RefreshCw size={14} className={loading ? 'spinning' : ''} /> 새로고침</button>
            </div>
          </header>

          <div className="management-toolbar">
            <span className="management-toolbar-label">스케줄은 에디터에서 예약 노드를 추가하면 자동으로 이 목록에 표시됩니다.</span>
            <button className="management-button" onClick={() => navigate('/editor')}><ExternalLink size={13} /> 에디터 열기</button>
          </div>

          {loading && schedules.length === 0 ? (
            <div className="management-loading" aria-label="스케줄 목록을 불러오는 중">{[0, 1, 2, 3].map(item => <span key={item} />)}</div>
          ) : schedules.length === 0 ? (
            <div className="management-empty">
              <span className="management-empty-icon"><Calendar size={20} /></span>
              <h2>등록된 스케줄이 없습니다</h2>
              <p>에디터에서 '스케줄 노드'를 추가하여 자동화를 예약해보세요.</p>
              <button className="management-button primary" onClick={() => navigate('/editor')}>에디터에서 추가하기</button>
            </div>
          ) : (
            <div className="management-grid">
              {schedules.map(schedule => (
                <article key={schedule.project_id} className={`management-card is-${schedule.status.toLowerCase()}`}>
                  <div className="management-card-body">
                    <div className="management-card-top">
                      <span className="management-resource"><span className="management-resource-icon"><Clock size={14} /></span> SCHEDULE</span>
                      <span className={`management-status ${schedule.status.toLowerCase()}`}><span className="management-status-dot" />{schedule.status === 'Active' ? '실행 대기' : schedule.status === 'Paused' ? '일시 정지' : '중지됨'}</span>
                    </div>
                    <h2 title={schedule.title}>{schedule.title || '제목 없는 스케줄'}</h2>
                    <div className="management-data-row"><span>CRON</span><code>{schedule.cron || '설정 없음'}</code></div>
                    <div className="management-meta-grid">
                      <span className="management-meta-item"><span>다음 실행</span><strong>{schedule.next_run ? formatManagementDateTime(schedule.next_run) : '예약 없음'}</strong></span>
                      <span className="management-meta-item"><span>최근 실행</span><strong>{formatManagementDateTime(schedule.last_run)}</strong></span>
                      <span className="management-meta-item"><span>최근 결과</span><strong>{executionOutcomeLabel(schedule.last_outcome)}</strong></span>
                      <span className="management-meta-item"><span>최근 수정</span><strong>{formatManagementDateTime(schedule.updated_at)}</strong></span>
                      <span className="management-meta-item"><span>프로젝트 ID</span><code>#{schedule.project_id}</code></span>
                      <span className="management-meta-item"><span>스케줄 노드</span><code title={schedule.node_id}>{shortResourceId(schedule.node_id)}</code></span>
                    </div>
                  </div>

                  <footer className="management-card-actions">
                    {schedule.status === 'Active' ? (
                      <button className="management-button" onClick={() => handleAction(schedule.project_id, 'pause')}>
                        <Square size={14} /> 일시 정지
                      </button>
                    ) : (
                      <button className="management-button primary" onClick={() => handleAction(schedule.project_id, 'resume')}>
                        <Play size={14} /> 재개
                      </button>
                    )}
                    <div className="management-menu-wrap">
                      <button className="management-icon-button" onClick={(e) => toggleDropdown(schedule.project_id, e)} aria-label={`${schedule.title} 메뉴`}>
                        <MoreVertical size={16} />
                      </button>
                      {activeDropdown === schedule.project_id && (
                        <div className="management-menu">
                          <button onClick={() => navigate(`/editor/${schedule.project_id}`)}>
                            <ExternalLink size={14} /> 에디터에서 열기
                          </button>
                          <button onClick={() => openLogs(schedule.project_id)}>
                            <FileText size={14} /> 실행 로그
                          </button>
                          <div className="management-menu-divider"></div>
                          <button className="danger" onClick={() => handleDelete(schedule.project_id)}>
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
        <div className="logs-modal-overlay management-modal-overlay" onClick={() => setLogsModalOpen(false)}>
          <div className="logs-modal-content management-modal" onClick={(e) => e.stopPropagation()}>
            <div className="logs-modal-header">
              <h3>스케줄 실행 로그</h3>
              <button className="close-btn" onClick={() => setLogsModalOpen(false)} aria-label="로그 닫기">&times;</button>
            </div>
            <div className="logs-modal-body">
              {scheduleLogs.length === 0 ? (
                <p className="no-logs">기록된 실행 로그가 없습니다.</p>
              ) : (
                <div className="logs-list">
                  {scheduleLogs.map(log => (
                    <div key={log.id} className="log-item">
                      <div className="log-time">{new Date(log.execution_time).toLocaleString()}</div>
                      <div className="log-tokens">소모 토큰: {log.total_tokens || 0}</div>
                      <div className="log-result">
                        <pre>{log.result}</pre>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
