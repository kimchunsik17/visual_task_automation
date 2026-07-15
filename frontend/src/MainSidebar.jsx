import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';
import { useAuth } from './AuthContext';
import { Wand2, Home, LayoutGrid, LibraryBig, Settings, Bot, BarChart, Clock } from 'lucide-react';
import './MainSidebar.css';

const MainSidebar = ({ isCollapsed = false, onExpand, onToggleChat }) => {
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
    <aside 
      className={`main-sidebar ${isCollapsed ? 'collapsed' : ''}`} 
      onClick={(e) => {
        // 만약 축소된 상태에서 내비게이션 아이템이 아닌 바깥 영역이나 아이콘을 누르면 확장
        if (isCollapsed && onExpand) {
          onExpand();
        }
      }}
    >
      <div className="main-sidebar-header">
        <Wand2 size={24} color="#60a5fa" />
        <span className="brand-name">Auto Flow</span>
      </div>

      <nav className="main-nav">
        <button className={`nav-item ${location.pathname === '/' ? 'active' : ''}`} onClick={() => navigate('/')}>
          <Home size={18} /> <span>홈</span>
        </button>
        <button className={`nav-item ${location.pathname === '/workflows' ? 'active' : ''}`} onClick={() => navigate('/workflows')}>
          <LayoutGrid size={18} /> <span>내 워크플로우</span>
        </button>
        <button className={`nav-item ${location.pathname === '/templates' ? 'active' : ''}`} onClick={() => navigate('/templates')}>
          <LibraryBig size={18} /> <span>커뮤니티 템플릿</span>
        </button>
        <button className={`nav-item ${location.pathname === '/bots' ? 'active' : ''}`} onClick={() => navigate('/bots')}>
          <Bot size={18} /> <span>봇 관리</span>
        </button>
        <button className={`nav-item ${location.pathname === '/scheduler' ? 'active' : ''}`} onClick={() => navigate('/scheduler')}>
          <Clock size={18} /> <span>스케줄 관리</span>
        </button>
        <button className={`nav-item ${location.pathname === '/statistics' ? 'active' : ''}`} onClick={() => navigate('/statistics')}>
          <BarChart size={18} /> <span>통계</span>
        </button>
        {onToggleChat && (
          <button className="nav-item" onClick={onToggleChat} style={{ color: '#a78bfa' }}>
            <Wand2 size={18} /> <span>대화 기록</span>
          </button>
        )}
        <div className="nav-divider"></div>
        <button className={`nav-item ${location.pathname === '/settings' ? 'active' : ''}`} onClick={() => navigate('/settings')} style={{ position: 'relative' }}>
          <Settings size={18} /> <span>설정</span>
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

