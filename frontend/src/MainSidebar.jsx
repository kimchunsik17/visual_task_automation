import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';
import { useAuth } from './AuthContext';
import { Wand2, Home, LayoutGrid, LibraryBig, Settings, Bot, BarChart, Clock } from 'lucide-react';
import './MainSidebar.css';

const MainSidebar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, login, logout, token } = useAuth();
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    if (!token) return;
    const fetchCount = async () => {
      try {
        const res = await axios.get('/api/friends/pending-count', { headers: { Authorization: `Bearer ${token}` } });
        setPendingCount(res.data.count);
      } catch (e) {/* silent */}
    };
    fetchCount();
    const interval = setInterval(fetchCount, 5000);
    return () => clearInterval(interval);
  }, [token]);

  const handleGoogleSuccess = async (credentialResponse) => {
    try {
      const res = await axios.post('/api/auth/google', {
        token: credentialResponse.credential,
      });
      login(res.data.user, res.data.access_token);
    } catch (error) {
      console.error('Login failed:', error);
      alert('로그인 처리 중 에러가 발생했습니다: ' + (error.response?.data?.detail || error.message));
    }
  };

  return (
    <aside className="main-sidebar">
      <div className="main-sidebar-header">
        <Wand2 size={24} color="#60a5fa" />
        <span className="brand-name">Auto Flow</span>
      </div>

      <nav className="main-nav">
        <button className={`nav-item ${location.pathname === '/' ? 'active' : ''}`} onClick={() => navigate('/')}>
          <Home size={18} /> 홈
        </button>
        <button className={`nav-item ${location.pathname === '/workflows' ? 'active' : ''}`} onClick={() => navigate('/workflows')}>
          <LayoutGrid size={18} /> 내 워크플로우
        </button>
        <button className={`nav-item ${location.pathname === '/templates' ? 'active' : ''}`} onClick={() => navigate('/templates')}>
          <LibraryBig size={18} /> 커뮤니티 템플릿
        </button>
        <button className={`nav-item ${location.pathname === '/bots' ? 'active' : ''}`} onClick={() => navigate('/bots')}>
          <Bot size={18} /> 봇 관리
        </button>
        <button className={`nav-item ${location.pathname === '/scheduler' ? 'active' : ''}`} onClick={() => navigate('/scheduler')}>
          <Clock size={18} /> 스케줄 관리
        </button>
        <button className={`nav-item ${location.pathname === '/statistics' ? 'active' : ''}`} onClick={() => navigate('/statistics')}>
          <BarChart size={18} /> 통계
        </button>
        <div className="nav-divider"></div>
        <button className={`nav-item ${location.pathname === '/settings' ? 'active' : ''}`} onClick={() => navigate('/settings')} style={{ position: 'relative' }}>
          <Settings size={18} /> 설정
          {pendingCount > 0 && (
            <span style={{
              position: 'absolute',
              top: '6px',
              right: '8px',
              background: '#ef4444',
              color: '#fff',
              borderRadius: '50%',
              width: '18px',
              height: '18px',
              fontSize: '0.7rem',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              animation: 'pulse-opacity 2s ease-in-out infinite'
            }}>
              {pendingCount}
            </span>
          )}
        </button>
      </nav>

      <div className="main-sidebar-footer">
        {user ? (
          <div className="user-profile-vertical">
            <img src={user.picture} alt="Profile" className="profile-pic-large" />
            <div className="user-info">
              <span className="user-name">{user.name}</span>
              <span className="user-email">{user.email || 'user@example.com'}</span>
            </div>
            <button onClick={logout} className="btn-logout">로그아웃</button>
          </div>
        ) : (
          <div className="login-container">
            <p className="login-hint">로그인하여 워크플로우를 저장하세요</p>
            <GoogleLogin
              onSuccess={handleGoogleSuccess}
              onError={() => {
                console.log('Login Failed');
              }}
            />
          </div>
        )}
      </div>
    </aside>
  );
};

export default MainSidebar;

