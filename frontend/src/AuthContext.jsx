import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import axios from 'axios';
import { loadFeatures } from './features';

const AuthContext = createContext();

// 시연 게스트(DEMO_GUEST) 자동 입장을 이 탭에서 멈추는 표시 — 관리자가 로그아웃하고
// 구글로 로그인할 수 있어야 하므로, "명시적 로그아웃" 뒤에는 자동 입장하지 않는다.
// sessionStorage 라 탭을 닫으면 초기화된다(다음 방문자는 다시 자동 입장).
const GUEST_OPTOUT_KEY = 'wf-demo-guest-optout';

const readGuestOptout = () => {
  try {
    return Boolean(window.sessionStorage.getItem(GUEST_OPTOUT_KEY));
  } catch {
    return false;
  }
};

function readStoredAuth() {
  const token = localStorage.getItem('token');
  const savedUser = localStorage.getItem('user');

  if (!token || !savedUser) {
    return { token: null, user: null };
  }

  try {
    const [, encodedPayload] = token.split('.');
    if (!encodedPayload) throw new Error('Invalid JWT');

    const normalizedPayload = encodedPayload.replace(/-/g, '+').replace(/_/g, '/');
    const paddedPayload = normalizedPayload.padEnd(Math.ceil(normalizedPayload.length / 4) * 4, '=');
    const payload = JSON.parse(atob(paddedPayload));

    if (!payload.exp || payload.exp * 1000 <= Date.now()) {
      throw new Error('Expired JWT');
    }

    return { token, user: JSON.parse(savedUser) };
  } catch {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    return { token: null, user: null };
  }
}

export function AuthProvider({ children }) {
  const [initialAuth] = useState(readStoredAuth);
  const [user, setUser] = useState(initialAuth.user);
  const [token, setToken] = useState(initialAuth.token);

  useEffect(() => {
    if (token) {
      localStorage.setItem('token', token);
    } else {
      localStorage.removeItem('token');
    }
    if (user) {
      localStorage.setItem('user', JSON.stringify(user));
    } else {
      localStorage.removeItem('user');
    }
  }, [token, user]);

  useEffect(() => {
    const interceptor = axios.interceptors.response.use(
      response => response,
      error => {
        const requestHeaders = error.config?.headers;
        const requestAuth = requestHeaders?.get?.('Authorization')
          || requestHeaders?.Authorization
          || requestHeaders?.authorization;

        if (
          error.response?.status === 401
          && token
          && requestAuth === `Bearer ${token}`
        ) {
          setUser(null);
          setToken(null);
        }

        return Promise.reject(error);
      }
    );

    return () => axios.interceptors.response.eject(interceptor);
  }, [token]);

  const login = useCallback((userData, accessToken) => {
    setUser(userData);
    setToken(accessToken);
  }, []);

  const logout = useCallback(() => {
    // 시연 게스트 자동 입장이 곧바로 되돌리지 않도록 이 탭에서는 멈춘다(관리자 로그인 경로).
    try { window.sessionStorage.setItem(GUEST_OPTOUT_KEY, '1'); } catch { /* 저장소 불가 = 무시 */ }
    setUser(null);
    setToken(null);
  }, []);

  // 시연 게스트 입장 — 버튼(사이드바)과 자동 입장이 같은 경로를 쓴다.
  const enterGuest = useCallback(async () => {
    const res = await axios.post('/api/auth/guest');
    try { window.sessionStorage.removeItem(GUEST_OPTOUT_KEY); } catch { /* 무시 */ }
    login(res.data.user, res.data.access_token);
    return res.data.user;
  }, [login]);

  // 시연 게스트 자동 입장(DEMO_GUEST) — 비로그인 방문자를 계정 없이 바로 들여보낸다.
  // 명시적으로 로그아웃한 탭(관리자 로그인 경로)에서는 자동 입장하지 않는다.
  useEffect(() => {
    if (token) return undefined;
    let alive = true;
    loadFeatures().then((data) => {
      if (!alive || !data?.demo_guest || readGuestOptout()) return;
      axios.post('/api/auth/guest')
        .then((res) => { if (alive) login(res.data.user, res.data.access_token); })
        .catch(() => { /* 입장 실패(정원 초과 등) = 로그인 화면 그대로 */ });
    });
    return () => { alive = false; };
  }, [token, login]);

  return (
    <AuthContext.Provider value={{ user, token, login, logout, enterGuest }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
