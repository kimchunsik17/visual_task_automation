import { useEffect, useState } from 'react';
import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';
import { useAuth } from './AuthContext';
import { isDemoGuest, loadFeatures } from './features';
import logoImg from './logo.png';

// 로그인하지 않은 사용자는 children을 아예 렌더링하지 않고 로그인 화면으로 막는다.
// 공유 링크(/app/:shareToken, /viewer/:projectId)는 계정 없이도 열람 가능해야 하므로
// App.jsx에서 이 컴포넌트로 감싸지 않는다.
const RequireAuth = ({ children }) => {
  const { user, login, enterGuest } = useAuth();
  // 시연 게스트 입장(DEMO_GUEST). 로그아웃한 탭은 자동 입장이 멈추므로(AuthContext 의 opt-out)
  // 이 게이트에도 다시 들어갈 입구가 있어야 한다 — 없으면 보호된 페이지에서 로그아웃한 순간
  // 구글 로그인만 남아 게스트로 되돌아갈 길이 없다(2026-09-05 부스 점검에서 발견).
  // 사이드바 푸터의 버튼과 같은 경로(enterGuest)를 쓴다. 훅은 아래 조기 return 보다 먼저 온다.
  const [demoGuest, setDemoGuest] = useState(isDemoGuest());
  useEffect(() => {
    let alive = true;
    loadFeatures().then((data) => { if (alive) setDemoGuest(Boolean(data?.demo_guest)); });
    return () => { alive = false; };
  }, []);

  // (제거됨) 테스트 빌드용 `return children` 무조건 통과. 남겨두면 로그인하지 않은 사람에게도
  // 에디터·앱 빌더 화면이 그대로 열려, 데이터는 401 로 비어 있는데 UI 만 동작하는 상태가 된다.
  if (user) return children;

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
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100dvh',
      width: '100vw',
      background: 'var(--bg-color)',
      padding: '2rem',
      boxSizing: 'border-box',
    }}>
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '1.5rem',
        background: 'var(--card-bg)',
        border: '1px solid var(--border-color)',
        borderRadius: '16px',
        padding: '3rem 2.5rem',
        boxShadow: 'var(--card-shadow)',
        maxWidth: '380px',
        width: '100%',
      }}>
        <img src={logoImg} alt="WorkFlow Ai Logo" style={{ width: '56px', height: '56px', objectFit: 'contain' }} />
        <div style={{ textAlign: 'center' }}>
          <h1 style={{ margin: '0 0 0.5rem 0', fontSize: '1.3rem', fontWeight: 700, color: 'var(--text-color)' }}>
            로그인이 필요합니다
          </h1>
          <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
            {demoGuest ? '구글 계정으로 로그인하거나, 계정 없이 게스트로 체험해 보세요.' : '계속하려면 구글 계정으로 로그인해주세요.'}
          </p>
        </div>
        {demoGuest && (
          <button type="button" className="demo-login-toggle" style={{ marginTop: 0 }}
                  onClick={() => enterGuest().catch((error) => {
                    alert('게스트 입장 실패: ' + (error.response?.data?.detail || error.message));
                  })}>
            게스트로 입장하기 (시연 체험)
          </button>
        )}
        <GoogleLogin
          onSuccess={handleGoogleSuccess}
          onError={() => {
            console.log('Login Failed');
            alert('로그인에 실패했습니다. 다시 시도해주세요.');
          }}
        />
      </div>
    </div>
  );
};

export default RequireAuth;
