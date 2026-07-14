import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import { useNavigate } from 'react-router-dom';
import MainSidebar from '../MainSidebar';
import { Clock, Play, Square, ExternalLink, RefreshCw, Trash2, FileText, MoreVertical, Calendar } from 'lucide-react';
import './MainPage.css';
import './SchedulerPage.css';

export default function SchedulerPage() {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(true);
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
    } catch (err) {
      console.error('Failed to fetch schedules:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSchedules();
  }, [token]);

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
    if (!window.confirm('정말로 이 스케줄을 삭제하시겠습니까? (워크플로우에서 스케줄 노드가 제거됩니다)')) {
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
        <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
          <div className="content-area centered" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto', padding: '2rem' }}>
            <h2>로그인이 필요합니다</h2>
            <p>스케줄을 관리하려면 먼저 로그인해주세요.</p>
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
              <h1 className="page-title"><Clock className="title-icon" /> 스케줄 관리</h1>
              <p className="page-subtitle">백그라운드에서 주기적으로 실행되는 워크플로우를 확인하고 관리하세요.</p>
            </div>
            <button className="btn-refresh" onClick={fetchSchedules} disabled={loading}>
              <RefreshCw size={18} className={loading ? 'spinning' : ''} /> 새로고침
            </button>
          </div>

          {loading ? (
            <div className="loading-state">
              <RefreshCw size={32} className="spinning" />
              <p>스케줄 목록을 불러오는 중...</p>
            </div>
          ) : schedules.length === 0 ? (
            <div className="empty-state">
              <Calendar size={48} className="empty-icon" />
              <h3>등록된 스케줄이 없습니다</h3>
              <p>에디터에서 '스케줄 노드'를 추가하여 자동화를 예약해보세요.</p>
            </div>
          ) : (
            <div className="scheduler-grid">
              {schedules.map(schedule => (
                <div key={schedule.project_id} className={`scheduler-card ${schedule.status.toLowerCase()}`}>
                  <div className="scheduler-card-header">
                    <div className="scheduler-status-indicator">
                      <span className={`status-dot ${schedule.status.toLowerCase()}`}></span>
                      <span className="status-text">
                        {schedule.status === 'Active' ? '실행 대기 중' : schedule.status === 'Paused' ? '일시 정지' : '중지됨'}
                      </span>
                    </div>
                  </div>
                  
                  <div className="scheduler-card-body">
                    <h3 className="project-title">{schedule.title}</h3>
                    <p className="schedule-cron">
                      Cron: <code>{schedule.cron}</code>
                    </p>
                    <p className="next-run-time">
                      다음 실행: {schedule.next_run ? new Date(schedule.next_run).toLocaleString() : '없음'}
                    </p>
                  </div>

                  <div className="scheduler-card-actions">
                    {schedule.status === 'Active' ? (
                      <button className="btn-primary-action stop" onClick={() => handleAction(schedule.project_id, 'pause')}>
                        <Square size={16} /> 일시 정지
                      </button>
                    ) : (
                      <button className="btn-primary-action start" onClick={() => handleAction(schedule.project_id, 'resume')}>
                        <Play size={16} /> 재개
                      </button>
                    )}
                    
                    <div className="dropdown-container">
                      <button className="btn-icon" onClick={(e) => toggleDropdown(schedule.project_id, e)}>
                        <MoreVertical size={20} />
                      </button>
                      
                      {activeDropdown === schedule.project_id && (
                        <div className="dropdown-menu">
                          <button className="dropdown-item" onClick={() => navigate(`/editor/${schedule.project_id}`)}>
                            <ExternalLink size={16} /> 에디터로
                          </button>
                          <button className="dropdown-item" onClick={() => openLogs(schedule.project_id)}>
                            <FileText size={16} /> 실행 로그
                          </button>
                          <div className="dropdown-divider"></div>
                          <button className="dropdown-item danger" onClick={() => handleDelete(schedule.project_id)}>
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
        <div className="logs-modal-overlay" onClick={() => setLogsModalOpen(false)}>
          <div className="logs-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="logs-modal-header">
              <h3>스케줄 실행 로그</h3>
              <button className="close-btn" onClick={() => setLogsModalOpen(false)}>&times;</button>
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
