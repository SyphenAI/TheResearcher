import React, { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../api/auth";

export default function LoginPage() {
  const { user, login, loading } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("researcher");
  const [password, setPassword] = useState("password");
  const [error, setError] = useState("");

  if (user && !user.must_change_password) return <Navigate to="/app" replace />;
  if (user && user.must_change_password) return <Navigate to="/change-password" replace />;

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      const data = await login(username, password);
      navigate(data.must_change_password ? "/change-password" : "/app");
    } catch (err) {
      setError(err.message || "Login failed");
    }
  }

  return (
    <div className="login-wrap">
      <form className="panel login-card stack" onSubmit={onSubmit}>
        <div className="brand">
          <div className="brand-mark" />
          <div>
            <h1 style={{ margin: 0, fontSize: "1.25rem" }}>TheResearcher</h1>
            <div className="muted">Local SecOps research agent</div>
          </div>
        </div>
        <p className="muted">
          First sign-in uses <code>researcher / password</code>. You'll be asked to change it right away.
        </p>
        {error && <div className="alert error">{error}</div>}
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        <button className="btn primary" disabled={loading} type="submit">
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
