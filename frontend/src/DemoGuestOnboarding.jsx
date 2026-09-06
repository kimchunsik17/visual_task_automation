import { useRef, useState } from 'react';
import axios from 'axios';
import { useAuth } from './AuthContext';
import './DemoGuestOnboarding.css';

// 시연 게스트(DEMO_GUEST)의 최초 1회 입력 — 결과를 받을 실제 이메일과 이름.
//
// 게스트 계정은 guest-…@demo.local 이라는 받을 수 없는 주소로 만들어진다. 그 주소가 남아 있는
// 동안 이 안내를 띄우고, 등록하면 서버가 이메일을 바꾸고 이름을 '(시연용)이름' 으로 붙여 준다
// (POST /api/auth/guest/profile). 시연 워크플로우의 이메일 노드 수신자({{USER_EMAIL}})는 발송
// 직전 이 이메일로 풀린다. 입력창은 비제어(uncontrolled)로 둔다 — 한글 IME 조합이 제어 입력에서
// 끊기는 재발 이력이 있다(노드 한글 입력 메모).
const SKIP_KEY = 'wf-demo-onboarding-skip';   // 탭 단위 — '나중에' 를 누르면 이 탭에서는 다시 묻지 않는다

const isDemoGuestUser = (user) =>
  Boolean(user?.email && String(user.email).toLowerCase().endsWith('@demo.local'));

const readSkipped = () => {
  try { return Boolean(window.sessionStorage.getItem(SKIP_KEY)); } catch { return false; }
};

export default function DemoGuestOnboarding() {
  const { user, token, login } = useAuth();
  const nameRef = useRef(null);
  const emailRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [skipped, setSkipped] = useState(readSkipped);

  if (!user || !token || !isDemoGuestUser(user) || skipped) return null;

  const submit = async (event) => {
    event.preventDefault();
    const email = (emailRef.current?.value || '').trim();
    const name = (nameRef.current?.value || '').trim();
    if (!email) { setError('이메일을 입력해 주세요.'); return; }
    setBusy(true);
    setError('');
    try {
      // 이 앱은 axios 전역 인증 헤더를 쓰지 않는다 — 요청마다 붙인다(빠뜨리면 401 'Not authenticated', 2026-09-06 부스 점검).
      const res = await axios.post('/api/auth/guest/profile', { email, name },
        { headers: { Authorization: `Bearer ${token}` } });
      login(res.data.user, token);   // 사이드바의 이름·이메일이 곧바로 바뀌고, @demo.local 이 아니므로 이 모달은 사라진다
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setBusy(false);
    }
  };

  const skip = () => {
    try { window.sessionStorage.setItem(SKIP_KEY, '1'); } catch { /* 저장소 불가 = 이 렌더에서만 닫힘 */ }
    setSkipped(true);
  };

  return (
    <div className="demo-onboarding-overlay" role="dialog" aria-modal="true" aria-labelledby="demo-onboarding-title">
      <form className="demo-onboarding-card" onSubmit={submit}>
        <h2 id="demo-onboarding-title">시연 체험을 시작합니다</h2>
        <p>워크플로우가 만든 문서와 알림을 받을 이메일을 알려주세요. 한 번만 입력하면 됩니다.</p>
        <label>
          이름
          <input ref={nameRef} type="text" name="name" placeholder="예: 홍길동" maxLength={40} autoComplete="name" autoFocus />
        </label>
        <label>
          이메일
          <input ref={emailRef} type="email" name="email" placeholder="결과를 받을 이메일 주소" required autoComplete="email" />
        </label>
        {error && <p className="demo-onboarding-error">{error}</p>}
        <div className="demo-onboarding-actions">
          <button type="button" className="demo-onboarding-skip" onClick={skip} disabled={busy}>나중에</button>
          <button type="submit" className="demo-onboarding-submit" disabled={busy}>{busy ? '등록 중…' : '시작하기'}</button>
        </div>
        <p className="demo-onboarding-note">표시 이름은 "(시연용)이름" 으로 붙습니다. 시연이 끝나면 계정과 함께 삭제됩니다.</p>
      </form>
    </div>
  );
}
