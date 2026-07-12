import { Settings, User, Bell, Shield, Palette } from 'lucide-react';
import MainSidebar from '../MainSidebar';
import { useAuth } from '../AuthContext';
import './MainPage.css';

function SettingsPage() {
  const { user } = useAuth();

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <div className="dashboard-grid">
          <section>
            <div className="section-header">
              <h3><Settings size={22} color="#94a3b8" /> 설정</h3>
            </div>
            
            <div className="settings-container" style={{ display: 'flex', flexDirection: 'column', gap: '2rem', maxWidth: '800px' }}>
              
              <div className="settings-section" style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '1.5rem' }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'white' }}>
                  <User size={18} color="#60a5fa" /> 계정 정보
                </h4>
                {user ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', marginTop: '1rem' }}>
                    <img src={user.picture} alt="Profile" style={{ width: '64px', height: '64px', borderRadius: '50%', border: '2px solid #334155' }} />
                    <div>
                      <p style={{ margin: '0 0 0.5rem 0', color: 'white', fontWeight: 600, fontSize: '1.1rem' }}>{user.name}</p>
                      <p style={{ margin: 0, color: '#94a3b8' }}>{user.email}</p>
                    </div>
                  </div>
                ) : (
                  <p style={{ color: '#94a3b8', margin: '1rem 0 0 0' }}>로그인이 필요합니다.</p>
                )}
              </div>

              <div className="settings-section" style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '1.5rem' }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'white' }}>
                  <Palette size={18} color="#c084fc" /> 테마 설정
                </h4>
                <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
                  <button className="btn-secondary" style={{ flex: 1, padding: '1rem', background: 'rgba(255, 255, 255, 0.05)', border: '2px solid #60a5fa' }}>다크 모드</button>
                  <button className="btn-secondary" style={{ flex: 1, padding: '1rem', opacity: 0.5, cursor: 'not-allowed' }}>라이트 모드 (준비중)</button>
                </div>
              </div>

              <div className="settings-section" style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '1.5rem' }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: 0, color: 'white' }}>
                  <Bell size={18} color="#f472b6" /> 알림
                </h4>
                <p style={{ color: '#94a3b8', margin: '1rem 0 0 0' }}>새로운 알림이 없습니다.</p>
              </div>

            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;
