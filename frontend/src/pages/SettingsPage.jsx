import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Settings, User, Bell, Shield, Palette, DollarSign, AlertTriangle, Users, UserPlus, UserMinus, UserCheck, UserX, Clock } from 'lucide-react';
import MainSidebar from '../MainSidebar';
import { useAuth } from '../AuthContext';
import './MainPage.css';

function SettingsPage() {
  const { user, token, logout } = useAuth();
  const navigate = useNavigate();
  const [theme, setTheme] = useState(document.documentElement.getAttribute('data-theme') || 'dark');
  const [tokenDisplayMode, setTokenDisplayMode] = useState(localStorage.getItem('tokenDisplayMode') || 'tokens');
  const [costCurrency, setCostCurrency] = useState(localStorage.getItem('costCurrency') || 'USD');
  const [friends, setFriends] = useState([]);
  const [friendRequests, setFriendRequests] = useState([]);
  const [newFriendEmail, setNewFriendEmail] = useState('');
  const [requestStatus, setRequestStatus] = useState(null); // { type: 'success'|'error', msg }

  useEffect(() => {
    if (token) {
      loadFriends();
      loadFriendRequests();
    }
  }, [token]);

  const loadFriends = async () => {
    try {
      const res = await axios.get('/api/friends', { headers: { Authorization: `Bearer ${token}` } });
      setFriends(res.data);
    } catch (e) {
      console.error('Failed to load friends', e);
    }
  };

  const loadFriendRequests = async () => {
    try {
      const res = await axios.get('/api/friends/requests', { headers: { Authorization: `Bearer ${token}` } });
      setFriendRequests(res.data);
    } catch (e) {
      console.error('Failed to load friend requests', e);
    }
  };

  const handleSendRequest = async () => {
    if (!newFriendEmail) return;
    try {
      const res = await axios.post('/api/friends/request', { email: newFriendEmail }, { headers: { Authorization: `Bearer ${token}` } });
      setNewFriendEmail('');
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
      loadFriends();
      loadFriendRequests();
    } catch (e) {
      alert('수락 실패');
    }
  };

  const handleReject = async (requestId) => {
    try {
      await axios.post(`/api/friends/requests/${requestId}/reject`, {}, { headers: { Authorization: `Bearer ${token}` } });
      loadFriendRequests();
    } catch (e) {
      alert('거절 실패');
    }
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

  const handleDeleteAccount = async () => {
    const confirmDelete = window.confirm("정말로 탈퇴하시겠습니까? 모든 프로젝트와 데이터가 완전히 삭제되며 복구할 수 없습니다.");
    if (!confirmDelete) return;
    
    try {
      await axios.delete('/api/users/me', {
        headers: { Authorization: `Bearer ${token}` }
      });
      alert('회원 탈퇴가 완료되었습니다.');
      logout();
      navigate('/');
    } catch (error) {
      console.error('Failed to delete account:', error);
      alert('회원 탈퇴 처리 중 오류가 발생했습니다: ' + (error.response?.data?.detail || error.message));
    }
  };

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <div className="dashboard-grid">
          <section>
            <div className="section-header">
              <h3><Settings size={22} color="var(--text-muted)" /> 설정</h3>
            </div>
            
            <div className="settings-container" style={{ display: 'flex', flexDirection: 'column', gap: '2rem', maxWidth: '800px' }}>
              
              <div className="settings-section" style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '1.5rem', backdropFilter: 'blur(10px)', boxShadow: 'var(--card-shadow)' }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'var(--text-color)' }}>
                  <User size={18} color="#60a5fa" /> 계정 정보
                </h4>
                {user ? (
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginTop: '1rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
                      <img src={user.picture} alt="Profile" style={{ width: '64px', height: '64px', borderRadius: '50%', border: '2px solid #334155' }} />
                      <div>
                        <p style={{ margin: '0 0 0.5rem 0', color: 'var(--text-color)', fontWeight: 600, fontSize: '1.1rem' }}>{user.name}</p>
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

              <div className="settings-section" style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '1.5rem', backdropFilter: 'blur(10px)', boxShadow: 'var(--card-shadow)' }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'var(--text-color)' }}>
                  <Palette size={18} color="#c084fc" /> 테마 설정
                </h4>
                <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
                  <button 
                    className="btn-secondary" 
                    style={{ flex: 1, padding: '1rem', background: theme === 'dark' ? 'var(--btn-active-bg)' : 'transparent', border: theme === 'dark' ? '2px solid #60a5fa' : '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '8px', transition: 'all 0.3s' }}
                    onClick={() => handleThemeChange('dark')}
                  >
                    다크 모드
                  </button>
                  <button 
                    className="btn-secondary" 
                    style={{ flex: 1, padding: '1rem', background: theme === 'light' ? 'var(--btn-active-bg)' : 'transparent', border: theme === 'light' ? '2px solid #60a5fa' : '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '8px', transition: 'all 0.3s' }}
                    onClick={() => handleThemeChange('light')}
                  >
                    라이트 모드
                  </button>
                </div>
              </div>

              <div className="settings-section" style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '1.5rem', backdropFilter: 'blur(10px)', boxShadow: 'var(--card-shadow)' }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'var(--text-color)' }}>
                  <Users size={18} color="#10b981" /> 친구 관리
                </h4>

                {/* 친구 신청 보내기 */}
                <div style={{ marginTop: '1rem', marginBottom: '1.5rem' }}>
                  <p style={{ color: 'var(--text-muted)', marginBottom: '0.75rem', fontSize: '0.9rem' }}>
                    이메일로 친구 신청을 보내세요. 상대방이 수락하면 '친구공개' 앱을 함께 사용할 수 있습니다.
                  </p>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <input
                      type="email"
                      placeholder="친구에게 보낼 이메일 입력"
                      value={newFriendEmail}
                      onChange={(e) => setNewFriendEmail(e.target.value)}
                      style={{ flex: 1, padding: '0.6rem 1rem', background: 'var(--bg-color)', border: '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '6px', outline: 'none' }}
                      onKeyDown={(e) => e.key === 'Enter' && handleSendRequest()}
                    />
                    <button className="btn-primary" onClick={handleSendRequest} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1rem', whiteSpace: 'nowrap' }}>
                      <UserPlus size={16} /> 신청 보내기
                    </button>
                  </div>
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
                      <Clock size={15} /> 받은 친구 신청 <span style={{ background: '#ef4444', color: '#fff', borderRadius: '50%', width: '20px', height: '20px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700 }}>{friendRequests.length}</span>
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
                              <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>{friend.email}</p>
                            </div>
                          </div>
                          <button onClick={() => {
                            const ok = window.confirm(`${friend.name}님을 친구 목록에서 삭제할까요?`);
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

              <div className="settings-section" style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '1.5rem', backdropFilter: 'blur(10px)', boxShadow: 'var(--card-shadow)' }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'var(--text-color)' }}>
                  <Bell size={18} color="#f472b6" /> 알림
                </h4>
                <p style={{ color: 'var(--text-muted)', margin: '1rem 0 0 0' }}>새로운 알림이 없습니다.</p>
              </div>

              <div className="settings-section" style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '1.5rem', backdropFilter: 'blur(10px)', boxShadow: 'var(--card-shadow)' }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'var(--text-color)' }}>
                  <DollarSign size={18} color="#fbbf24" /> 토큰 표시 설정
                </h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
                  <div>
                    <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>표시 방식</label>
                    <div style={{ display: 'flex', gap: '1rem' }}>
                      <button 
                        className="btn-secondary" 
                        style={{ flex: 1, padding: '1rem', background: tokenDisplayMode === 'tokens' ? 'var(--btn-active-bg)' : 'transparent', border: tokenDisplayMode === 'tokens' ? '2px solid #60a5fa' : '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '8px', transition: 'all 0.3s' }}
                        onClick={() => handleDisplayModeChange('tokens')}
                      >
                        토큰 수 표시
                      </button>
                      <button 
                        className="btn-secondary" 
                        style={{ flex: 1, padding: '1rem', background: tokenDisplayMode === 'cost' ? 'var(--btn-active-bg)' : 'transparent', border: tokenDisplayMode === 'cost' ? '2px solid #60a5fa' : '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '8px', transition: 'all 0.3s' }}
                        onClick={() => handleDisplayModeChange('cost')}
                      >
                        금액 표시
                      </button>
                    </div>
                  </div>
                  {tokenDisplayMode === 'cost' && (
                    <div style={{ marginTop: '0.5rem' }}>
                      <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>화폐 단위</label>
                      <div style={{ display: 'flex', gap: '1rem' }}>
                        <button 
                          className="btn-secondary" 
                          style={{ flex: 1, padding: '1rem', background: costCurrency === 'USD' ? 'var(--btn-active-bg)' : 'transparent', border: costCurrency === 'USD' ? '2px solid #60a5fa' : '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '8px', transition: 'all 0.3s' }}
                          onClick={() => handleCurrencyChange('USD')}
                        >
                          달러 (USD)
                        </button>
                        <button 
                          className="btn-secondary" 
                          style={{ flex: 1, padding: '1rem', background: costCurrency === 'KRW' ? 'var(--btn-active-bg)' : 'transparent', border: costCurrency === 'KRW' ? '2px solid #60a5fa' : '1px solid var(--border-color)', color: 'var(--text-color)', borderRadius: '8px', transition: 'all 0.3s' }}
                          onClick={() => handleCurrencyChange('KRW')}
                        >
                          원화 (KRW)
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>

            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;

