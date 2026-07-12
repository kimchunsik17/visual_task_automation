import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import { Play, Plus, LayoutGrid, Smartphone } from 'lucide-react';
import MainSidebar from '../MainSidebar';
import './MainPage.css'; // Reusing layout CSS

function WorkflowsPage() {
  const navigate = useNavigate();
  const { user, token } = useAuth();
  const [myProjects, setMyProjects] = useState([]);
  const [myLoading, setMyLoading] = useState(true);

  const fetchMyProjects = async () => {
    if (!token) {
      setMyLoading(false);
      return;
    }
    setMyLoading(true);
    try {
      const res = await axios.get('/api/projects/my', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setMyProjects(res.data);
    } catch (error) {
      console.error('Error fetching my projects:', error);
    } finally {
      setMyLoading(false);
    }
  };

  useEffect(() => {
    fetchMyProjects();
  }, [user, token]);

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
              <p style={{ color: '#94a3b8', textAlign: 'center', padding: '2rem' }}>로그인 후 내 워크플로우를 확인할 수 있습니다.</p>
            ) : myLoading ? (
              <p style={{ color: '#94a3b8' }}>워크플로우를 불러오는 중...</p>
            ) : myProjects.length === 0 ? (
              <p style={{ color: '#64748b', padding: '2rem', textAlign: 'center', background: 'var(--card-bg)', borderRadius: '16px', border: '1px dashed #334155' }}>
                아직 저장된 워크플로우가 없습니다. 홈으로 돌아가서 AI를 통해 첫 워크플로우를 만들어보세요!
              </p>
            ) : (
              <div className="projects-grid">
                {myProjects.map(project => (
                  <div key={project.id} className="project-card">
                    <h4>{project.title}</h4>
                    <p>{project.description || '설명이 없습니다.'}</p>
                    <div className="project-meta">
                      <span className={`status-badge ${project.is_public ? 'public' : 'private'}`}>
                        {project.is_public ? '공개' : '비공개'}
                      </span>
                    </div>
                    <div className="card-actions" style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                      <button className="btn-secondary" onClick={() => navigate(`/editor/${project.id}`)} style={{ flex: 1 }}>
                        <Play size={14} /> 편집기
                      </button>
                      <button className="btn-primary" onClick={() => navigate(`/app/${project.id}`)} style={{ flex: 1, backgroundColor: '#3b82f6', color: 'white', border: 'none' }}>
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
