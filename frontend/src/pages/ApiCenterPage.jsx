import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';
import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';
import { Key, Plus, Trash2, Shield, Info, Save, ExternalLink, X } from 'lucide-react';
import { customConfirm } from '../CustomConfirm';
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
    name: 'Kakao REST API 키',
    icon: '💬',
    guide: [
      "1. [카카오 디벨로퍼스](https://developers.kakao.com/)에 로그인합니다.",
      "2. '내 애플리케이션'에서 앱을 생성하거나 선택합니다.",
      "3. '요약 정보' 탭의 'REST API 키'를 복사합니다.",
      "4. 이 키는 아래 '카카오 메시지 토큰'의 access_token을 6시간마다 자동으로 갱신하는 데 쓰입니다(client_id 역할)."
    ]
  },
  {
    id: 'kakao_token',
    name: 'Kakao 메시지 토큰 (자동 갱신)',
    icon: '🔑',
    isTokenPair: true,
    guide: [
      "1. 카카오 로그인 OAuth 동의 절차를 한 번 완료해서 access_token과 refresh_token을 발급받습니다.",
      "   (카카오 디벨로퍼스 앱의 '카카오 로그인 > 도구 > 토큰 받기' 기능을 쓰면 간편합니다.)",
      "2. 발급받은 access_token과 refresh_token을 아래 두 칸에 각각 붙여넣고 저장합니다.",
      "3. access_token은 6시간 뒤 만료되지만, 워크플로우 실행 시 refresh_token으로 자동 갱신되므로 이후엔 다시 안 붙여넣어도 됩니다.",
      "4. 위 'Kakao REST API 키'도 함께 등록되어 있어야 자동 갱신이 동작합니다."
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
    ]
  },
  {
    id: 'telegram',
    name: 'Telegram Bot Token',
    icon: '✈️',
    guide: [
      "1. 텔레그램 앱에서 [@BotFather](https://t.me/BotFather)를 검색해 대화를 시작합니다.",
      "2. '/newbot' 명령어를 보내고, 안내에 따라 봇 이름과 사용자명을 정합니다.",
      "3. 생성이 완료되면 BotFather가 토큰(숫자:영문 조합)을 보내줍니다 — 그 값을 복사합니다.",
      "4. 이 토큰은 만료되지 않으므로(카카오와 달리 재발급/자동 갱신이 필요 없음), 한 번만 등록하면 됩니다.",
    ]
  },
  {
    id: 'notion',
    name: 'Notion Integration Token',
    icon: '📝',
    guide: [
      "1. [Notion 내 통합](https://www.notion.so/my-integrations)에 접속합니다.",
      "2. '새 통합 만들기'를 클릭하고 이름을 정한 뒤 생성합니다.",
      "3. 'Internal Integration Secret' 값을 복사합니다 (secret_ 또는 ntn_으로 시작).",
      "4. 워크플로우에서 다룰 Notion 페이지/데이터베이스를 열어 '...' 메뉴 → '연결 추가'에서 방금 만든 통합을 선택해 연결해야 실제로 접근할 수 있습니다.",
    ]
  },
  {
    id: 'google_smtp',
    name: 'Gmail SMTP', 
    icon: '📧',
    guide: [
      "1. 구글 계정 관리에 들어가서 2단계 인증을 활성화합니다.",
      "2. '앱 비밀번호(App Passwords)'를 검색하여 새 앱 비밀번호를 생성합니다.",
      "3. 16자리 앱 비밀번호가 생성됩니다.",
      "4. 본인 이메일과 생성된 비밀번호를 '이메일:앱비밀번호' 형식(예: user@gmail.com:abcd1234efgh)으로 붙여넣습니다."
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
  const [editingProviders, setEditingProviders] = useState({});

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

  const handleSaveKey = async (providerId, isTokenPair = false) => {
    const value = newKeyValues[providerId];
    if (isTokenPair) {
      const accessToken = value?.access_token;
      const refreshToken = value?.refresh_token;
      // refresh_token은 있으면 자동 갱신에 쓰이지만 없어도 access_token만으로 당장은 동작한다
      // (그 access_token이 만료되는 6시간 뒤부터는 다시 수동으로 넣어줘야 함).
      if (!accessToken) return;
      try {
        await axios.post('/api/user/apikeys', {
          provider: providerId,
          api_key: accessToken,
          ...(refreshToken ? { refresh_token: refreshToken } : {}),
        }, {
          headers: { Authorization: `Bearer ${sudoToken}` }
        });
        setNewKeyValues(prev => ({...prev, [providerId]: {}}));
        setEditingProviders(prev => ({...prev, [providerId]: false}));
        fetchKeys();
      } catch (err) {
        alert("저장에 실패했습니다.");
      }
      return;
    }
    if (!value) return;
    try {
      await axios.post('/api/user/apikeys', { provider: providerId, api_key: value }, {
        headers: { Authorization: `Bearer ${sudoToken}` }
      });
      setNewKeyValues(prev => ({...prev, [providerId]: ''}));
      setEditingProviders(prev => ({...prev, [providerId]: false}));
      fetchKeys();
    } catch (err) {
      alert("저장에 실패했습니다.");
    }
  };

  const handleDeleteKey = async (providerId) => {
    if (!(await customConfirm("정말로 이 키를 삭제하시겠습니까? 관련 자동화가 작동하지 않을 수 있습니다."))) return;
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
                      {existingKey && !editingProviders[provider.id] ? (
                        <div className="key-display">
                          <div className="masked-key">{existingKey.masked_key}</div>
                          {provider.isTokenPair && (
                            <div className="token-status" style={{ fontSize: '0.8rem', color: existingKey.has_refresh_token ? '#2a9d5c' : '#d97706', marginTop: '4px' }}>
                              {existingKey.has_refresh_token
                                ? `자동 갱신 활성화됨${existingKey.token_expires_at ? ` (현재 토큰 만료: ${new Date(existingKey.token_expires_at).toLocaleString()})` : ''}`
                                : 'refresh_token이 없어 자동 갱신이 되지 않습니다. 다시 저장해주세요.'}
                            </div>
                          )}
                          <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                            <button
                              className="save-key-btn"
                              onClick={() => setEditingProviders(prev => ({...prev, [provider.id]: true}))}
                            >
                              <Key size={16} /> 값 변경
                            </button>
                            <button className="delete-key-btn" onClick={() => handleDeleteKey(provider.id)}>
                              <Trash2 size={16} /> 삭제
                            </button>
                          </div>
                        </div>
                      ) : provider.isTokenPair ? (
                        <div className="key-input-area" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                          <input
                            type="password"
                            placeholder="access_token을 입력하세요"
                            value={newKeyValues[provider.id]?.access_token || ''}
                            onChange={(e) => setNewKeyValues({
                              ...newKeyValues,
                              [provider.id]: { ...newKeyValues[provider.id], access_token: e.target.value }
                            })}
                          />
                          <input
                            type="password"
                            placeholder="refresh_token을 입력하세요 (선택 — 없으면 6시간마다 재입력 필요)"
                            value={newKeyValues[provider.id]?.refresh_token || ''}
                            onChange={(e) => setNewKeyValues({
                              ...newKeyValues,
                              [provider.id]: { ...newKeyValues[provider.id], refresh_token: e.target.value }
                            })}
                          />
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button
                              className="save-key-btn"
                              disabled={!newKeyValues[provider.id]?.access_token}
                              onClick={() => handleSaveKey(provider.id, true)}
                            >
                              <Save size={16} /> 저장
                            </button>
                            {existingKey && (
                              <button
                                className="delete-key-btn"
                                onClick={() => setEditingProviders(prev => ({...prev, [provider.id]: false}))}
                              >
                                취소
                              </button>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div className="key-input-area">
                          <input
                            type="password"
                            placeholder="API 키를 입력하세요"
                            value={newKeyValues[provider.id] || ''}
                            onChange={(e) => setNewKeyValues({...newKeyValues, [provider.id]: e.target.value})}
                          />
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button
                              className="save-key-btn"
                              disabled={!newKeyValues[provider.id]}
                              onClick={() => handleSaveKey(provider.id)}
                            >
                              <Save size={16} /> 저장
                            </button>
                            {existingKey && (
                              <button
                                className="delete-key-btn"
                                onClick={() => setEditingProviders(prev => ({...prev, [provider.id]: false}))}
                              >
                                취소
                              </button>
                            )}
                          </div>
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
