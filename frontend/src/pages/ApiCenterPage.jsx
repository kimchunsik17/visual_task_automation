import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';
import { Key, Trash2, Info, Save, ExternalLink, X, CheckCircle2, AlertTriangle } from 'lucide-react';
import { Icon } from '../icons';
import { customConfirm } from '../CustomConfirm';
import MainSidebar from '../MainSidebar';
import SectionTabs from '../components/SectionTabs';
import DatabaseCredentialsCard from '../components/DatabaseCredentialsCard';
import { SETTINGS_SECTION_TABS } from '../navigation';
import safeAutomationArt from '../assets/editorial/security/safe-automation-v2.webp';
import './MainPage.css';
import './ApiCenterPage.css';
import credentialProviders from '../generated/credentialProviders.json';

// provider 목록의 정본은 저장소 루트 credential_providers.json 이고, 아래 번들은
// `python backend/export_node_definitions.py` 가 만든다(ADR-0007). 예전에는 이 목록이
// 이 파일 안에만 있어서 서버는 어떤 provider 가 유효한지도, 사용자가 무엇을 연결해뒀는지도
// 판단할 수 없었다. 번들 파일을 직접 고치지 마라 — 드리프트 테스트가 잡아낸다.
const PROVIDERS = credentialProviders.map((provider) => ({
  ...provider,
  // token_pair 는 access_token + refresh_token 을 함께 받는다(카카오). 예전 isTokenPair
  // 플래그를 정본의 kind 에서 파생시킨다.
  isTokenPair: provider.kind === 'token_pair',
  // authorize 선언이 있으면 토큰을 손으로 붙여넣는 대신 동의 절차로 받는다(한국형 노드 계획 Phase 0).
  isOAuth: !!provider.authorize,
}));

/**
 * 연결 상태 한 줄.
 *
 * 서버(`connectors/providers.connection_status`)가 이미 계산해 주는 것을 그대로 보여준다 —
 * 예전에는 이 값을 받아만 두고 쓰지 않아서, **토큰이 만료됐는지 실행해 봐야 알 수 있었다.**
 *
 * 순서는 "고칠 수 있는 것부터" 다. 만료됐으면 그것부터, 자동 갱신 짝이 빠졌으면 무엇이
 * 빠졌는지, 그 다음이 권한 범위다.
 */
const ConnectionStatus = ({ status }) => {
  if (!status || !status.connected) return null;

  const refresh = status.auto_refresh;
  const expiresAt = refresh?.expires_at ? new Date(refresh.expires_at) : null;
  const expired = Boolean(refresh?.expired);
  // 만료가 임박한 것도 알린다 — 만료된 뒤에 아는 것보다 낫다.
  const soon = !expired && expiresAt && (expiresAt - Date.now()) < 24 * 3600 * 1000;

  const rows = [];
  if (expired) {
    rows.push({ tone: 'bad', text: '토큰이 만료됐습니다. 다시 연결해주세요.' });
  } else if (soon) {
    rows.push({ tone: 'warn', text: `토큰이 곧 만료됩니다 (${expiresAt.toLocaleString()})` });
  } else if (expiresAt) {
    rows.push({ tone: 'ok', text: `토큰 만료: ${expiresAt.toLocaleString()}` });
  }

  if (refresh) {
    if (!refresh.has_refresh_token) {
      rows.push({ tone: 'bad', text: 'refresh_token 이 없어 자동 갱신이 되지 않습니다. 다시 연결해주세요.' });
    } else if (!refresh.client_id_connected) {
      rows.push({ tone: 'bad',
                  text: `자동 갱신에 '${refresh.client_id_provider}' 등록이 함께 필요합니다.` });
    } else if (status.ready) {
      rows.push({ tone: 'ok', text: '자동 갱신 준비 완료' });
    }
  }

  if (rows.length === 0 && !(status.scopes || []).length) return null;

  return (
    <div className="api-conn-status">
      {rows.map((r) => (
        <div key={r.text} className={`api-conn-row api-conn-${r.tone}`}>
          {r.tone === 'ok' ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
          <span>{r.text}</span>
        </div>
      ))}
      {status.scopes?.length > 0 && (
        <details className="api-scope-list">
          <summary>이 연결이 갖는 권한 {status.scopes.length}개</summary>
          <ul>
            {status.scopes.map((sc) => (
              <li key={sc.value || sc.name}>
                <code>{sc.value || sc.name}</code>
                {sc.description ? <span> — {sc.description}</span> : null}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
};

export default function ApiCenterPage() {
  const { user, token } = useAuth();
  const [sudoToken, setSudoToken] = useState(null);
  const [apiKeys, setApiKeys] = useState([]);
  // 실행 오류 안내의 문맥형 바로가기(/settings/api-center?provider=google_oauth 등)가
  // 해당 공급자 카드를 강조하고 화면 안으로 스크롤한다(IA 계획 §3.2).
  const [searchParams] = useSearchParams();
  const focusedProvider = searchParams.get('provider');
  useEffect(() => {
    if (!focusedProvider) return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(`provider-${focusedProvider}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [focusedProvider, apiKeys.length]);

  // 동의 절차로 돌아왔을 때(?connected= / ?oauth_error=) 결과를 알려준다. 서버가 이 두 값만
  // 붙여 보내므로 화면은 그것만 읽는다.
  const connectedProvider = searchParams.get('connected');
  const oauthError = searchParams.get('oauth_error');
  // provider 콘솔에 등록할 콜백 주소. 서버가 만드는 값이라 사용자가 추측하면 안 된다.
  const [callbackUrls, setCallbackUrls] = useState({});
  const [connecting, setConnecting] = useState(null);
  // 연결 상태(만료·자동갱신 준비·scope)는 서버가 `/api/credential-providers` 에서 이미
  // 계산해 준다. 예전에는 받아만 두고 화면에 쓰지 않아서, 토큰이 만료됐는지 자동 갱신이
  // 실제로 동작할 준비가 됐는지를 사용자가 실행해 보기 전에는 알 수 없었다.
  const [connections, setConnections] = useState({});

  useEffect(() => {
    axios.get('/api/credential-providers', { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => {
        const urls = {};
        (res.data?.providers || []).forEach((p) => { if (p.callback_url) urls[p.id] = p.callback_url; });
        setCallbackUrls(urls);
        const byProvider = {};
        (res.data?.connections || []).forEach((c) => { byProvider[c.provider] = c; });
        setConnections(byProvider);
      })
      .catch(() => {});
  }, [token]);

  const handleConnect = async (providerId) => {
    setConnecting(providerId);
    try {
      const res = await axios.post(`/api/oauth/${providerId}/start`,
        { return_to: `/settings/api-center?provider=${providerId}` },
        { headers: { Authorization: `Bearer ${sudoToken}` } });
      // 동의 화면으로 넘어간다. 돌아올 주소는 서버가 state 와 함께 들고 있다.
      window.location.href = res.data.url;
    } catch (err) {
      const detail = err.response?.data?.detail;
      alert(detail?.message || '연결을 시작하지 못했습니다.', 'error');
      setConnecting(null);
    }
  };

  const [loading, setLoading] = useState(false);
  const [activeGuide, setActiveGuide] = useState(null);
  const [newKeyValues, setNewKeyValues] = useState({});
  const [editingProviders, setEditingProviders] = useState({});

  const handleGoogleSuccess = async (credentialResponse) => {
    try {
      const payloadToken = credentialResponse.credential;
      if (!payloadToken) {
         alert("인증 토큰을 받아오지 못했습니다.", 'error');
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
        alert("세션이 만료되었습니다. 다시 인증해주세요.", 'warning');
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
        <SectionTabs ariaLabel="설정 섹션" tabs={SETTINGS_SECTION_TABS} />
          <div className="content-area centered" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto' }}>
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
        <SectionTabs ariaLabel="설정 섹션" tabs={SETTINGS_SECTION_TABS} />
        <div className="content-area" style={{ width: '100%', maxWidth: '1000px', margin: '0 auto' }}>
          
          <div className="page-header">
            <div>
              <h1 className="page-title"><Key className="title-icon" /> API Center</h1>
              <p className="page-subtitle">여러분의 소중한 외부 API 키를 안전하게 저장하고 워크플로우에 주입하세요.</p>
            </div>
          </div>

          {!sudoToken ? (
            <div className="sudo-auth-container">
              <img
                className="sudo-auth-art"
                src={safeAutomationArt}
                alt=""
                aria-hidden="true"
              />
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
                // Database 는 여러 개를 이름으로 등록한다(ADR-0017) — 전용 카드
                if (provider.id === 'database') {
                  return (
                    <DatabaseCredentialsCard
                      key={provider.id}
                      provider={provider}
                      token={token}
                      sudoToken={sudoToken}
                      focused={focusedProvider === provider.id}
                      onGuide={() => setActiveGuide(provider)}
                    />
                  );
                }
                const existingKey = apiKeys.find(k => k.provider === provider.id);
                return (
                  <div
                    key={provider.id}
                    id={`provider-${provider.id}`}
                    className={`api-card ${existingKey ? 'has-key' : ''} ${focusedProvider === provider.id ? 'provider-focus' : ''}`}
                  >
                    <div className="api-card-header">
                      <div className="api-card-title">
                        <span className="api-icon"><Icon name={provider.icon} size={24} /></span>
                        <h3>{provider.name}</h3>
                      </div>
                      <button className="guide-btn" onClick={() => setActiveGuide(provider)}>
                        <Info size={16} /> 발급 가이드
                      </button>
                    </div>

                    <div className="api-card-body">
                      <ConnectionStatus status={connections[provider.id]} />
                      {/* 동의 절차로 받는 provider — 토큰을 손으로 옮기지 않는다(Phase 0). */}
                      {provider.isOAuth && (
                        <div className="oauth-connect" style={{
                          border: '1px solid var(--border-color)', borderRadius: '10px',
                          padding: '12px', marginBottom: '12px',
                        }}>
                          {connectedProvider === provider.id && (
                            <div style={{ color: '#2a9d5c', fontSize: '0.85rem', marginBottom: '8px' }}>
                              연결됐습니다.
                            </div>
                          )}
                          {oauthError && focusedProvider === provider.id && (
                            <div style={{ color: '#d97706', fontSize: '0.85rem', marginBottom: '8px' }}>
                              {oauthError === 'denied'
                                ? '동의를 취소하셨습니다. 다시 시도할 수 있습니다.'
                                : '연결이 완료되지 않았습니다. 다시 시도해주세요.'}
                            </div>
                          )}
                          <button
                            className="save-key-btn"
                            disabled={connecting === provider.id}
                            onClick={() => handleConnect(provider.id)}
                          >
                            <ExternalLink size={16} />
                            {connecting === provider.id ? ' 이동 중…' : (existingKey ? ' 다시 연결' : ' 연결하기')}
                          </button>
                          {callbackUrls[provider.id] && (
                            <div style={{ marginTop: '10px', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                              <div style={{ marginBottom: '4px' }}>
                                아래 주소를 서비스 콘솔의 <strong>Callback URL</strong> 에 그대로 등록해야 합니다.
                              </div>
                              <code style={{
                                display: 'block', wordBreak: 'break-all', padding: '6px 8px',
                                background: 'var(--bg-color)', color: 'var(--text-color)',
                                border: '1px solid var(--border-color)', borderRadius: '6px',
                                fontFamily: 'var(--font-mono)',
                              }}>{callbackUrls[provider.id]}</code>
                            </div>
                          )}
                        </div>
                      )}
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
                          {provider.isOAuth && (
                            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                              위 '연결하기' 를 쓰는 것이 정상 경로입니다. 아래는 토큰을 직접 받아 둔 경우에만 씁니다.
                            </div>
                          )}
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
              <h3><Icon name={activeGuide.icon} size={20} /> {activeGuide.name} 키 발급 가이드</h3>
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
