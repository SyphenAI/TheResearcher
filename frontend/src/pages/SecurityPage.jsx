import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../api/auth";

const EMPTY_FORM = {
  provider: "openai",
  label: "default",
  value: "",
  model: "",
  is_active: true,
  use_for_research: true,
  use_for_judge: true,
};

export default function SecurityPage() {
  const { user } = useAuth();
  const [tokens, setTokens] = useState([]);
  const [providers, setProviders] = useState([]);
  const [suggestedModels, setSuggestedModels] = useState({});
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [audit, setAudit] = useState([]);
  const [auditNote, setAuditNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [backups, setBackups] = useState([]);
  const [testResult, setTestResult] = useState(null);
  const [usage, setUsage] = useState(null);

  async function loadUsage() {
    try {
      const u = await api("/api/security/usage?days=30&limit=25");
      setUsage(u);
    } catch {
      setUsage(null);
    }
  }

  async function load() {
    const [p, t] = await Promise.all([
      api("/api/security/providers"),
      api("/api/security/tokens"),
    ]);
    setProviders(p.providers || []);
    setSuggestedModels(p.suggested_models || {});
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
      await loadUsage();
      try {
        const b = await api("/api/workspace/backups");
        setBackups(b.backups || []);
      } catch {
        setBackups([]);
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
      model: token.model || "",
      is_active: token.is_active,
      use_for_research: token.use_for_research !== false,
      use_for_judge: token.use_for_judge !== false,
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
          model: form.model.trim(),
          is_active: form.is_active,
          use_for_research: form.use_for_research,
          use_for_judge: form.use_for_judge,
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
            model: form.model.trim(),
            value: form.value.trim(),
            is_active: form.is_active,
            use_for_research: form.use_for_research,
            use_for_judge: form.use_for_judge,
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

  async function toggleJudge(token) {
    setBusy(true);
    setError("");
    try {
      const enabled = !(token.use_for_judge !== false);
      await api(
        `/api/security/tokens/${token.id}/judge?enabled=${enabled ? "true" : "false"}`,
        { method: "POST" }
      );
      setMessage(
        enabled
          ? `${token.provider} included in judge panel.`
          : `${token.provider} removed from judge panel.`
      );
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleResearch(token) {
    setBusy(true);
    setError("");
    try {
      const enabled = !(token.use_for_research !== false);
      await api(
        `/api/security/tokens/${token.id}/research?enabled=${enabled ? "true" : "false"}`,
        { method: "POST" }
      );
      setMessage(
        enabled
          ? `${token.provider} included in research assistant.`
          : `${token.provider} removed from research assistant.`
      );
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function testToken(token) {
    setBusy(true);
    setError("");
    setMessage(`Testing ${token.provider}/${token.label}…`);
    setTestResult({
      pending: true,
      provider: token.provider,
      label: token.label,
      text: "Calling provider…",
    });
    try {
      const res = await api(`/api/security/tokens/${token.id}/test`, { method: "POST" });
      const latency = res.latency_ms != null ? ` (${res.latency_ms}ms)` : "";
      const text = res.ok
        ? `Test passed for ${res.provider}/${res.label}${latency}. ${res.message || ""}`.trim()
        : `Test failed for ${res.provider}/${res.label}${latency}. ${res.message || "No details."}`.trim();
      setTestResult({
        pending: false,
        ok: !!res.ok,
        provider: res.provider,
        label: res.label,
        model: res.model || "",
        text,
      });
      if (res.ok) {
        setMessage(text);
        setError("");
      } else {
        setError(text);
        setMessage("");
      }
      // Keep result visible; refresh lists without wiping banners.
      const [p, t] = await Promise.all([
        api("/api/security/providers"),
        api("/api/security/tokens"),
      ]);
      setProviders(p.providers || []);
      setSuggestedModels(p.suggested_models || {});
      setTokens(t);
      if (user?.role === "admin") {
        try {
          const a = await api("/api/security/audit?limit=20");
          setAudit(a.events || []);
          setAuditNote(a.note || "");
        } catch {
          /* ignore */
        }
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      const text = err.message || "Token test failed.";
      setError(text);
      setMessage("");
      setTestResult({
        pending: false,
        ok: false,
        provider: token.provider,
        label: token.label,
        text,
      });
      window.scrollTo({ top: 0, behavior: "smooth" });
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
  const modelSuggestions = suggestedModels[form.provider] || [];

  return (
    <div className="stack">
      <div>
        <h1>Security</h1>
        <p className="muted">
          Manage provider API tokens. Tokens stay local and encrypted. A model can be active overall, then
          included or excluded from Research and Judge separately. Usage estimates help pick cheaper models.
        </p>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}
      {testResult && (
        <div className={`alert ${testResult.pending ? "warn" : testResult.ok ? "ok" : "error"}`}>
          <strong>
            {testResult.pending
              ? "Token test running"
              : testResult.ok
                ? "Token test passed"
                : "Token test failed"}
          </strong>
          <div style={{ marginTop: "0.35rem" }}>{testResult.text}</div>
          {testResult.model ? (
            <div className="muted" style={{ marginTop: "0.25rem" }}>
              Model: {testResult.model}
            </div>
          ) : null}
        </div>
      )}

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
          <label>
            Preferred model (optional, use cheaper IDs to save tokens)
            <input
              list={`models-${form.provider}`}
              value={form.model}
              onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
              placeholder={
                modelSuggestions[0]
                  ? `e.g. ${modelSuggestions[0]}`
                  : "Leave blank for automatic default"
              }
            />
            <datalist id={`models-${form.provider}`}>
              {modelSuggestions.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </label>
          <p className="footer-note">
            Tip: Haiku / mini models are cheaper for drafts and tests. Use Sonnet/Opus only when quality
            matters. Blank preferred model falls back to provider defaults.
          </p>
          <label className="row" style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            />
            <span>Active (master switch; off means unused everywhere)</span>
          </label>
          <label className="row" style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={form.use_for_research}
              onChange={(e) => setForm((f) => ({ ...f, use_for_research: e.target.checked }))}
            />
            <span>Use for Research Assistant</span>
          </label>
          <label className="row" style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={form.use_for_judge}
              onChange={(e) => setForm((f) => ({ ...f, use_for_judge: e.target.checked }))}
            />
            <span>Use for Judge panel</span>
          </label>
          <p className="footer-note">
            Example: keep a model active for research, but turn Judge off if it is not performing well.
          </p>
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

      {user?.role === "admin" && (
        <div className="panel stack">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>Usage & cost (30 days)</h2>
            <div className="row">
              <button className="btn ghost" type="button" disabled={busy} onClick={loadUsage}>
                Refresh
              </button>
              <button
                className="btn ghost"
                type="button"
                disabled={busy || !usage?.recent?.length}
                onClick={async () => {
                  if (!window.confirm("Clear all usage log rows?")) return;
                  setBusy(true);
                  try {
                    await api("/api/security/usage", { method: "DELETE" });
                    setMessage("Usage log cleared.");
                    await loadUsage();
                  } catch (e) {
                    setError(e.message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Clear log
              </button>
            </div>
          </div>
          {usage ? (
            <>
              <p className="muted" style={{ margin: 0 }}>
                {usage.note}
              </p>
              {usage.cost_alert && (
                <div className="alert warn" style={{ margin: 0 }}>
                  <strong>Cost alert.</strong> {usage.cost_alert_message}
                </div>
              )}
              <div className="grid-3">
                <div className="metric">
                  <span className="muted">Calls</span>
                  <strong>{usage.total_calls}</strong>
                </div>
                <div className="metric">
                  <span className="muted">Tokens in / out</span>
                  <strong style={{ fontSize: "1rem" }}>
                    {usage.input_tokens} / {usage.output_tokens}
                  </strong>
                </div>
                <div className="metric">
                  <span className="muted">Est. cost USD</span>
                  <strong>${Number(usage.estimated_cost_usd || 0).toFixed(4)}</strong>
                </div>
                <div className="metric">
                  <span className="muted">Est. last 24h</span>
                  <strong className={usage.cost_alert ? "badge bad" : ""}>
                    ${Number(usage.estimated_cost_usd_24h || 0).toFixed(4)}
                  </strong>
                </div>
                <div className="metric">
                  <span className="muted">Alert at (24h)</span>
                  <strong style={{ fontSize: "1rem" }}>
                    ${Number(usage.daily_cost_alert_usd || 0).toFixed(2)}
                  </strong>
                </div>
              </div>
              {(usage.by_model || []).length > 0 && (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Provider</th>
                      <th>Model</th>
                      <th>Calls</th>
                      <th>In</th>
                      <th>Out</th>
                      <th>Est. $</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usage.by_model.map((r) => (
                      <tr key={`${r.provider}-${r.model}`}>
                        <td>{r.provider}</td>
                        <td>
                          <code>{r.model}</code>
                        </td>
                        <td>{r.calls}</td>
                        <td>{r.input_tokens}</td>
                        <td>{r.output_tokens}</td>
                        <td>${Number(r.estimated_cost_usd || 0).toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {(usage.recent || []).length > 0 && (
                <>
                  <h3 style={{ margin: 0 }}>Recent calls</h3>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>When</th>
                        <th>Purpose</th>
                        <th>Model</th>
                        <th>Tokens</th>
                        <th>Est. $</th>
                        <th>OK</th>
                      </tr>
                    </thead>
                    <tbody>
                      {usage.recent.map((e) => (
                        <tr key={e.id}>
                          <td className="muted">{e.created_at}</td>
                          <td>{e.purpose}</td>
                          <td>
                            <code>
                              {e.provider}/{e.model}
                            </code>
                          </td>
                          <td>
                            {e.input_tokens}/{e.output_tokens}
                          </td>
                          <td>${Number(e.estimated_cost_usd || 0).toFixed(4)}</td>
                          <td>
                            <span className={`badge ${e.ok ? "good" : "bad"}`}>
                              {e.ok ? "ok" : "fail"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
              {!usage.total_calls && (
                <p className="muted">No live model calls logged yet. Research, Judge, or Rewrite will fill this.</p>
              )}
            </>
          ) : (
            <p className="muted">Usage summary unavailable.</p>
          )}
        </div>
      )}

      <div className="panel">
        <h2>Stored tokens</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Provider</th>
              <th>Label</th>
              <th>Model</th>
              <th>Masked</th>
              <th>Active</th>
              <th>Research</th>
              <th>Judge</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {tokens.map((t) => (
              <tr key={t.id} style={{ opacity: t.is_active ? 1 : 0.65 }}>
                <td>{t.provider}</td>
                <td>{t.label}</td>
                <td>
                  <code>{t.model || "auto"}</code>
                </td>
                <td>
                  <code>{t.masked_value}</code>
                </td>
                <td>
                  <span className={`badge ${t.is_active ? "good" : "bad"}`}>
                    {t.is_active ? "on" : "off"}
                  </span>
                </td>
                <td>
                  <span className={`badge ${t.is_active && t.use_for_research !== false ? "good" : "bad"}`}>
                    {t.is_active && t.use_for_research !== false ? "on" : "off"}
                  </span>
                </td>
                <td>
                  <span className={`badge ${t.is_active && t.use_for_judge !== false ? "good" : "bad"}`}>
                    {t.is_active && t.use_for_judge !== false ? "on" : "off"}
                  </span>
                </td>
                <td>
                  {user?.role === "admin" && (
                    <div className="row">
                      <button className="btn ghost" type="button" disabled={busy} onClick={() => testToken(t)}>
                        Test
                      </button>
                      <button className="btn ghost" type="button" disabled={busy} onClick={() => startEdit(t)}>
                        Edit
                      </button>
                      <button className="btn ghost" type="button" disabled={busy || !t.is_active} onClick={() => toggleResearch(t)}>
                        {t.use_for_research !== false ? "Research off" : "Research on"}
                      </button>
                      <button className="btn ghost" type="button" disabled={busy || !t.is_active} onClick={() => toggleJudge(t)}>
                        {t.use_for_judge !== false ? "Judge off" : "Judge on"}
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
                <td colSpan={8} className="muted">
                  No tokens yet. Add them here when you're ready.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {user?.role === "admin" && (
        <div className="panel stack">
          <h2 style={{ margin: 0 }}>Backup / restore</h2>
          <p className="muted" style={{ margin: 0 }}>
            Local zip of DB, artifacts, and refs inside the project data directory.
          </p>
          <div className="row">
            <button
              className="btn primary"
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  const res = await api("/api/workspace/backups", { method: "POST" });
                  setMessage(`Backup created: ${res.filename}`);
                  await load();
                } catch (err) {
                  setError(err.message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Create backup
            </button>
          </div>
          <ul className="muted">
            {backups.map((b) => (
              <li key={b.filename}>
                {b.filename} ({b.size_bytes} bytes){" "}
                <button
                  className="btn ghost"
                  type="button"
                  disabled={busy}
                  onClick={async () => {
                    if (!window.confirm(`Restore ${b.filename}? Current DB is copied aside first.`)) return;
                    setBusy(true);
                    try {
                      const res = await api(
                        `/api/workspace/backups/restore?filename=${encodeURIComponent(b.filename)}`,
                        { method: "POST" }
                      );
                      setMessage(res.message || "Restored. Restart container recommended.");
                    } catch (err) {
                      setError(err.message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Restore
                </button>
              </li>
            ))}
            {!backups.length && <li>No backups yet.</li>}
          </ul>
        </div>
      )}

      {user?.role === "admin" && (
        <div className="panel stack">
          <h2 style={{ margin: 0 }}>Recent audit</h2>
          <p className="muted" style={{ margin: 0 }}>
            {auditNote ||
              "Security and system events only. Research content changes live in git and project storage."}
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>What happened</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.id}>
                  <td>{a.created_at}</td>
                  <td>{a.actor}</td>
                  <td>{a.action_label || a.action}</td>
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
