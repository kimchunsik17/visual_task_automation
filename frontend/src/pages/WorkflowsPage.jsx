import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import { Play, Plus, LayoutGrid, Smartphone, Trash2, Clock } from 'lucide-react';
import MainSidebar from '../MainSidebar';
import './MainPage.css';

function timeAgo(dateStr) {
  if (!dateStr) return '';
  let parsedDateStr = dateStr;
  if (!parsedDateStr.endsWith('Z') && !parsedDateStr.match(/[+-]\d{2}:?\d{2}$/)) {
    parsedDateStr += 'Z';
  }
  const diff = Date.now() - new Date(parsedDateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return '방금 전';
  if (mins < 60) return `${mins}분 전`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}일 전`;
  const months = Math.floor(days / 30);
  return `${months}개월 전`;
}

function WorkflowsPage() {
  const navigate = useNavigate();
  const { user, token } = useAuth();
  const [myProjects, setMyProjects] = useState([]);
  const [myLoading, setMyLoading] = useState(true);

  const fetchMyProjects = async () => {
    if (!token) { setMyLoading(false); return; }
    setMyLoading(true);
    try {
      const res = await axios.get('/api/projects/my', { headers: { Authorization: `Bearer ${token}` } });
      setMyProjects(res.data);
    } catch (error) {
      console.error('Error fetching my projects:', error);
    } finally {
      setMyLoading(false);
    }
  };

  useEffect(() => { fetchMyProjects(); }, [user, token]);

  const handleDelete = async (projectId) => {
    if (!window.confirm("정말로 이 워크플로우를 삭제하시겠습니까?")) return;
    try {
      await axios.delete(`/api/projects/${projectId}`, { headers: { Authorization: `Bearer ${token}` } });
      setMyProjects(prev => prev.filter(p => p.id !== projectId));
    } catch (error) {
      console.error("Failed to delete project", error);
      alert("프로젝트 삭제에 실패했습니다.");
    }
  };

  const handleAppRun = async (project) => {
    let sToken = project.share_token;
    if (!sToken) {
      try {
        const res = await axios.post(`/api/projects/${project.id}/deploy`, {}, { headers: { Authorization: `Bearer ${token}` } });
        sToken = res.data.share_token;
      } catch (error) {
        console.error("Failed to prepare app run", error);
        alert("앱 실행 준비에 실패했습니다.");
        return;
      }
    }
    navigate(`/app/${sToken}`);
  };

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <div className="dashboard-grid">
          <section>
            <div className="section-header">
              <h3><LayoutGrid size={22} color="#c084fc" /> 내 워크플로우</h3>
              <button className="btn-secondary" onClick={() => navigate('/editor')}>
                <Plus size={16} /> 새 빈 프로젝트
              </button>
            </div>

            {!user ? (
              <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>로그인 후 내 워크플로우를 확인할 수 있습니다.</p>
            ) : myLoading ? (
              <p style={{ color: 'var(--text-muted)' }}>워크플로우를 불러오는 중...</p>
            ) : myProjects.length === 0 ? (
              <div style={{ padding: '3rem 2rem', textAlign: 'center', background: 'var(--card-bg)', borderRadius: '16px', border: '1px dashed var(--border-color)' }}>
                <LayoutGrid size={40} color="var(--text-muted)" style={{ marginBottom: '1rem', opacity: 0.4 }} />
                <p style={{ color: 'var(--text-muted)', margin: '0 0 1.5rem 0', fontSize: '1rem' }}>
                  아직 저장된 워크플로우가 없습니다.
                </p>
                <button className="btn-primary" onClick={() => navigate('/editor')} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Plus size={16} /> 첫 워크플로우 만들기
                </button>
              </div>
            ) : (
              <div className="projects-grid">
                {myProjects.map(project => (
                  <div key={project.id} className="project-card" style={{ position: 'relative', display: 'flex', flexDirection: 'column' }}>
                    <button
                      onClick={() => handleDelete(project.id)}
                      style={{ position: 'absolute', top: '1rem', right: '1rem', padding: '0.4rem', background: 'transparent', border: 'none', color: '#ef4444', cursor: 'pointer', borderRadius: '4px' }}
                      title="삭제"
                      onMouseOver={(e) => e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.1)'}
                      onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                    >
                      <Trash2 size={18} />
                    </button>
                    <h4 style={{ paddingRight: '2rem', marginBottom: '0.4rem' }}>{project.title}</h4>
                    {project.description && (
                      <p style={{ marginBottom: '0.5rem', flex: 1 }}>{project.description}</p>
                    )}
                    <div className="project-meta" style={{ marginBottom: '0.75rem' }}>
                      {project.visibility === 'public' ? (
                        <span className="status-badge public">공개</span>
                      ) : project.visibility === 'friends' ? (
                        <span className="status-badge friends" style={{ backgroundColor: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6', border: '1px solid rgba(59, 130, 246, 0.2)' }}>친구공개</span>
                      ) : (
                        <span className="status-badge private">비공개</span>
                      )}
                      {project.updated_at && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                          <Clock size={12} />
                          {timeAgo(project.updated_at)}
                        </span>
                      )}
                    </div>
                    <div className="card-actions" style={{ display: 'flex', gap: '0.5rem', marginTop: 'auto' }}>
                      <button className="btn-secondary" onClick={() => navigate(`/editor/${project.id}`)} style={{ flex: 1 }}>
                        <Play size={14} /> 편집기
                      </button>
                      <button className="btn-primary" onClick={() => handleAppRun(project)} style={{ flex: 1, backgroundColor: '#3b82f6', color: 'var(--text-color)', border: 'none' }}>
                        <Smartphone size={14} /> 앱 실행
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

export default WorkflowsPage;
