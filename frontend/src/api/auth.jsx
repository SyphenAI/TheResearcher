import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, login as apiLogin, setToken } from "./client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function refresh() {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api("/api/auth/me");
      setUser(me);
      setError("");
    } catch (err) {
      setToken("");
      setUser(null);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function login(username, password) {
    setLoading(true);
    try {
      const data = await apiLogin(username, password);
      await refresh();
      return data;
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    setToken("");
    setUser(null);
  }

  const value = useMemo(
    () => ({ user, loading, error, login, logout, refresh }),
    [user, loading, error]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
