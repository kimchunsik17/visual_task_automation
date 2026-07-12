import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';
import { useAuth } from './AuthContext';
import { Wand2, Home, LayoutGrid, LibraryBig, Settings } from 'lucide-react';
import './MainSidebar.css';

const MainSidebar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, login, logout } = useAuth();

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
        <div className="nav-divider"></div>
        <button className={`nav-item ${location.pathname === '/settings' ? 'active' : ''}`} onClick={() => navigate('/settings')}>
          <Settings size={18} /> 설정
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
