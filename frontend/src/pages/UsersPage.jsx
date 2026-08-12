import React, { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../api/auth";

export default function UsersPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("researcher");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  if (user && user.role !== "admin") return <Navigate to="/app" replace />;

  async function load() {
    const rows = await api("/api/auth/users");
    setUsers(rows);
  }

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);

  async function createUser(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      await api("/api/auth/users", {
        method: "POST",
        body: JSON.stringify({
          username,
          password,
          role,
          display_name: displayName || username,
        }),
      });
      setUsername("");
      setPassword("");
      setDisplayName("");
      setMessage("User created. They must change password on first login.");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="stack">
      <div>
        <h1>Users</h1>
        <p className="muted">Admin researcher can create teammates with roles and permissions.</p>
      </div>
      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}

      <form className="panel stack" onSubmit={createUser}>
        <h2>Create user</h2>
        <div className="grid-3">
          <label>
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label>
            Display name
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </label>
          <label>
            Role
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="researcher">researcher</option>
              <option value="reviewer">reviewer</option>
              <option value="admin">admin</option>
            </select>
          </label>
        </div>
        <label>
          Temporary password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
        </label>
        <button className="btn primary" type="submit">
          Create user
        </button>
      </form>

      <div className="panel">
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Username</th>
              <th>Display</th>
              <th>Role</th>
              <th>Must change pw</th>
              <th>Active</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td>{u.username}</td>
                <td>{u.display_name}</td>
                <td>{u.role}</td>
                <td>{u.must_change_password ? "yes" : "no"}</td>
                <td>{u.is_active ? "yes" : "no"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
