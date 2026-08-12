import React, { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../api/auth";

export default function ChangePasswordPage() {
  const { user, refresh, logout } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState("password");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  if (!user) return <Navigate to="/login" replace />;

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setOk("");
    if (newPassword !== confirm) {
      setError("New passwords don't match.");
      return;
    }
    if (newPassword.length < 8) {
      setError("Use at least 8 characters.");
      return;
    }
    try {
      await api("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      setOk("Password updated. Taking you to the dashboard.");
      await refresh();
      navigate("/app");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="login-wrap">
      <form className="panel login-card stack" onSubmit={onSubmit}>
        <h1 style={{ fontSize: "1.25rem" }}>Change password</h1>
        <p className="muted">Required on first login for the admin researcher account.</p>
        {error && <div className="alert error">{error}</div>}
        {ok && <div className="alert ok">{ok}</div>}
        <label>
          Current password
          <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
        </label>
        <label>
          New password
          <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        </label>
        <label>
          Confirm new password
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </label>
        <div className="row">
          <button className="btn primary" type="submit">
            Save password
          </button>
          <button
            className="btn ghost"
            type="button"
            onClick={() => {
              logout();
              navigate("/login");
            }}
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
