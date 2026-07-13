import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';
import { useAuth } from './AuthContext';
import { Wand2, Home, LayoutGrid, LibraryBig, Settings, Bot } from 'lucide-react';
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
      alert('ë¡œê·¸??ì²˜ë¦¬ ì¤??ëŸ¬ê°€ ë°œìƒ?ˆìŠµ?ˆë‹¤: ' + (error.response?.data?.detail || error.message));
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
          <Home size={18} /> ??
        </button>
        <button className={`nav-item ${location.pathname === '/workflows' ? 'active' : ''}`} onClick={() => navigate('/workflows')}>
          <LayoutGrid size={18} /> ???Œí¬?Œë¡œ??
        </button>
        <button className={`nav-item ${location.pathname === '/templates' ? 'active' : ''}`} onClick={() => navigate('/templates')}>
          <LibraryBig size={18} /> ì»¤ë??ˆí‹° ?œí”Œë¦?
        </button>
        <button className={`nav-item ${location.pathname === '/bots' ? 'active' : ''}`} onClick={() => navigate('/bots')}>
          <Bot size={18} /> ë´?ê´€ë¦?
        </button>
        <div className="nav-divider"></div>
        <button className={`nav-item ${location.pathname === '/settings' ? 'active' : ''}`} onClick={() => navigate('/settings')}>
          <Settings size={18} /> ?¤ì •
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
            <button onClick={logout} className="btn-logout">ë¡œê·¸?„ì›ƒ</button>
          </div>
        ) : (
          <div className="login-container">
            <p className="login-hint">ë¡œê·¸?¸í•˜???Œí¬?Œë¡œ?°ë? ?€?¥í•˜?¸ìš”</p>
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
