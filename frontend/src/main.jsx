// 개발 중에만 전역 미처리 에러를 전체화면 오버레이로 보여준다.
// 프로덕션에서는 스택 노출·화면 가림 문제가 있어 붙이지 않는다 (ErrorBoundary 가 담당).
if (import.meta.env.DEV) {
  const showFatalOverlay = (title, body) => {
    const div = document.createElement('div');
    div.style.position = 'fixed';
    div.style.top = '0';
    div.style.left = '0';
    div.style.width = '100vw';
    div.style.height = '100dvh';
    div.style.backgroundColor = 'darkred';
    div.style.color = 'white';
    div.style.zIndex = '999999';
    div.style.padding = '20px';
    div.style.whiteSpace = 'pre-wrap';
    div.style.overflow = 'auto';
    const h1 = document.createElement('h1');
    h1.textContent = title;
    const pre = document.createElement('pre');
    pre.textContent = body;
    div.append(h1, pre);
    document.body.appendChild(div);
  };

  window.addEventListener('unhandledrejection', (event) => {
    showFatalOverlay('FATAL PROMISE ERROR', String(event.reason?.stack || event.reason));
  });

  window.addEventListener('error', (event) => {
    showFatalOverlay('FATAL BROWSER ERROR', `${event.error?.stack || ''}\n${event.message}`);
  });
}

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './index.css'
import './styles/toolShell.css'
import { GoogleOAuthProvider } from '@react-oauth/google'
import { AuthProvider } from './AuthContext.jsx'
import axios from 'axios'

// ngrok 경고 페이지 우회용 헤더
axios.defaults.headers.common['ngrok-skip-browser-warning'] = '69420';

// Get client ID from environment or use a default one for now.
const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || 'dummy-client-id';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <GoogleOAuthProvider clientId={clientId}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </GoogleOAuthProvider>
  </StrictMode>,
)

