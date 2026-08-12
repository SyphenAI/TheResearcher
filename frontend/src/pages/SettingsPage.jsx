import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../api/auth";

const EMPTY = {
  max_agent_pct: 10,
  max_ai_checker_pct: 10,
  evidence_coverage_min_pct: 70,
  enforce_publish_gate: true,
  allow_force_export: true,
  default_evidence_mode: true,
  default_template_key: "blank",
  require_citations_for_publish: true,
  humanize_before_export_hint: true,
  semantic_scholar_api_key: "",
  openalex_api_key: "",
  follow_topics: [
    "offensive security",
    "exposure management",
    "vulnerability management",
    "breach and attack simulation",
  ],
  follow_topics_text: "",
};

const EMPTY_TEMPLATE = {
  key: "",
  title: "",
  description: "",
  sectionsText: "Overview\nAnalysis\nFindings\nRecommendations\nReferences",
};

export default function SettingsPage() {
  const { user } = useAuth();
  const [form, setForm] = useState(EMPTY);
  const [defaults, setDefaults] = useState(EMPTY);
  const [templates, setTemplates] = useState([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [templateForm, setTemplateForm] = useState(EMPTY_TEMPLATE);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const selected = useMemo(
    () => templates.find((t) => t.key === selectedKey) || null,
    [templates, selectedKey]
  );

  async function load() {
    const [s, d, t] = await Promise.all([
      api("/api/settings"),
      api("/api/settings/defaults"),
      api("/api/settings/templates").catch(() => api("/api/workspace/templates")),
    ]);
    const follow = Array.isArray(s.follow_topics) ? s.follow_topics : EMPTY.follow_topics;
    setForm({
      ...EMPTY,
      ...s,
      follow_topics: follow,
      follow_topics_text: follow.join("\n"),
    });
    setDefaults({
      ...EMPTY,
      ...d,
      follow_topics: Array.isArray(d.follow_topics) ? d.follow_topics : EMPTY.follow_topics,
    });
    const rows = t.templates || [];
    setTemplates(rows);
    if (!selectedKey && rows.length) {
      setSelectedKey(rows[0].key);
      fillTemplateForm(rows[0]);
    } else if (selectedKey) {
      const current = rows.find((r) => r.key === selectedKey);
      if (current) fillTemplateForm(current);
    }
  }

  function fillTemplateForm(t) {
    setTemplateForm({
      key: t.key || "",
      title: t.title || "",
      description: t.description || "",
      sectionsText: (t.sections || []).join("\n"),
    });
    setCreating(false);
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
      const follow = String(form.follow_topics_text || "")
        .split(/[\n,;]+/)
        .map((t) => t.trim())
        .filter((t) => t.length >= 2)
        .slice(0, 12);
      const { follow_topics_text, ...rest } = form;
      const payload = { ...rest, follow_topics: follow };
      const saved = await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      const topics = Array.isArray(saved.follow_topics) ? saved.follow_topics : follow;
      setForm({
        ...EMPTY,
        ...saved,
        follow_topics: topics,
        follow_topics_text: topics.join("\n"),
      });
      setMessage("Global rules saved.");
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

  function startCreate() {
    setCreating(true);
    setSelectedKey("");
    setTemplateForm({ ...EMPTY_TEMPLATE });
    setMessage("");
    setError("");
  }

  function parseSections(text) {
    return text
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  async function saveTemplate(e) {
    e.preventDefault();
    if (user?.role !== "admin") return;
    setBusy(true);
    setError("");
    setMessage("");
    const sections = parseSections(templateForm.sectionsText);
    if (!templateForm.title.trim()) {
      setError("Template title is required.");
      setBusy(false);
      return;
    }
    if (!sections.length) {
      setError("Add at least one section (one per line).");
      setBusy(false);
      return;
    }
    try {
      if (creating || !templateForm.key) {
        const created = await api("/api/settings/templates", {
          method: "POST",
          body: JSON.stringify({
            title: templateForm.title.trim(),
            description: templateForm.description.trim(),
            sections,
          }),
        });
        setMessage(`Created template "${created.title}". It is available in Start research.`);
        await load();
        setSelectedKey(created.key);
        fillTemplateForm(created);
      } else {
        const updated = await api(`/api/settings/templates/${encodeURIComponent(templateForm.key)}`, {
          method: "PUT",
          body: JSON.stringify({
            title: templateForm.title.trim(),
            description: templateForm.description.trim(),
            sections,
          }),
        });
        setMessage(`Updated template "${updated.title}".`);
        await load();
        setSelectedKey(updated.key);
        fillTemplateForm(updated);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function deleteSelected() {
    if (!templateForm.key) return;
    if (templateForm.key === "blank") {
      setError("The blank template cannot be deleted.");
      return;
    }
    if (!window.confirm(`Delete template "${templateForm.title}"?`)) return;
    setBusy(true);
    try {
      await api(`/api/settings/templates/${encodeURIComponent(templateForm.key)}`, {
        method: "DELETE",
      });
      setMessage("Template deleted.");
      setSelectedKey("");
      setTemplateForm({ ...EMPTY_TEMPLATE });
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function resetTemplates() {
    if (!window.confirm("Reset all templates to built-in topic packs? Custom templates will be removed.")) {
      return;
    }
    setBusy(true);
    try {
      const res = await api("/api/settings/templates/reset", { method: "POST" });
      setTemplates(res.templates || []);
      if (res.templates?.length) {
        setSelectedKey(res.templates[0].key);
        fillTemplateForm(res.templates[0]);
      }
      setMessage("Templates reset to built-in packs.");
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
          Global rules and research templates. Templates seed the Start research dropdown and description box.
        </p>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}
      {readOnly && (
        <div className="alert warn">You can view settings. Admin can edit rules and templates.</div>
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
            {(templates.length ? templates : [{ key: "blank", title: "Blank research" }]).map((t) => (
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

        <h2>Scholar search (optional keys)</h2>
        <p className="muted" style={{ margin: 0 }}>
          Crossref works without keys. Semantic Scholar is usable lightly without a key. OpenAlex often
          wants a free key from openalex.org. Keys stay local in Settings.
        </p>
        <label>
          Semantic Scholar API key
          <input
            type="password"
            value={form.semantic_scholar_api_key || ""}
            disabled={readOnly}
            onChange={(e) => setField("semantic_scholar_api_key", e.target.value)}
            placeholder="Optional"
          />
        </label>
        <label>
          OpenAlex API key
          <input
            type="password"
            value={form.openalex_api_key || ""}
            disabled={readOnly}
            onChange={(e) => setField("openalex_api_key", e.target.value)}
            placeholder="Optional free key"
          />
        </label>

        <h2>Topics to follow (dashboard feed)</h2>
        <p className="muted" style={{ margin: 0 }}>
          One topic per line. The dashboard pulls world news (Google News RSS) and recent papers for
          these themes so you can stay current outside any single project. Max 8 used per refresh.
        </p>
        <label>
          Follow topics
          <textarea
            style={{ minHeight: 120 }}
            value={form.follow_topics_text || ""}
            disabled={readOnly}
            onChange={(e) => setField("follow_topics_text", e.target.value)}
            placeholder={"offensive security\nexposure management\nvulnerability management"}
          />
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
              Reset rules to defaults
            </button>
          </div>
        )}

        <div className="alert warn">
          Product defaults: agent {defaults.max_agent_pct}%, AI checker {defaults.max_ai_checker_pct}%,
          evidence {defaults.evidence_coverage_min_pct}%. Saved values apply only on this machine.
        </div>
      </form>

      <div className="panel stack">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <h2 style={{ margin: 0 }}>Research templates</h2>
            <p className="muted" style={{ margin: "0.35rem 0 0" }}>
              These power the Start research dropdown and description box. Edit existing packs or create a
              new template for a weekly topic.
            </p>
          </div>
          {!readOnly && (
            <div className="row">
              <button className="btn primary" type="button" disabled={busy} onClick={startCreate}>
                New template
              </button>
              <button className="btn" type="button" disabled={busy} onClick={resetTemplates}>
                Reset templates
              </button>
            </div>
          )}
        </div>

        <div className="grid-2">
          <div className="stack">
            <h3 style={{ margin: 0 }}>Existing templates</h3>
            <div className="section-list" style={{ maxHeight: 360 }}>
              {templates.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  className={`section-item ${!creating && selectedKey === t.key ? "active" : ""}`}
                  onClick={() => {
                    setSelectedKey(t.key);
                    fillTemplateForm(t);
                  }}
                >
                  <div>{t.title}</div>
                  <div className="muted" style={{ fontSize: "0.8rem" }}>
                    {t.key}
                    {t.builtin ? " · built-in" : " · custom"} · {(t.sections || []).length} sections
                  </div>
                </button>
              ))}
              {!templates.length && <p className="muted">No templates yet.</p>}
            </div>
          </div>

          <form className="stack" onSubmit={saveTemplate}>
            <h3 style={{ margin: 0 }}>{creating ? "Create template" : "Edit template"}</h3>
            {!creating && templateForm.key && (
              <div className="badge">key: {templateForm.key}</div>
            )}
            <label>
              Title
              <input
                value={templateForm.title}
                disabled={readOnly}
                onChange={(e) => setTemplateForm((f) => ({ ...f, title: e.target.value }))}
                placeholder="e.g. Weekly exposure brief"
                required
              />
            </label>
            <label>
              Description (shown in Start research box)
              <textarea
                value={templateForm.description}
                disabled={readOnly}
                onChange={(e) => setTemplateForm((f) => ({ ...f, description: e.target.value }))}
                placeholder="Short blurb that helps you pick the right pack this week"
                style={{ minHeight: 90 }}
              />
            </label>
            <label>
              Sections (one per line)
              <textarea
                value={templateForm.sectionsText}
                disabled={readOnly}
                onChange={(e) => setTemplateForm((f) => ({ ...f, sectionsText: e.target.value }))}
                placeholder={"Overview\nAnalysis\nFindings\nRecommendations\nReferences"}
                style={{ minHeight: 180 }}
              />
            </label>
            {selected && !creating && (
              <div className="alert ok" style={{ margin: 0 }}>
                Preview: {selected.description || "No description yet."}
                <div className="muted" style={{ marginTop: "0.35rem" }}>
                  {(selected.sections || []).length} sections
                </div>
              </div>
            )}
            {!readOnly && (
              <div className="row">
                <button className="btn primary" type="submit" disabled={busy}>
                  {creating ? "Create template" : "Save template"}
                </button>
                {creating && (
                  <button
                    className="btn ghost"
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setCreating(false);
                      if (templates[0]) {
                        setSelectedKey(templates[0].key);
                        fillTemplateForm(templates[0]);
                      }
                    }}
                  >
                    Cancel
                  </button>
                )}
                {!creating && templateForm.key && templateForm.key !== "blank" && (
                  <button className="btn danger" type="button" disabled={busy} onClick={deleteSelected}>
                    Delete
                  </button>
                )}
              </div>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}
