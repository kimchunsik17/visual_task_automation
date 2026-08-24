import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../AuthContext';
import MainSidebar from '../MainSidebar';
import { Plus, LayoutTemplate, Clock, ChevronRight, Trash2 } from 'lucide-react';
import './MainPage.css';

const CustomAppsDashboardPage = () => {
  const navigate = useNavigate();
  const { token } = useAuth();
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    const fetchApps = async () => {
      try {
        const res = await axios.get('/api/apps/custom', {
          headers: { Authorization: `Bearer ${token}` }
        });
        setApps(res.data);
      } catch (err) {
        console.error('Failed to fetch custom apps', err);
      } finally {
        setLoading(false);
      }
    };
    fetchApps();
  }, [token]);

  const handleDeleteApp = async (e, appId) => {
    e.stopPropagation();
    if (!window.confirm("정말로 이 앱을 삭제하시겠습니까?")) return;
    try {
      await axios.delete(`/api/apps/custom/${appId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setApps(prev => prev.filter(a => a.id !== appId));
    } catch (err) {
      alert("앱 삭제 중 오류가 발생했습니다.");
    }
  };

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <div className="dashboard-grid">
          <section>
            <div className="section-header">
              <h3><LayoutTemplate size={22} color="#c084fc" /> 내 커스텀 앱</h3>
              <p style={{ color: 'var(--text-muted)', marginLeft: '1rem', flex: 1 }}>AI를 이용해 직접 만든 나만의 앱들을 관리하세요</p>
            </div>
          <div className="projects-grid">
            {/* Create New App Card */}
            <div 
              className="project-card create-new"
              onClick={() => navigate('/app-builder')}
            >
              <div className="create-icon">
                <Plus size={32} />
              </div>
              <h3>새 앱 만들기</h3>
              <p>빈 캔버스에서 시작하기</p>
            </div>

            {/* List Existing Apps */}
            {loading ? (
              <div style={{ color: 'var(--text-muted)' }}>앱 불러오는 중...</div>
            ) : (
              apps.map(app => (
                <div 
                  key={app.id} 
                  className="project-card"
                  onClick={() => navigate(`/app-builder/${app.id}`)}
                >
                  <div className="project-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <LayoutTemplate size={20} color="var(--primary-color)" />
                      <h3 style={{ margin: 0 }}>{app.title || '제목 없는 앱'}</h3>
                    </div>
                    <button
                      onClick={(e) => handleDeleteApp(e, app.id)}
                      className="icon-btn danger-btn"
                      style={{ padding: '0.25rem', background: 'transparent', border: 'none', cursor: 'pointer', color: '#ef4444' }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                  <div className="project-card-body">
                    <p className="project-desc" style={{ color: 'var(--text-muted)' }}>
                      {app.description || `ID: ${app.id.substring(0, 8)}...`}
                    </p>
                  </div>
                  <div className="project-card-footer">
                    <div className="footer-left">
                      <Clock size={12} /> 
                      <span>{new Date(app.created_at).toLocaleDateString()}</span>
                    </div>
                    <div className="footer-right">
                      <ChevronRight size={16} />
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default CustomAppsDashboardPage;
