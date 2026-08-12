import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../api/auth";

const EMPTY = {
  max_agent_pct: 10,
  max_ai_checker_pct: 10,
  evidence_coverage_min_pct: 70,
  enforce_publish_gate: true,
  allow_force_export: true,
  default_evidence_mode: true,
  default_template_key: "gartner_panel",
  require_citations_for_publish: true,
  humanize_before_export_hint: true,
};

export default function SettingsPage() {
  const { user } = useAuth();
  const [form, setForm] = useState(EMPTY);
  const [defaults, setDefaults] = useState(EMPTY);
  const [templates, setTemplates] = useState([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const [s, d, t] = await Promise.all([
      api("/api/settings"),
      api("/api/settings/defaults"),
      api("/api/workspace/templates").catch(() => ({ templates: [] })),
    ]);
    setForm({ ...EMPTY, ...s });
    setDefaults({ ...EMPTY, ...d });
    setTemplates(t.templates || []);
  }

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);

  function setField(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function save(e) {
    e.preventDefault();
    if (user?.role !== "admin") {
      setError("Only admin can change global settings.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify(form),
      });
      setForm({ ...EMPTY, ...saved });
      setMessage("Global rules saved. New projects and publish checks will use these values.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function resetDefaults() {
    if (!window.confirm("Reset all global rules to defaults?")) return;
    setBusy(true);
    try {
      const saved = await api("/api/settings/reset", { method: "POST" });
      setForm({ ...EMPTY, ...saved });
      setMessage("Settings reset to defaults.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const readOnly = user?.role !== "admin";

  return (
    <div className="stack">
      <div>
        <h1>Settings</h1>
        <p className="muted">
          Global rules for publish quality, agent contribution targets, and defaults.
          Make them stricter for panel polish or looser while drafting.
        </p>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}
      {readOnly && (
        <div className="alert warn">You can view settings. Admin can edit global rules.</div>
      )}

      <form className="panel stack" onSubmit={save}>
        <h2 style={{ margin: 0 }}>Publish and quality gates</h2>

        <label>
          Max agent contribution % (publish target)
          <input
            type="number"
            min={0}
            max={100}
            step={0.5}
            value={form.max_agent_pct}
            disabled={readOnly}
            onChange={(e) => setField("max_agent_pct", Number(e.target.value))}
          />
        </label>
        <p className="muted" style={{ margin: 0 }}>
          Default is 10%. Raise this (for example 25 or 40) while drafting if the gate feels too tight.
        </p>

        <label>
          Max AI checker likelihood %
          <input
            type="number"
            min={0}
            max={100}
            step={0.5}
            value={form.max_ai_checker_pct}
            disabled={readOnly}
            onChange={(e) => setField("max_ai_checker_pct", Number(e.target.value))}
          />
        </label>

        <label>
          Minimum evidence coverage %
          <input
            type="number"
            min={0}
            max={100}
            step={1}
            value={form.evidence_coverage_min_pct}
            disabled={readOnly}
            onChange={(e) => setField("evidence_coverage_min_pct", Number(e.target.value))}
          />
        </label>

        <label className="row" style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
          <input
            type="checkbox"
            checked={!!form.enforce_publish_gate}
            disabled={readOnly}
            onChange={(e) => setField("enforce_publish_gate", e.target.checked)}
          />
          <span>Enforce publish gate on Word export</span>
        </label>

        <label className="row" style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
          <input
            type="checkbox"
            checked={!!form.require_citations_for_publish}
            disabled={readOnly}
            onChange={(e) => setField("require_citations_for_publish", e.target.checked)}
          />
          <span>Require citation coverage for publish</span>
        </label>

        <label className="row" style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
          <input
            type="checkbox"
            checked={!!form.allow_force_export}
            disabled={readOnly}
            onChange={(e) => setField("allow_force_export", e.target.checked)}
          />
          <span>Allow admin force export (bypass gate)</span>
        </label>

        <h2>Research defaults</h2>
        <label>
          Default project template
          <select
            value={form.default_template_key}
            disabled={readOnly}
            onChange={(e) => setField("default_template_key", e.target.value)}
          >
            {(templates.length
              ? templates
              : [{ key: "gartner_panel", title: "Gartner panel" }]
            ).map((t) => (
              <option key={t.key} value={t.key}>
                {t.title}
              </option>
            ))}
          </select>
        </label>

        <label className="row" style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
          <input
            type="checkbox"
            checked={!!form.default_evidence_mode}
            disabled={readOnly}
            onChange={(e) => setField("default_evidence_mode", e.target.checked)}
          />
          <span>Evidence mode on for new projects</span>
        </label>

        <label className="row" style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
          <input
            type="checkbox"
            checked={!!form.humanize_before_export_hint}
            disabled={readOnly}
            onChange={(e) => setField("humanize_before_export_hint", e.target.checked)}
          />
          <span>Show humanize-before-export guidance in the desk</span>
        </label>

        {!readOnly && (
          <div className="row">
            <button className="btn primary" type="submit" disabled={busy}>
              Save settings
            </button>
            <button className="btn" type="button" disabled={busy} onClick={resetDefaults}>
              Reset to defaults
            </button>
          </div>
        )}

        <div className="alert warn">
          Current defaults baked into the product: agent {defaults.max_agent_pct}%, AI checker{" "}
          {defaults.max_ai_checker_pct}%, evidence {defaults.evidence_coverage_min_pct}%. Your saved
          values override those for this local install only.
        </div>
      </form>
    </div>
  );
}
