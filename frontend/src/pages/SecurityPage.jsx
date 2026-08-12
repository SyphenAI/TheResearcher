import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../api/auth";

export default function SecurityPage() {
  const { user } = useAuth();
  const [tokens, setTokens] = useState([]);
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState("openai");
  const [label, setLabel] = useState("default");
  const [value, setValue] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [audit, setAudit] = useState([]);

  async function load() {
    const [p, t] = await Promise.all([
      api("/api/security/providers"),
      api("/api/security/tokens"),
    ]);
    setProviders(p.providers || []);
    setTokens(t);
    if (user?.role === "admin") {
      try {
        const a = await api("/api/security/audit?limit=30");
        setAudit(a);
      } catch {
        setAudit([]);
      }
    }
  }

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);

  async function saveToken(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      await api("/api/security/tokens", {
        method: "POST",
        body: JSON.stringify({ provider, label, value, is_active: true }),
      });
      setValue("");
      setMessage("Token stored encrypted in local data volume.");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeToken(id) {
    await api(`/api/security/tokens/${id}`, { method: "DELETE" });
    await load();
  }

  async function killSwitch() {
    if (!window.confirm("Remove ALL API tokens and local secret backups now?")) return;
    try {
      const res = await api("/api/security/kill-switch", { method: "POST" });
      setMessage(res.message);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="stack">
      <div>
        <h1>Security</h1>
        <p className="muted">
          Manage provider API tokens for research agents. Tokens stay local (encrypted at rest in the data volume).
        </p>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}

      {user?.role === "admin" ? (
        <form className="panel stack" onSubmit={saveToken}>
          <h2>Add or update token</h2>
          <div className="grid-3">
            <label>
              Provider
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                {(providers.length ? providers : ["openai", "anthropic", "google", "xai", "custom"]).map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Label
              <input value={label} onChange={(e) => setLabel(e.target.value)} />
            </label>
            <label>
              Secret value
              <input
                type="password"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="Paste API token"
              />
            </label>
          </div>
          <div className="row">
            <button className="btn primary" type="submit">
              Save token
            </button>
            <button className="btn danger" type="button" onClick={killSwitch}>
              Kill switch
            </button>
          </div>
        </form>
      ) : (
        <div className="alert warn">Only the admin researcher can write tokens. You can still view masked entries if permitted.</div>
      )}

      <div className="panel">
        <h2>Stored tokens</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Provider</th>
              <th>Label</th>
              <th>Masked</th>
              <th>Active</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {tokens.map((t) => (
              <tr key={t.id}>
                <td>{t.provider}</td>
                <td>{t.label}</td>
                <td>
                  <code>{t.masked_value}</code>
                </td>
                <td>{t.is_active ? "yes" : "no"}</td>
                <td>
                  {user?.role === "admin" && (
                    <button className="btn ghost" onClick={() => removeToken(t.id)}>
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!tokens.length && (
              <tr>
                <td colSpan={5} className="muted">
                  No tokens yet. Add them here when you're ready.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {user?.role === "admin" && (
        <div className="panel">
          <h2>Recent audit</h2>
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.id}>
                  <td>{a.created_at}</td>
                  <td>{a.actor}</td>
                  <td>{a.action}</td>
                  <td className="muted">{a.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
