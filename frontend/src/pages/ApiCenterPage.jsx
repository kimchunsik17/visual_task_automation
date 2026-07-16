import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';
import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';
import { Key, Plus, Trash2, Shield, Info, Save, ExternalLink, X } from 'lucide-react';
import MainSidebar from '../MainSidebar';
import './MainPage.css';
import './ApiCenterPage.css';

const PROVIDERS = [
  { 
    id: 'openai', 
    name: 'OpenAI (ChatGPT)', 
    icon: '🤖',
    guide: [
      "1. [OpenAI API Keys 페이지](https://platform.openai.com/api-keys)에 접속합니다.",
      "2. 회원가입 또는 로그인을 진행합니다.",
      "3. 우측 상단의 'Create new secret key' 버튼을 클릭합니다.",
      "4. 생성된 키(sk-... 형식)를 복사하여 아래에 붙여넣습니다."
    ]
  },
  { 
    id: 'gemini', 
    name: 'Google Gemini', 
    icon: '✨',
    guide: [
      "1. [Google AI Studio](https://aistudio.google.com/app/apikey)에 접속합니다.",
      "2. 구글 계정으로 로그인합니다.",
      "3. 'Create API key' 버튼을 눌러 새 프로젝트에 키를 생성합니다.",
      "4. 생성된 문자열을 복사합니다."
    ]
  },
  { 
    id: 'kakao', 
    name: 'Kakao REST API', 
    icon: '💬',
    guide: [
      "1. [카카오 디벨로퍼스](https://developers.kakao.com/)에 로그인합니다.",
      "2. '내 애플리케이션'에서 앱을 생성하거나 선택합니다.",
      "3. '요약 정보' 탭의 'REST API 키'를 복사합니다.",
      "4. (주의) 카카오톡 메시지 전송을 위해서는 메시지 API 활성화가 추가로 필요합니다."
    ]
  },
  { 
    id: 'discord', 
    name: 'Discord Bot Token', 
    icon: '🎮',
    guide: [
      "1. [Discord Developer Portal](https://discord.com/developers/applications)에 접속합니다.",
      "2. 'New Application'을 클릭해 봇을 만듭니다.",
      "3. 좌측 'Bot' 메뉴로 이동 후 'Reset Token'을 눌러 토큰을 발급합니다.",
      "4. 해당 토큰을 복사하여 붙여넣습니다."
    ]
  }
];

export default function ApiCenterPage() {
  const { user, token } = useAuth();
  const [sudoToken, setSudoToken] = useState(null);
  const [apiKeys, setApiKeys] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeGuide, setActiveGuide] = useState(null);
  const [newKeyValues, setNewKeyValues] = useState({});

  const handleGoogleSuccess = async (credentialResponse) => {
    try {
      const payloadToken = credentialResponse.credential;
      if (!payloadToken) {
         alert("인증 토큰을 받아오지 못했습니다.");
         return;
      }
      const res = await axios.post('/api/auth/sudo', { token: payloadToken });
      setSudoToken(res.data.sudo_token);
    } catch (err) {
      alert("인증에 실패했습니다. " + (err.response?.data?.detail || ''));
    }
  };

  useEffect(() => {
    if (sudoToken) {
      fetchKeys();
    }
  }, [sudoToken]);

  const fetchKeys = async () => {
    try {
      setLoading(true);
      const res = await axios.get('/api/user/apikeys', {
        headers: { Authorization: `Bearer ${sudoToken}` }
      });
      setApiKeys(res.data);
    } catch (err) {
      if (err.response?.status === 401 || err.response?.status === 403) {
        setSudoToken(null);
        alert("세션이 만료되었습니다. 다시 인증해주세요.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSaveKey = async (providerId) => {
    const key = newKeyValues[providerId];
    if (!key) return;
    try {
      await axios.post('/api/user/apikeys', { provider: providerId, api_key: key }, {
        headers: { Authorization: `Bearer ${sudoToken}` }
      });
      setNewKeyValues(prev => ({...prev, [providerId]: ''}));
      fetchKeys();
    } catch (err) {
      alert("저장에 실패했습니다.");
    }
  };

  const handleDeleteKey = async (providerId) => {
    if (!window.confirm("정말로 이 키를 삭제하시겠습니까? 관련 자동화가 작동하지 않을 수 있습니다.")) return;
    try {
      await axios.delete(`/api/user/apikeys/${providerId}`, {
        headers: { Authorization: `Bearer ${sudoToken}` }
      });
      fetchKeys();
    } catch (err) {
      alert("삭제에 실패했습니다.");
    }
  };

  if (!user) {
    return (
      <div className="main-page-layout">
        <MainSidebar />
        <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
          <div className="content-area centered" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto', padding: '2rem' }}>
            <h2>로그인이 필요합니다</h2>
            <p>API 센터를 이용하려면 먼저 로그인해주세요.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="main-page-layout">
      <MainSidebar />
      <div className="main-page-content" style={{ justifyContent: 'flex-start' }}>
        <div className="content-area" style={{ width: '100%', maxWidth: '1000px', margin: '0 auto', padding: '2rem' }}>
          
          <div className="page-header">
            <div>
              <h1 className="page-title"><Key className="title-icon" /> API Center</h1>
              <p className="page-subtitle">여러분의 소중한 외부 API 키를 안전하게 저장하고 워크플로우에 주입하세요.</p>
            </div>
          </div>

          {!sudoToken ? (
            <div className="sudo-auth-container">
              <Shield size={64} className="shield-icon" />
              <h2>안전한 접근을 위한 재인증</h2>
              <p>API 키는 매우 민감한 정보입니다. 본인 확인을 위해 구글 계정으로 다시 인증해 주세요.</p>
              <div className="google-login-wrapper" style={{ display: 'flex', justifyContent: 'center', marginTop: '20px' }}>
                <GoogleLogin
                  onSuccess={handleGoogleSuccess}
                  onError={() => alert('구글 로그인에 실패했습니다.')}
                  useOneTap={false}
                />
              </div>
            </div>
          ) : (
            <div className="api-providers-grid">
              {PROVIDERS.map(provider => {
                const existingKey = apiKeys.find(k => k.provider === provider.id);
                return (
                  <div key={provider.id} className={`api-card ${existingKey ? 'has-key' : ''}`}>
                    <div className="api-card-header">
                      <div className="api-card-title">
                        <span className="api-icon">{provider.icon}</span>
                        <h3>{provider.name}</h3>
                      </div>
                      <button className="guide-btn" onClick={() => setActiveGuide(provider)}>
                        <Info size={16} /> 발급 가이드
                      </button>
                    </div>

                    <div className="api-card-body">
                      {existingKey ? (
                        <div className="key-display">
                          <div className="masked-key">{existingKey.masked_key}</div>
                          <button className="delete-key-btn" onClick={() => handleDeleteKey(provider.id)}>
                            <Trash2 size={16} /> 삭제
                          </button>
                        </div>
                      ) : (
                        <div className="key-input-area">
                          <input 
                            type="password" 
                            placeholder="API 키를 입력하세요" 
                            value={newKeyValues[provider.id] || ''}
                            onChange={(e) => setNewKeyValues({...newKeyValues, [provider.id]: e.target.value})}
                          />
                          <button 
                            className="save-key-btn" 
                            disabled={!newKeyValues[provider.id]}
                            onClick={() => handleSaveKey(provider.id)}
                          >
                            <Save size={16} /> 저장
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

        </div>
      </div>

      {activeGuide && (
        <div className="guide-modal-overlay" onClick={() => setActiveGuide(null)}>
          <div className="guide-modal-content" onClick={e => e.stopPropagation()}>
            <div className="guide-modal-header">
              <h3>{activeGuide.icon} {activeGuide.name} 키 발급 가이드</h3>
              <button className="close-btn" onClick={() => setActiveGuide(null)}><X size={20} /></button>
            </div>
            <div className="guide-modal-body">
              {activeGuide.guide.map((step, idx) => {
                // simple markdown link parser
                const parts = step.split(/\[(.*?)\]\((.*?)\)/);
                if (parts.length === 3) {
                  return (
                    <p key={idx}>
                      {parts[0]}<a href={parts[2]} target="_blank" rel="noreferrer" className="guide-link">{parts[1]} <ExternalLink size={12}/></a>
                    </p>
                  );
                }
                return <p key={idx}>{step}</p>;
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
