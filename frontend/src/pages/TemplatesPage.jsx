import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Play, LibraryBig, Search, X, Download } from 'lucide-react';
import MainSidebar from '../MainSidebar';
import { useAuth } from '../AuthContext';
import './MainPage.css';

function TemplatesPage() {
  const navigate = useNavigate();
  const { user, token } = useAuth();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [importing, setImporting] = useState(null);

  const fetchProjects = async () => {
    try {
      const res = await axios.get('/api/projects/public');
      setProjects(res.data);
    } catch (error) {
      console.error('Error fetching projects:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleImport = async (project) => {
    if (!user || !token) {
      alert("템플릿을 가져오려면 로그인이 필요합니다.");
      return;
    }
    
    try {
      setImporting(project.id);
      
      // 1. 원본 프로젝트 데이터 불러오기
      const res = await axios.get(`/api/projects/${project.id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const originalData = res.data;
      
      // 2. 내 계정에 새 프로젝트(사본) 생성
      const createRes = await axios.post('/api/projects', {
        title: `${originalData.title} (사본)`,
        description: originalData.description,
        graph_data: originalData.graph_data,
        visibility: 'private'
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      const newProjectId = createRes.data.id;
      
      // 3. 에디터로 이동
      navigate(`/editor/${newProjectId}`);
      
    } catch (error) {
      console.error('Error importing project:', error);
      alert("템플릿 가져오기에 실패했습니다.");
    } finally {
      setImporting(null);
    }
  };

  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return projects;
    const q = searchQuery.toLowerCase();
    return projects.filter(
      p => p.title?.toLowerCase().includes(q) || p.description?.toLowerCase().includes(q) || p.owner?.toLowerCase().includes(q)
    );
  }, [projects, searchQuery]);

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <div className="dashboard-grid">
          <section>
            <div className="section-header">
              <h3><LibraryBig size={22} color="#3b82f6" /> 커뮤니티 템플릿</h3>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                {!loading && `${projects.length}개의 공개 워크플로우`}
              </span>
            </div>

            {/* 검색 바 */}
            <div style={{ position: 'relative', marginBottom: '1.5rem', maxWidth: '460px' }}>
              <Search size={16} style={{ position: 'absolute', left: '0.9rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
              <input
                type="text"
                placeholder="제목, 설명, 작성자로 검색..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.65rem 2.5rem 0.65rem 2.4rem',
                  background: 'var(--card-bg)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '10px',
                  color: 'var(--text-color)',
                  fontSize: '0.9rem',
                  outline: 'none',
                  transition: 'border-color 0.2s',
                  boxSizing: 'border-box',
                }}
                onFocus={(e) => e.target.style.borderColor = '#3b82f6'}
                onBlur={(e) => e.target.style.borderColor = 'var(--border-color)'}
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  style={{ position: 'absolute', right: '0.75rem', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', padding: 0 }}
                >
                  <X size={16} />
                </button>
              )}
            </div>

            {loading ? (
              <p style={{ color: 'var(--text-muted)' }}>템플릿을 불러오는 중...</p>
            ) : projects.length === 0 ? (
              <div style={{ padding: '3rem 2rem', textAlign: 'center', background: 'var(--card-bg)', borderRadius: '16px', border: '1px dashed var(--border-color)' }}>
                <LibraryBig size={40} color="var(--text-muted)" style={{ marginBottom: '1rem', opacity: 0.4 }} />
                <p style={{ color: 'var(--text-muted)', margin: 0 }}>아직 공개된 템플릿이 없습니다.</p>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: '0.5rem' }}>워크플로우를 '공개'로 설정하면 여기에 표시됩니다.</p>
              </div>
            ) : filtered.length === 0 ? (
              <div style={{ padding: '2.5rem', textAlign: 'center', background: 'var(--card-bg)', borderRadius: '16px', border: '1px dashed var(--border-color)' }}>
                <Search size={36} color="var(--text-muted)" style={{ marginBottom: '1rem', opacity: 0.4 }} />
                <p style={{ color: 'var(--text-muted)', margin: 0 }}>
                  "<strong>{searchQuery}</strong>"에 대한 결과가 없습니다.
                </p>
              </div>
            ) : (
              <div className="projects-grid">
                {filtered.map(project => (
                  <div key={project.id} className="project-card">
                    <h4>{project.title}</h4>
                    {project.description && (
                      <p>{project.description}</p>
                    )}
                    <div className="project-meta">
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                        by {project.owner}
                      </span>
                    </div>
                    <div className="card-actions" style={{ display: 'flex', gap: '0.5rem' }}>
                      <button 
                        className="btn-secondary" 
                        onClick={() => navigate(`/editor/${project.id}`)} 
                        style={{ flex: 1, padding: '0.5rem' }}
                      >
                        <Play size={14} /> 실행
                      </button>
                      <button 
                        className="btn-primary" 
                        onClick={() => handleImport(project)} 
                        disabled={importing === project.id}
                        style={{ flex: 1, padding: '0.5rem' }}
                      >
                        <Download size={14} /> {importing === project.id ? '복사중...' : '가져오기'}
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

export default TemplatesPage;
