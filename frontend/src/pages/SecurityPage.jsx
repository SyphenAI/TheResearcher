import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../api/auth";

const EMPTY_FORM = {
  provider: "openai",
  label: "default",
  value: "",
  is_active: true,
};

export default function SecurityPage() {
  const { user } = useAuth();
  const [tokens, setTokens] = useState([]);
  const [providers, setProviders] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [audit, setAudit] = useState([]);
  const [auditNote, setAuditNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const [p, t] = await Promise.all([
      api("/api/security/providers"),
      api("/api/security/tokens"),
    ]);
    setProviders(p.providers || []);
    setTokens(t);
    if (user?.role === "admin") {
      try {
        const a = await api("/api/security/audit?limit=20");
        setAudit(a.events || []);
        setAuditNote(a.note || "");
      } catch {
        setAudit([]);
        setAuditNote("");
      }
    }
  }

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);

  function resetForm() {
    setEditingId(null);
    setForm({
      ...EMPTY_FORM,
      provider: providers[0] || "openai",
    });
  }

  function startEdit(token) {
    setEditingId(token.id);
    setForm({
      provider: token.provider,
      label: token.label,
      value: "",
      is_active: token.is_active,
    });
    setMessage(`Editing ${token.provider}/${token.label}. Leave secret blank to keep the current value.`);
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function saveToken(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    setBusy(true);
    try {
      if (editingId) {
        const body = {
          provider: form.provider,
          label: form.label,
          is_active: form.is_active,
        };
        if (form.value.trim()) body.value = form.value.trim();
        await api(`/api/security/tokens/${editingId}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
        setMessage("Token updated.");
      } else {
        if (!form.value.trim()) {
          setError("Secret value is required for new tokens.");
          return;
        }
        await api("/api/security/tokens", {
          method: "POST",
          body: JSON.stringify({
            provider: form.provider,
            label: form.label,
            value: form.value.trim(),
            is_active: form.is_active,
          }),
        });
        setMessage("Token stored encrypted in local data volume.");
      }
      resetForm();
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function removeToken(id) {
    if (!window.confirm("Permanently delete this token?")) return;
    setBusy(true);
    try {
      await api(`/api/security/tokens/${id}`, { method: "DELETE" });
      if (editingId === id) resetForm();
      setMessage("Token deleted.");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleToken(token) {
    setBusy(true);
    setError("");
    try {
      const path = token.is_active
        ? `/api/security/tokens/${token.id}/disable`
        : `/api/security/tokens/${token.id}/enable`;
      await api(path, { method: "POST" });
      setMessage(
        token.is_active
          ? `Disabled ${token.provider}/${token.label}. Re-enable anytime.`
          : `Re-enabled ${token.provider}/${token.label}.`
      );
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function disableAll() {
    if (!window.confirm("Disable all tokens? Values stay stored and can be re-enabled later.")) {
      return;
    }
    setBusy(true);
    try {
      const res = await api("/api/security/tokens/disable-all", { method: "POST" });
      setMessage(res.message);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function enableAll() {
    setBusy(true);
    try {
      const res = await api("/api/security/tokens/enable-all", { method: "POST" });
      setMessage(res.message);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function globalKill() {
    if (
      !window.confirm(
        "GLOBAL KILL permanently removes ALL API tokens and secret backups. This cannot be undone. Use Disable if you might need them again."
      )
    ) {
      return;
    }
    if (!window.confirm("Confirm Global Kill? Type action is permanent wipe.")) return;
    setBusy(true);
    try {
      const res = await api("/api/security/global-kill", { method: "POST" });
      setMessage(res.message);
      resetForm();
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const providerOptions = providers.length
    ? providers
    : ["openai", "anthropic", "google", "xai", "azure_openai", "custom"];

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
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>{editingId ? "Edit token" : "Add or update token"}</h2>
            {editingId && (
              <button className="btn ghost" type="button" onClick={resetForm} disabled={busy}>
                Cancel edit
              </button>
            )}
          </div>
          <p className="muted" style={{ margin: 0 }}>
            {editingId
              ? "Update provider, label, active state, or rotate the secret. Blank secret keeps the existing value."
              : "Create a new token, or re-save the same provider/label pair to replace its secret."}
          </p>
          <div className="grid-3">
            <label>
              Provider
              <select
                value={form.provider}
                onChange={(e) => setForm((f) => ({ ...f, provider: e.target.value }))}
              >
                {providerOptions.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Label
              <input
                value={form.label}
                onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              />
            </label>
            <label>
              Secret value
              <input
                type="password"
                value={form.value}
                onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))}
                placeholder={editingId ? "Leave blank to keep current" : "Paste API token"}
              />
            </label>
          </div>
          <label className="row" style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            />
            <span>Active (unchecked = disabled, reversible kill for this token)</span>
          </label>
          <div className="row">
            <button className="btn primary" type="submit" disabled={busy}>
              {editingId ? "Save edits" : "Save token"}
            </button>
            <button className="btn" type="button" onClick={disableAll} disabled={busy}>
              Disable all
            </button>
            <button className="btn" type="button" onClick={enableAll} disabled={busy}>
              Enable all
            </button>
            <button className="btn danger" type="button" onClick={globalKill} disabled={busy}>
              Global Kill
            </button>
          </div>
          <p className="footer-note">
            <strong>Disable</strong> stops use but keeps the encrypted secret so you can re-enable later.
            <strong> Global Kill</strong> permanently wipes every token from local storage.
          </p>
        </form>
      ) : (
        <div className="alert warn">
          Only the admin researcher can write tokens. You can still view masked entries if permitted.
        </div>
      )}

      <div className="panel">
        <h2>Stored tokens</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Provider</th>
              <th>Label</th>
              <th>Masked</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {tokens.map((t) => (
              <tr key={t.id} style={{ opacity: t.is_active ? 1 : 0.65 }}>
                <td>{t.provider}</td>
                <td>{t.label}</td>
                <td>
                  <code>{t.masked_value}</code>
                </td>
                <td>
                  <span className={`badge ${t.is_active ? "good" : "bad"}`}>
                    {t.is_active ? "active" : "disabled"}
                  </span>
                </td>
                <td>
                  {user?.role === "admin" && (
                    <div className="row">
                      <button className="btn ghost" type="button" disabled={busy} onClick={() => startEdit(t)}>
                        Edit
                      </button>
                      <button className="btn ghost" type="button" disabled={busy} onClick={() => toggleToken(t)}>
                        {t.is_active ? "Disable" : "Enable"}
                      </button>
                      <button className="btn ghost" type="button" disabled={busy} onClick={() => removeToken(t.id)}>
                        Delete
                      </button>
                    </div>
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
        <div className="panel stack">
          <h2 style={{ margin: 0 }}>Recent audit</h2>
          <p className="muted" style={{ margin: 0 }}>
            {auditNote ||
              "Generic security events only. Research content and real change history live in git."}
          </p>
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
              {!audit.length && (
                <tr>
                  <td colSpan={4} className="muted">
                    No security events yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
