
window.addEventListener('unhandledrejection', function(event) {
  const div = document.createElement('div');
  div.style.position = 'fixed';
  div.style.top = '0';
  div.style.left = '0';
  div.style.width = '100vw';
  div.style.height = '100vh';
  div.style.backgroundColor = 'darkred';
  div.style.color = 'white';
  div.style.zIndex = '999999';
  div.style.padding = '20px';
  div.style.whiteSpace = 'pre-wrap';
  div.style.overflow = 'auto';
  div.innerHTML = '<h1>FATAL PROMISE ERROR</h1><pre>' + (event.reason?.stack || event.reason) + '</pre>';
  document.body.appendChild(div);
});


window.addEventListener('error', function(event) {
  const div = document.createElement('div');
  div.style.position = 'fixed';
  div.style.top = '0';
  div.style.left = '0';
  div.style.width = '100vw';
  div.style.height = '100vh';
  div.style.backgroundColor = 'darkred';
  div.style.color = 'white';
  div.style.zIndex = '999999';
  div.style.padding = '20px';
  div.style.whiteSpace = 'pre-wrap';
  div.style.overflow = 'auto';
  div.innerHTML = '<h1>FATAL BROWSER ERROR</h1><pre>' + event.error?.stack + '</pre><p>' + event.message + '</p>';
  document.body.appendChild(div);
});

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './index.css'
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

