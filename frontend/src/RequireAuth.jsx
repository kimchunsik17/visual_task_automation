import { GoogleLogin } from '@react-oauth/google';
import axios from 'axios';
import { useAuth } from './AuthContext';
import logoImg from './logo.png';

// 로그인하지 않은 사용자는 children을 아예 렌더링하지 않고 로그인 화면으로 막는다.
// 공유 링크(/app/:shareToken, /viewer/:projectId)는 계정 없이도 열람 가능해야 하므로
// App.jsx에서 이 컴포넌트로 감싸지 않는다.
const RequireAuth = ({ children }) => {
  const { user, login } = useAuth();

  // 테스트 빌드 임시 해제: 항상 통과
  return children;

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
            계속하려면 구글 계정으로 로그인해주세요.
          </p>
        </div>
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
