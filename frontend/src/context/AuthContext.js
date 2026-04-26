import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { apiFetch, getToken, setToken } from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await apiFetch('/api/auth/me');
      setUser(me);
    } catch (e) {
      if (e.status === 401) {
        setToken(null);
      }
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(async (email, password) => {
    setError(null);
    try {
      const { access_token } = await apiFetch('/api/auth/login', {
        method: 'POST',
        auth: false,
        body: { email, password },
      });
      setToken(access_token);
      const me = await apiFetch('/api/auth/me');
      setUser(me);
      return true;
    } catch (e) {
      setError(typeof e.detail === 'string' ? e.detail : 'Login failed');
      return false;
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, error, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
