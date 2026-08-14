import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import axios from 'axios';

const AuthContext = createContext();

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
    setUser(null);
    setToken(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
