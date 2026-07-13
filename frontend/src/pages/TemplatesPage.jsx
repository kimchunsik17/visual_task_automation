import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Play, LibraryBig } from 'lucide-react';
import MainSidebar from '../MainSidebar';
import './MainPage.css'; // Reusing layout CSS

function TemplatesPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

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

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <div className="dashboard-grid">
          <section>
            <div className="section-header">
              <h3><LibraryBig size={22} color="#3b82f6" /> ì»¤ë??ˆí‹° ?œí”Œë¦?/h3>
            </div>
            
            {loading ? (
              <p style={{ color: 'var(--text-muted)' }}>?œí”Œë¦¿ì„ ë¶ˆëŸ¬?¤ëŠ” ì¤?..</p>
            ) : projects.length === 0 ? (
              <p style={{ color: '#64748b' }}>?„ì§ ê³µê°œ???œí”Œë¦¿ì´ ?†ìŠµ?ˆë‹¤.</p>
            ) : (
              <div className="projects-grid">
                {projects.map(project => (
                  <div key={project.id} className="project-card">
                    <h4>{project.title}</h4>
                    <p>{project.description || '?¤ëª…???†ìŠµ?ˆë‹¤.'}</p>
                    <div className="project-meta">
                      <span>?‘ì„±?? {project.owner}</span>
                    </div>
                    <div className="card-actions">
                      <button className="btn-secondary" onClick={() => navigate(`/editor/${project.id}`)}>
                        <Play size={14} /> ?´ê¸° ë°??¤í–‰
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
