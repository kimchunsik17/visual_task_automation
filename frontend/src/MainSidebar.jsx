import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';
import { useAuth } from './AuthContext';
import { Grid2X2, History, LogOut, Menu, User, X } from 'lucide-react';
import { Icon } from './icons';
import ChatSidebar from './ChatSidebar';
import { readMainSidebarPanel, writeMainSidebarPanel } from './mainSidebarState';
import logoImg from './logo.png';
import './MainSidebar.css';

// 1차 내비게이션 정본 (HOME_SIDEBAR_INFORMATION_ARCHITECTURE_PLAN §1·§4).
// 웹훅·봇·스케줄은 "운영"으로, API 센터는 설정 하위로, 커뮤니티 템플릿은 커뮤니티로 묶였다 —
// 하위 페이지 이동은 각 섹션 상단의 SectionTabs(navigation.js)가 담당한다.
const NAV_GROUPS = [
  {
    label: '제작',
    items: [
      { id: 'home', label: '홈', icon: 'nav-home', path: '/', match: (p) => p === '/' },
      { id: 'workflows', label: '내 워크플로우', icon: 'nav-workflows', path: '/workflows', match: (p) => p === '/workflows' },
      { id: 'app-builder', label: '앱 빌더', icon: 'nav-app-builder', path: '/custom-apps', match: (p) => p.startsWith('/custom-apps') || p.startsWith('/app-builder') },
      { id: 'tutorial', label: '튜토리얼', icon: 'nav-tutorial', path: '/tutorial', match: (p) => p.startsWith('/tutorial') || p.startsWith('/documents') },
    ],
  },
  {
    label: '관리 및 탐색',
    items: [
      { id: 'operations', label: '운영', icon: 'nav-scheduler', path: '/operations', match: (p) => p.startsWith('/operations') },
      { id: 'community', label: '커뮤니티', icon: 'nav-templates', path: '/community/qna', match: (p) => p.startsWith('/community') },
      { id: 'messages', label: '쪽지', icon: 'nav-messages', path: '/messages', match: (p) => p.startsWith('/messages') },
      { id: 'statistics', label: '통계', icon: 'nav-statistics', path: '/statistics', match: (p) => p === '/statistics' },
    ],
  },
  {
    label: '계정 및 도움말',
    items: [
      { id: 'approvals', label: '승인 대기함', icon: 'node-human-approval', path: '/approvals', match: (p) => p === '/approvals', badge: 'approvals' },
      { id: 'settings', label: '설정', icon: 'nav-settings', path: '/settings/profile', match: (p) => p.startsWith('/settings'), badge: 'friends' },
      { id: 'patch-notes', label: '패치 노트', icon: 'nav-patch-notes', path: '/patch-notes', match: (p) => p === '/patch-notes' },
      { id: 'intro', label: '서비스 소개', icon: 'nav-intro', path: '/intro', match: (p) => p === '/intro' },
    ],
  },
];

const MainSidebar = ({ onSelectSession, currentChatSessionId, onChatSessionDeleted }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, login, logout, token } = useAuth();
  const sidebarStorage = typeof window !== 'undefined' ? window.sessionStorage : null;
  const [pendingCount, setPendingCount] = useState(0);
  const [approvalCount, setApprovalCount] = useState(0);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  // 사이드바 안의 탭. 예전에는 사이드바가 둘이었고 한쪽을 누르면 다른 쪽이 접혔는데,
  // 접힌 상태의 위계가 불안정하고 가로 공간을 늘 두 벌 차지했다 — 하나로 합치고 탭으로 나눈다.
  const [panel, setPanel] = useState(() => readMainSidebarPanel(sidebarStorage)); // 'menu' | 'chat'
  // 운영 권한은 서버가 판단한다(ADR-0020) — moderator 도 검수 화면이 필요하므로 is_admin 만으로는 부족하다.
  const [isStaff, setIsStaff] = useState(false);
  const selectPanel = (nextPanel) => {
    const normalized = writeMainSidebarPanel(sidebarStorage, nextPanel);
    setPanel(normalized);
  };
  const selectChatSession = (session) => {
    setIsMobileOpen(false);
    if (onSelectSession) onSelectSession(session);
    else navigate('/', { state: { session } });
  };
  const startNewChat = () => {
    setIsMobileOpen(false);
    navigate('/', { state: { newChat: true } });
  };

  useEffect(() => {
    if (!token) { setIsStaff(false); return; }
    axios.get('/api/community/me', { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => setIsStaff(Boolean(res.data?.isStaff)))
      .catch(() => setIsStaff(false));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    const fetchCount = async () => {
      try {
        const res = await axios.get('/api/friends/pending-count', { headers: { Authorization: `Bearer ${token}` } });
        setPendingCount(res.data.count);
      } catch (e) {/* silent */ }
      try {
        const res = await axios.get('/api/approvals/count', { headers: { Authorization: `Bearer ${token}` } });
        setApprovalCount(res.data.count);
      } catch (e) {/* silent */ }
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
      alert('로그인 처리 중 에러가 발생했습니다: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  return (
    <>
      <button
        className="mobile-sidebar-toggle"
        onClick={() => setIsMobileOpen(true)}
      >
        <Menu size={24} />
      </button>

      {isMobileOpen && (
        <div className="mobile-sidebar-overlay" onClick={() => setIsMobileOpen(false)}></div>
      )}

      <div className={`mobile-sidebar-wrapper ${isMobileOpen ? 'mobile-open' : ''}`}>
          <aside className="main-sidebar">
            <div className="main-sidebar-header">
              <button type="button" className="sidebar-brand" onClick={() => navigate('/')} aria-label="홈으로 이동">
                <img src={logoImg} alt="WorkFlow Ai" className="brand-logo" />
                <span className="brand-name logo-container">
                  <span className="text-workflow">WorkFlow</span>
                  <span className="text-ai">&nbsp;Ai</span>
                </span>
              </button>
              <button className="sidebar-close" onClick={() => setIsMobileOpen(false)} aria-label="사이드바 닫기">
                <X size={18} />
              </button>
            </div>

            {/* 하위 탭. 대화 기록이 여기로 들어오면서 사이드바가 하나로 줄었다. */}
            <div className="sidebar-tabs" role="tablist" aria-label="사이드바 탭">
              {[
                ['menu', '메뉴', Grid2X2],
                ['chat', '대화 기록', History],
              ].map(([id, label, TabIcon]) => (
                <button key={id} type="button" role="tab" aria-selected={panel === id}
                        className={`sidebar-tab ${panel === id ? 'active' : ''}`}
                        onClick={() => selectPanel(id)}>
                  <TabIcon size={14} /> {label}
                </button>
              ))}
            </div>

        {panel === 'chat' ? (
          <ChatSidebar onSelectSession={selectChatSession} currentSessionId={currentChatSessionId}
                       onSessionDeleted={onChatSessionDeleted} onStartNewChat={startNewChat} />
        ) : (
        <nav className="main-nav">
          {NAV_GROUPS.map((group, groupIndex) => (
            <React.Fragment key={group.label}>
              {groupIndex > 0 && <div className="nav-divider"></div>}
              <div className="nav-group-label">{group.label}</div>
              {group.items.map((item) => {
                const active = item.match(location.pathname);
                const badgeCount = item.badge === 'approvals' ? approvalCount
                  : item.badge === 'friends' ? pendingCount : 0;
                return (
                  <button
                    key={item.id}
                    className={`nav-item ${active ? 'active' : ''}`}
                    onClick={() => navigate(item.path)}
                    style={badgeCount > 0 ? { position: 'relative' } : undefined}
                  >
                    <span className="nav-item-icon"><Icon name={item.icon} size={17} /></span>
                    <span>{item.label}</span>
                    {badgeCount > 0 && (
                      <span style={{
                        position: 'absolute', top: '6px', right: '8px',
                        background: item.badge === 'approvals' ? '#f59e0b' : '#ef4444',
                        color: '#fff', borderRadius: '50%', width: '18px', height: '18px',
                        fontSize: '0.65rem', fontWeight: 700,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        ...(item.badge === 'friends' ? { animation: 'pulse-opacity 2s ease-in-out infinite' } : {}),
                      }}>{badgeCount > 9 ? '9+' : badgeCount}</span>
                    )}
                  </button>
                );
              })}
            </React.Fragment>
          ))}
          <div className="nav-divider"></div>
          {/* moderator와 admin 모두 같은 운영 콘솔을 사용하되, 콘솔 안에서 권한별 섹션을 나눈다. */}
          {(isStaff || user?.is_admin) && (
            <button className={`nav-item ${location.pathname.startsWith('/admin') ? 'active' : ''}`}
                    onClick={() => navigate(user?.is_admin ? '/admin' : '/admin/moderation')}>
              <span className="nav-item-icon"><Icon name="nav-admin" size={17} /></span>
              <span>{user?.is_admin ? '어드민 패널' : '운영자 콘솔'}</span>
            </button>
          )}
        </nav>
        )}

        <div className="main-sidebar-footer">
          {user ? (
            <div className="user-profile-vertical">
              {user.picture ? <img src={user.picture} alt="" className="profile-pic-large" />
                : <span className="profile-pic-fallback">{(user.name || '?').slice(0, 1).toUpperCase()}</span>}
              <div className="user-info">
                <span className="user-name">{user.name}</span>
                <span className="user-email">{user.email || 'user@example.com'}</span>
              </div>
              <button onClick={logout} className="btn-logout" title="로그아웃" aria-label="로그아웃"><LogOut size={15} /></button>
            </div>
          ) : (
            <>
              <div className="login-container">
                <p className="login-hint">로그인하여 워크플로우를 저장하세요</p>
                <GoogleLogin
                  onSuccess={handleGoogleSuccess}
                  onError={() => {
                    console.log('Login Failed');
                  }}
                />
              </div>
              <div className="login-collapsed-icon">
                <User size={24} color="var(--text-muted)" />
              </div>
            </>
          )}
        </div>
      </aside>
      </div>
    </>
  );
};

export default MainSidebar;
