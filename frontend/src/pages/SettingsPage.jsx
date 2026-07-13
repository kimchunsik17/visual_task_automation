import { useState, useEffect } from 'react';
import { Settings, User, Bell, Shield, Palette, DollarSign } from 'lucide-react';
import MainSidebar from '../MainSidebar';
import { useAuth } from '../AuthContext';
import './MainPage.css';

function SettingsPage() {
  const { user } = useAuth();
  const [theme, setTheme] = useState(document.documentElement.getAttribute('data-theme') || 'dark');
  const [tokenDisplayMode, setTokenDisplayMode] = useState(localStorage.getItem('tokenDisplayMode') || 'tokens');
  const [costCurrency, setCostCurrency] = useState(localStorage.getItem('costCurrency') || 'USD');

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
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', marginTop: '1rem' }}>
                    <img src={user.picture} alt="Profile" style={{ width: '64px', height: '64px', borderRadius: '50%', border: '2px solid #334155' }} />
                    <div>
                      <p style={{ margin: '0 0 0.5rem 0', color: 'var(--text-color)', fontWeight: 600, fontSize: '1.1rem' }}>{user.name}</p>
                      <p style={{ margin: 0, color: 'var(--text-muted)' }}>{user.email}</p>
                    </div>
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

