import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { Settings, User, Palette, DollarSign, AlertTriangle, Users, UserPlus, UserMinus, UserCheck, UserX, Clock, PlayCircle, ShieldCheck , Key } from 'lucide-react';
import MainSidebar from '../MainSidebar';
import { useAuth } from '../AuthContext';
import { customConfirm } from '../CustomConfirm';
import { resetOnboardingProgress } from '../onboardingProgress';
import { resetTutorialLearningProgress } from '../tutorialProgress';
import './MainPage.css';

function SettingsPage() {
  const { user, token, logout } = useAuth();
  const navigate = useNavigate();
  // 탭은 URL(/settings/:tab)이 정본이다(IA 계획 §3.2) — 새로고침·뒤로가기·직접 링크가
  // 탭 상태와 일치하고, API 센터도 같은 체계(/settings/api-center)로 들어온다.
  const { tab: tabParam } = useParams();
  const VALID_TABS = ['profile', 'friends', 'appearance', 'tokens', 'privacy'];
  const activeTab = VALID_TABS.includes(tabParam) ? tabParam : 'profile';
  const setActiveTab = (id) => navigate(id === 'api-center' ? '/settings/api-center' : `/settings/${id}`);
  const [theme, setTheme] = useState(document.documentElement.getAttribute('data-theme') || 'dark');
  const [tokenDisplayMode, setTokenDisplayMode] = useState(localStorage.getItem('tokenDisplayMode') || 'tokens');
  const [costCurrency, setCostCurrency] = useState(localStorage.getItem('costCurrency') || 'USD');
  const [trainingConsent, setTrainingConsent] = useState(localStorage.getItem('llmTrainingConsent') === 'true');
  const [friends, setFriends] = useState([]);
  const [friendRequests, setFriendRequests] = useState([]);
  // 친구 찾기는 핸들 기반이다(ADR-0020). 이메일로 찾으면 이메일만 알아도 계정 존재 여부가
  // 확인돼(계정 열거), 커뮤니티가 열리는 순간 스팸의 입구가 된다.
  const [newFriendHandle, setNewFriendHandle] = useState('');
  const [greeting, setGreeting] = useState('');
  const [requestStatus, setRequestStatus] = useState(null);
  // 커뮤니티 프로필(핸들). 없으면 여기서 만든다 — 핸들은 백필하지 않고 커뮤니티에 처음
  // 들어올 때 만들기 때문에(ADR-0020), 지금은 이 화면이 그 첫 진입점이다.
  const [community, setCommunity] = useState(null);
  const [handleInput, setHandleInput] = useState('');
  const [handleStatus, setHandleStatus] = useState(null);

  useEffect(() => {
    if (token) { loadFriends(); loadFriendRequests(); loadCommunity(); }
  }, [token]);

  const loadFriends = async () => {
    try {
      const res = await axios.get('/api/friends', { headers: { Authorization: `Bearer ${token}` } });
      setFriends(res.data);
    } catch (e) { console.error('Failed to load friends', e); }
  };

  const loadCommunity = async () => {
    try {
      const res = await axios.get('/api/community/me', { headers: { Authorization: `Bearer ${token}` } });
      setCommunity(res.data);
      if (res.data.needsProfile) setHandleInput(res.data.suggestedHandle || '');
    } catch (e) { console.error('Failed to load community profile', e); }
  };

  const handleCreateProfile = async () => {
    if (!handleInput.trim()) return;
    try {
      await axios.post('/api/community/profile', { handle: handleInput.trim().replace(/^@/, '') },
                       { headers: { Authorization: `Bearer ${token}` } });
      setHandleStatus(null);
      loadCommunity();
    } catch (e) {
      setHandleStatus(e.response?.data?.detail || '핸들을 만들지 못했습니다.');
    }
  };

  const loadFriendRequests = async () => {
    try {
      const res = await axios.get('/api/friends/requests', { headers: { Authorization: `Bearer ${token}` } });
      setFriendRequests(res.data);
    } catch (e) { console.error('Failed to load friend requests', e); }
  };

  const handleSendRequest = async () => {
    if (!newFriendHandle) return;
    try {
      const res = await axios.post(
        '/api/friends/request',
        { handle: newFriendHandle.trim().replace(/^@/, ''), greeting },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setNewFriendHandle('');
      setGreeting('');
      setRequestStatus({ type: 'success', msg: res.data.message });
      setTimeout(() => setRequestStatus(null), 4000);
    } catch (e) {
      setRequestStatus({ type: 'error', msg: e.response?.data?.detail || '친구 신청 실패' });
      setTimeout(() => setRequestStatus(null), 4000);
    }
  };

  const handleAccept = async (requestId) => {
    try {
      await axios.post(`/api/friends/requests/${requestId}/accept`, {}, { headers: { Authorization: `Bearer ${token}` } });
      loadFriends(); loadFriendRequests();
    } catch (e) { alert('수락 실패'); }
  };

  const handleReject = async (requestId) => {
    try {
      await axios.post(`/api/friends/requests/${requestId}/reject`, {}, { headers: { Authorization: `Bearer ${token}` } });
      loadFriendRequests();
    } catch (e) { alert('거절 실패'); }
  };

  const handleThemeChange = (newTheme) => {
    setTheme(newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
  };

  const handleDisplayModeChange = (mode) => {
    setTokenDisplayMode(mode);
    localStorage.setItem('tokenDisplayMode', mode);
  };

  const handleCurrencyChange = (currency) => {
    setCostCurrency(currency);
    localStorage.setItem('costCurrency', currency);
  };

  const handleTrainingConsentChange = async (enabled) => {
    setTrainingConsent(enabled);
    localStorage.setItem('llmTrainingConsent', String(enabled));
    if (!enabled && token) {
      try {
        await axios.delete('/api/training-data/me', {
          headers: { Authorization: `Bearer ${token}` }
        });
      } catch (error) {
        console.error('Failed to delete training data:', error);
        alert('기존 학습 데이터를 삭제하지 못했습니다. 잠시 후 다시 시도해주세요.');
      }
    }
  };

  const handleReplayTutorial = (page) => {
    if (page === 'main') {
      localStorage.removeItem('tutorial_main_seen_v1');
      navigate('/');
    } else if (page === 'editor') {
      localStorage.removeItem('tutorial_editor_seen_v1');
      navigate('/editor');
    } else if (page === 'learning') {
      resetTutorialLearningProgress();
      navigate('/tutorial');
    } else {
      resetOnboardingProgress();
      navigate('/');
    }
  };

  const handleDeleteAccount = async () => {
    const confirmDelete = await customConfirm("정말로 탈퇴하시겠습니까? 모든 프로젝트와 데이터가 완전히 삭제되며 복구할 수 없습니다.");
    if (!confirmDelete) return;
    try {
      await axios.delete('/api/users/me', { headers: { Authorization: `Bearer ${token}` } });
      alert('회원 탈퇴가 완료되었습니다.');
      logout();
      navigate('/');
    } catch (error) {
      alert('회원 탈퇴 처리 중 오류가 발생했습니다: ' + (error.response?.data?.detail || error.message));
    }
  };

  const tabs = [
    { id: 'profile', label: '프로필', icon: <User size={16} /> },
    { id: 'friends', label: '친구', icon: <Users size={16} />, badge: friendRequests.length },
    { id: 'appearance', label: '화면', icon: <Palette size={16} /> },
    { id: 'tokens', label: '토큰', icon: <DollarSign size={16} /> },
    { id: 'privacy', label: '데이터', icon: <ShieldCheck size={16} /> },
    { id: 'api-center', label: 'API 센터', icon: <Key size={16} /> },
  ];

  const card = { background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '1.5rem', boxShadow: 'var(--card-shadow)' };

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <div className="dashboard-grid">
          <section>
            <div className="section-header">
              <h3><Settings size={22} color="var(--text-muted)" /> 설정</h3>
            </div>

            {/* 탭 네비게이션 */}
            <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '1.75rem', background: 'var(--card-bg)', padding: '0.35rem', borderRadius: '10px', border: '1px solid var(--border-color)', width: 'fit-content' }}>
              {tabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '0.4rem',
                    padding: '0.5rem 1.1rem', borderRadius: '7px', border: 'none', cursor: 'pointer',
                    background: activeTab === tab.id ? 'var(--primary-color, #3b82f6)' : 'transparent',
                    color: activeTab === tab.id ? '#fff' : 'var(--text-muted)',
                    fontWeight: activeTab === tab.id ? 600 : 400,
                    fontSize: '0.9rem', transition: 'all 0.2s',
                  }}
                >
                  {tab.icon}
                  {tab.label}
                  {tab.badge > 0 && (
                    <span style={{ background: '#ef4444', color: '#fff', borderRadius: '50%', width: '17px', height: '17px', fontSize: '0.65rem', fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                      {tab.badge}
                    </span>
                  )}
                </button>
              ))}
            </div>

            <div style={{ maxWidth: '800px', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

              {/* ─── 프로필 탭 ─── */}
              {activeTab === 'profile' && (
                <div style={card}>
                  <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'var(--text-color)' }}>
                    <User size={18} color="#60a5fa" /> 계정 정보
                  </h4>
                  {user ? (
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginTop: '1rem', flexWrap: 'wrap', gap: '1rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
                        <img src={user.picture} alt="Profile" style={{ width: '64px', height: '64px', borderRadius: '50%', border: '2px solid var(--border-color)' }} />
                        <div>
                          <p style={{ margin: '0 0 0.4rem 0', color: 'var(--text-color)', fontWeight: 600, fontSize: '1.1rem' }}>{user.name}</p>
                          <p style={{ margin: 0, color: 'var(--text-muted)' }}>{user.email}</p>
                        </div>
                      </div>
                      <button
                        onClick={handleDeleteAccount}
                        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', background: '#ef444420', color: '#ef4444', border: '1px solid #ef4444', borderRadius: '6px', cursor: 'pointer', transition: 'all 0.2s', fontSize: '0.9rem', fontWeight: 500 }}
                        onMouseOver={(e) => { e.currentTarget.style.background = '#ef4444'; e.currentTarget.style.color = '#ffffff'; }}
                        onMouseOut={(e) => { e.currentTarget.style.background = '#ef444420'; e.currentTarget.style.color = '#ef4444'; }}
                      >
                        <AlertTriangle size={16} /> 회원 탈퇴
                      </button>
                    </div>
                  ) : (
                    <p style={{ color: 'var(--text-muted)', margin: '1rem 0 0 0' }}>로그인이 필요합니다.</p>
                  )}
                </div>
              )}

              {/* ─── 친구 탭 ─── */}
              {activeTab === 'friends' && (
                <div style={card}>
                  <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'var(--text-color)' }}>
                    <Users size={18} color="#10b981" /> 친구 관리
                  </h4>

                  {/* 내 핸들 — 없으면 여기서 만든다(ADR-0020 SAFE-1) */}
                  {community?.needsProfile ? (
                    <div style={{ padding: '1rem', background: 'var(--bg-color)', border: '1px solid var(--border-color)', borderRadius: '8px', marginBottom: '1rem' }}>
                      <p style={{ margin: '0 0 0.5rem 0', fontWeight: 600, color: 'var(--text-color)' }}>먼저 핸들을 만들어주세요</p>
                      <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                        핸들은 커뮤니티에서 쓰이는 공개 이름입니다. 이메일은 공개되지 않아요.
                        소문자·숫자·하이픈으로 3~20자.
                      </p>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                          type="text"
                          value={handleInput}
                          onChange={(e) => setHandleInput(e.target.value)}
                          placeholder="예: minsu-kim"
                          style={{ flex: 1, padding: '0.6rem 1rem', background: 'var(--card-bg, transparent)', border: '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '6px', outline: 'none' }}
                          onKeyDown={(e) => e.key === 'Enter' && handleCreateProfile()}
                        />
                        <button className="btn-primary" onClick={handleCreateProfile} style={{ padding: '0.6rem 1rem', whiteSpace: 'nowrap' }}>
                          핸들 만들기
                        </button>
                      </div>
                      {handleStatus && (
                        <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.85rem', color: '#ef4444' }}>{handleStatus}</p>
                      )}
                    </div>
                  ) : community?.profile ? (
                    <p style={{ margin: '0 0 1rem 0', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                      내 핸들: <strong style={{ color: 'var(--text-color)' }}>@{community.profile.handle}</strong>
                      {' '}— 친구가 이 이름으로 나를 찾습니다.
                    </p>
                  ) : null}

                  {/* 친구 신청 보내기 */}
                  <div style={{ marginTop: '1rem', marginBottom: '1.5rem' }}>
                    <p style={{ color: 'var(--text-muted)', marginBottom: '0.75rem', fontSize: '0.9rem' }}>
                      핸들로 친구 신청을 보내세요. 상대방이 수락하면 '친구공개' 앱을 함께 사용할 수 있습니다.
                      <br />
                      <span style={{ fontSize: '0.85rem' }}>
                        상대가 커뮤니티에 참여하며 만든 핸들이 필요합니다. 아직 참여하지 않은 사용자는 찾을 수 없어요.
                      </span>
                    </p>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <input
                        type="text"
                        placeholder="@핸들 입력 (예: minsu-kim)"
                        value={newFriendHandle}
                        onChange={(e) => setNewFriendHandle(e.target.value)}
                        style={{ flex: 1, padding: '0.6rem 1rem', background: 'var(--bg-color)', border: '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '6px', outline: 'none' }}
                        onKeyDown={(e) => e.key === 'Enter' && handleSendRequest()}
                      />
                      <button className="btn-primary" onClick={handleSendRequest} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1rem', whiteSpace: 'nowrap' }}>
                        <UserPlus size={16} /> 신청 보내기
                      </button>
                    </div>
                    {/* 한 줄 인사말. 쪽지가 친구 한정이라 이 요청이 대화의 유일한 입구다 —
                        맥락 없는 요청은 그대로 수락률로 이어진다. */}
                    <input
                      type="text"
                      placeholder="인사말 (선택) — 어디서 봤는지 적으면 수락률이 올라갑니다"
                      value={greeting}
                      maxLength={200}
                      onChange={(e) => setGreeting(e.target.value)}
                      style={{ width: '100%', marginTop: '0.5rem', padding: '0.5rem 1rem', background: 'var(--bg-color)', border: '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '6px', outline: 'none', fontSize: '0.85rem' }}
                      onKeyDown={(e) => e.key === 'Enter' && handleSendRequest()}
                    />
                    {requestStatus && (
                      <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.85rem', color: requestStatus.type === 'success' ? '#10b981' : '#ef4444' }}>
                        {requestStatus.msg}
                      </p>
                    )}
                  </div>

                  {/* 받은 친구 신청 */}
                  {friendRequests.length > 0 && (
                    <div style={{ marginBottom: '1.5rem' }}>
                      <h5 style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', margin: '0 0 0.75rem 0', color: '#f59e0b', fontSize: '0.95rem' }}>
                        <Clock size={15} /> 받은 친구 신청
                        <span style={{ background: '#ef4444', color: '#fff', borderRadius: '50%', width: '20px', height: '20px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700 }}>{friendRequests.length}</span>
                      </h5>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                        {friendRequests.map(req => (
                          <div key={req.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.8rem 1rem', background: 'rgba(245, 158, 11, 0.07)', border: '1px solid rgba(245, 158, 11, 0.25)', borderRadius: '8px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                              <img src={req.picture || 'https://ui-avatars.com/api/?name=' + encodeURIComponent(req.name)} alt="" style={{ width: '36px', height: '36px', borderRadius: '50%' }} />
                              <div>
                                <p style={{ margin: 0, fontWeight: 600, color: 'var(--text-color)', fontSize: '0.95rem' }}>{req.name}</p>
                                <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>{req.email}</p>
                              </div>
                            </div>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                              <button onClick={() => handleAccept(req.id)} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', padding: '0.4rem 0.8rem', background: 'rgba(16,185,129,0.1)', color: '#10b981', border: '1px solid rgba(16,185,129,0.3)', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600 }}>
                                <UserCheck size={15} /> 수락
                              </button>
                              <button onClick={() => handleReject(req.id)} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', padding: '0.4rem 0.8rem', background: 'rgba(239,68,68,0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600 }}>
                                <UserX size={15} /> 거절
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 친구 목록 */}
                  <div>
                    <h5 style={{ margin: '0 0 0.75rem 0', color: 'var(--text-muted)', fontSize: '0.85rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>친구 목록 ({friends.length})</h5>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                      {friends.length === 0 ? (
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', padding: '1rem 0' }}>등록된 친구가 없습니다.</p>
                      ) : (
                        friends.map(friend => (
                          <div key={friend.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.8rem 1rem', background: 'var(--bg-color)', border: '1px solid var(--border-color)', borderRadius: '8px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                              <img src={friend.picture || 'https://ui-avatars.com/api/?name=' + encodeURIComponent(friend.name)} alt="" style={{ width: '36px', height: '36px', borderRadius: '50%' }} />
                              <div>
                                <p style={{ margin: 0, fontWeight: 500, color: 'var(--text-color)' }}>{friend.name}</p>
                                <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                  {friend.profile?.handle ? `@${friend.profile.handle}` : '커뮤니티 미참여'}
                                </p>
                              </div>
                            </div>
                            <button onClick={async () => {
                              const ok = await customConfirm(`${friend.name}님을 친구 목록에서 삭제할까요?`);
                              if (ok) axios.delete(`/api/friends/${friend.id}`, { headers: { Authorization: `Bearer ${token}` } }).then(loadFriends);
                            }} style={{ background: 'transparent', border: 'none', color: '#ef4444', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.85rem', padding: '0.3rem 0.5rem', borderRadius: '4px' }}>
                              <UserMinus size={15} /> 삭제
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* ─── 화면 탭 ─── */}
              {activeTab === 'appearance' && (
                <div style={card}>
                  <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'var(--text-color)' }}>
                    <Palette size={18} color="#c084fc" /> 테마 설정
                  </h4>
                  <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
                    <button
                      className="btn-secondary"
                      style={{ flex: 1, height: 'auto', padding: '1.5rem', background: theme === 'dark' ? 'var(--btn-active-bg)' : 'transparent', border: theme === 'dark' ? '2px solid #60a5fa' : '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '10px', transition: 'all 0.3s', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.6rem' }}
                      onClick={() => handleThemeChange('dark')}
                    >
                      <span style={{ fontSize: '2rem' }}>🌙</span>
                      <span style={{ fontWeight: 600 }}>다크 모드</span>
                    </button>
                    <button
                      className="btn-secondary"
                      style={{ flex: 1, height: 'auto', padding: '1.5rem', background: theme === 'light' ? 'var(--btn-active-bg)' : 'transparent', border: theme === 'light' ? '2px solid #60a5fa' : '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '10px', transition: 'all 0.3s', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.6rem' }}
                      onClick={() => handleThemeChange('light')}
                    >
                      <span style={{ fontSize: '2rem' }}>☀️</span>
                      <span style={{ fontWeight: 600 }}>라이트 모드</span>
                    </button>
                  </div>
                </div>
              )}

              {/* ─── 튜토리얼 다시보기 ─── */}
              {activeTab === 'appearance' && (
                <div style={card}>
                  <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'var(--text-color)' }}>
                    <PlayCircle size={18} color="#60a5fa" /> 튜토리얼
                  </h4>
                  <p style={{ color: 'var(--text-muted)', margin: '0.5rem 0 1rem 0', fontSize: '0.9rem' }}>
                    처음 접속했을 때 나왔던 안내를 다시 볼 수 있어요.
                  </p>
                  <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                    <button className="btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1rem' }} onClick={() => handleReplayTutorial('learning')}>
                      <PlayCircle size={16} /> 학습 센터 진도 초기화
                    </button>
                    <button className="btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1rem' }} onClick={() => handleReplayTutorial('onboarding')}>
                      <PlayCircle size={16} /> 시작 체크리스트 초기화
                    </button>
                    <button className="btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1rem' }} onClick={() => handleReplayTutorial('main')}>
                      <PlayCircle size={16} /> 메인 페이지 튜토리얼 다시보기
                    </button>
                    <button className="btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1rem' }} onClick={() => handleReplayTutorial('editor')}>
                      <PlayCircle size={16} /> 에디터 튜토리얼 다시보기
                    </button>
                  </div>
                </div>
              )}

              {/* ─── 토큰 탭 ─── */}
              {activeTab === 'tokens' && (
                <div style={card}>
                  <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'var(--text-color)' }}>
                    <DollarSign size={18} color="#fbbf24" /> 토큰 표시 설정
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
                    <div>
                      <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>표시 방식</label>
                      <div style={{ display: 'flex', gap: '1rem' }}>
                        <button className="btn-secondary" style={{ flex: 1, height: 'auto', padding: '1rem', background: tokenDisplayMode === 'tokens' ? 'var(--btn-active-bg)' : 'transparent', border: tokenDisplayMode === 'tokens' ? '2px solid #60a5fa' : '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '8px', transition: 'all 0.3s' }} onClick={() => handleDisplayModeChange('tokens')}>
                          토큰 수 표시
                        </button>
                        <button className="btn-secondary" style={{ flex: 1, height: 'auto', padding: '1rem', background: tokenDisplayMode === 'cost' ? 'var(--btn-active-bg)' : 'transparent', border: tokenDisplayMode === 'cost' ? '2px solid #60a5fa' : '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '8px', transition: 'all 0.3s' }} onClick={() => handleDisplayModeChange('cost')}>
                          금액 표시
                        </button>
                      </div>
                    </div>
                    {tokenDisplayMode === 'cost' && (
                      <div>
                        <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>화폐 단위</label>
                        <div style={{ display: 'flex', gap: '1rem' }}>
                          <button className="btn-secondary" style={{ flex: 1, height: 'auto', padding: '1rem', background: costCurrency === 'USD' ? 'var(--btn-active-bg)' : 'transparent', border: costCurrency === 'USD' ? '2px solid #60a5fa' : '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '8px', transition: 'all 0.3s' }} onClick={() => handleCurrencyChange('USD')}>
                            달러 (USD)
                          </button>
                          <button className="btn-secondary" style={{ flex: 1, height: 'auto', padding: '1rem', background: costCurrency === 'KRW' ? 'var(--btn-active-bg)' : 'transparent', border: costCurrency === 'KRW' ? '2px solid #60a5fa' : '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '8px', transition: 'all 0.3s' }} onClick={() => handleCurrencyChange('KRW')}>
                            원화 (KRW)
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'privacy' && (
                <div style={card}>
                  <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'var(--text-color)' }}>
                    <ShieldCheck size={18} color="#10b981" /> AI 학습 데이터
                  </h4>
                  <label style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', marginTop: '1rem', cursor: 'pointer' }}>
                    <span>
                      <strong style={{ display: 'block', color: 'var(--text-color)', marginBottom: '0.35rem' }}>품질 개선 데이터 제공</strong>
                      <span style={{ display: 'block', color: 'var(--text-muted)', fontSize: '0.9rem', lineHeight: 1.55 }}>
                        동의 이후 생성한 요청과 채택된 워크플로우만 수집 대상이 됩니다. API 키, 토큰, 이메일과 UI 상태는 저장 전에 제거됩니다.
                      </span>
                    </span>
                    <input
                      type="checkbox"
                      checked={trainingConsent}
                      onChange={(event) => handleTrainingConsentChange(event.target.checked)}
                      style={{ width: '20px', height: '20px', marginTop: '0.15rem', accentColor: '#10b981', flexShrink: 0 }}
                    />
                  </label>
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', margin: '1rem 0 0 0', lineHeight: 1.5 }}>
                    이 설정을 끄면 이후 수집이 중단되고 기존 학습 후보도 서버에서 삭제됩니다. 제품 기능에는 영향이 없습니다.
                  </p>
                </div>
              )}

            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;
