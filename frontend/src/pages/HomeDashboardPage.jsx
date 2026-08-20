import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { formatLocalDateTime } from "../utils/datetime";

function formatWhen(value) {
  if (!value) return "—";
  return formatLocalDateTime(value) || "—";
}

export default function HomeDashboardPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [templateKey, setTemplateKey] = useState("blank");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [providers, setProviders] = useState([]);
  const [archived, setArchived] = useState([]);
  const [globalMaxAgent, setGlobalMaxAgent] = useState(10);
  const [searchQ, setSearchQ] = useState("");
  const [feed, setFeed] = useState(null);
  const [feedBusy, setFeedBusy] = useState(false);
  const [feedDays, setFeedDays] = useState(7);
  const [costAlert, setCostAlert] = useState(null);

  async function loadProjects() {
    const data = await api("/api/projects");
    setProjects(data);
  }

  async function loadArchived() {
    try {
      const data = await api("/api/projects/archived");
      setArchived(data.projects || []);
    } catch {
      setArchived([]);
    }
  }

  async function loadFeed(daysOverride, { force = false } = {}) {
    const days = Number(daysOverride ?? feedDays) || 7;
    setFeedBusy(true);
    try {
      const q = `/api/workspace/feed?days=${days}${force ? "&refresh=true" : ""}`;
      const f = await api(q);
      setFeed(f);
      if (f?.days) setFeedDays(f.days);
    } catch {
      setFeed(null);
    } finally {
      setFeedBusy(false);
    }
  }

  useEffect(() => {
    Promise.all([
      loadProjects(),
      loadArchived(),
      api("/api/workspace/templates"),
      api("/api/workspace/providers").catch(() => ({ active: [] })),
      api("/api/settings").catch(() => ({ max_agent_pct: 10, default_template_key: "blank" })),
      loadFeed(),
      api("/api/security/usage?days=1&limit=5").catch(() => null),
    ])
      .then(([, , t, p, s, , u]) => {
        setTemplates(t.templates || []);
        setTemplateKey(s.default_template_key || t.default || "blank");
        setProviders(p.active || []);
        setGlobalMaxAgent(s.max_agent_pct ?? 10);
        if (u?.cost_alert) {
          setCostAlert(u.cost_alert_message || "Daily estimated LLM cost alert.");
        } else {
          setCostAlert(null);
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const metrics = useMemo(() => {
    const active = projects.filter((p) => (p.status || "").toLowerCase() === "active");
    const completed = projects.filter((p) =>
      ["completed", "done", "archived"].includes((p.status || "").toLowerCase())
    );
    const avgProgress = projects.length
      ? projects.reduce((sum, p) => sum + (p.progress_pct || 0), 0) / projects.length
      : 0;
    const needsHumanEdit = projects.filter(
      (p) => (p.agent_contribution_pct || 0) >= (globalMaxAgent ?? 10)
    ).length;
    const openTasks = projects.reduce(
      (sum, p) => sum + Math.max(0, (p.task_count || 0) - (p.tasks_done || 0)),
      0
    );
    return {
      total: projects.length,
      active: active.length,
      completed: completed.length,
      avgProgress: Math.round(avgProgress * 10) / 10,
      needsHumanEdit,
      openTasks,
      liveProviders: providers.length,
    };
  }, [projects, providers, globalMaxAgent]);

  const selectedTemplate = templates.find((t) => t.key === templateKey);

  async function startResearch(e) {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const project = await api("/api/projects", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(),
          description: description.trim(),
          template_key: templateKey,
          evidence_mode: true,
          max_agent_pct: 10,
        }),
      });
      setTitle("");
      setDescription("");
      setMessage("Research started. Opening workspace…");
      navigate(`/app/research/${project.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 style={{ marginBottom: 0 }}>Dashboard</h1>
          <p className="muted" style={{ margin: "0.35rem 0 0" }}>
            Pick a topic template for this week's research, or open an existing project.
          </p>
        </div>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            const q = searchQ.trim();
            if (q.length >= 2) navigate(`/search?q=${encodeURIComponent(q)}`);
          }}
        >
          <input
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            placeholder="Search library or open Search for scholar"
            style={{ minWidth: 220 }}
          />
          <button className="btn" type="submit">
            Search
          </button>
        </form>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}
      {costAlert && (
        <div className="alert warn">
          <strong>Cost alert.</strong> {costAlert}{" "}
          <button className="btn ghost" type="button" onClick={() => navigate("/security")}>
            Open usage
          </button>
        </div>
      )}

      <div className="grid-3">
        <div className="metric">
          <span className="muted">Active research</span>
          <strong>{metrics.active}</strong>
        </div>
        <div className="metric">
          <span className="muted">Average progress</span>
          <strong>{metrics.avgProgress}%</strong>
        </div>
        <div className="metric">
          <span className="muted">Open tasks</span>
          <strong>{metrics.openTasks}</strong>
        </div>
        <div className="metric">
          <span className="muted">Need human edit (&gt;{globalMaxAgent}% agent)</span>
          <strong className={metrics.needsHumanEdit ? "badge bad" : "badge good"}>
            {metrics.needsHumanEdit}
          </strong>
        </div>
        <div className="metric">
          <span className="muted">Live AI providers</span>
          <strong className={metrics.liveProviders ? "badge good" : "badge"}>
            {metrics.liveProviders}
          </strong>
        </div>
        <div className="metric">
          <span className="muted">Completed</span>
          <strong>{metrics.completed}</strong>
        </div>
      </div>

      {!metrics.liveProviders && (
        <div className="alert warn">
          No active provider tokens yet. Research Assistant will use the local scaffold until you add
          OpenAI, Anthropic, and/or xAI (Grok) tokens under Security.
        </div>
      )}

      <div className="grid-2 home-layout">
        <div className="panel stack">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>Current research</h2>
            <span className="badge">{metrics.total} total</span>
          </div>

          {loading && <p className="muted">Loading projects…</p>}

          {!loading && !projects.length && (
            <div className="empty-state">
              <h3>No research yet</h3>
              <p className="muted">
                Start a new project on the right. Choose a template that matches this week's topic.
              </p>
            </div>
          )}

          <div className="project-cards">
            {projects.map((p) => (
              <button
                key={p.id}
                type="button"
                className="project-card"
                onClick={() => navigate(`/app/research/${p.id}`)}
              >
                <div className="row" style={{ justifyContent: "space-between", width: "100%" }}>
                  <div className="project-card-title">{p.title}</div>
                  <span className={`badge ${p.status === "active" ? "good" : ""}`}>{p.status}</span>
                </div>
                <p className="muted project-card-desc">{p.description || "No description yet."}</p>
                <div className="progress-block">
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span className="muted">Progress</span>
                    <strong>{p.progress_pct ?? 0}%</strong>
                  </div>
                  <div className="progress-track" aria-hidden="true">
                    <div
                      className="progress-fill"
                      style={{ width: `${Math.min(100, Math.max(0, p.progress_pct || 0))}%` }}
                    />
                  </div>
                </div>
                <div className="project-card-meta muted">
                  <span>Template {p.template_key || "blank"}</span>
                  <span>
                    Sections {p.sections_with_content}/{p.section_count}
                  </span>
                  <span className={(p.agent_contribution_pct || 0) >= 10 ? "warn-text" : ""}>
                    Agent {p.agent_contribution_pct}%
                  </span>
                  <span>Updated {formatWhen(p.updated_at)}</span>
                </div>
                <div className="row" style={{ justifyContent: "space-between", width: "100%" }}>
                  <div className="project-card-cta">Open research desk →</div>
                  <button
                    className="btn ghost"
                    type="button"
                    onClick={async (e) => {
                      e.stopPropagation();
                      if (!window.confirm(`Archive "${p.title}"? It leaves the dashboard and moves to storage/archive.`)) {
                        return;
                      }
                      setBusy(true);
                      try {
                        await api(`/api/projects/${p.id}`, { method: "DELETE" });
                        setMessage("Project archived under storage/archive/.");
                        await loadProjects();
                        await loadArchived();
                      } catch (err) {
                        setError(err.message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Archive
                  </button>
                </div>
              </button>
            ))}
          </div>

          {!!archived.length && (
            <div className="stack" style={{ marginTop: "1rem" }}>
              <h2 style={{ margin: 0 }}>Archived research</h2>
              <p className="muted" style={{ margin: 0 }}>
                Deleted projects leave the dashboard and move under <code>storage/archive/</code>. Restore
                brings them back.
              </p>
              {archived.map((p) => (
                <div key={p.id} className="project-card" style={{ cursor: "default" }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <div>
                      <div className="project-card-title">{p.title}</div>
                      <div className="muted" style={{ fontSize: "0.85rem" }}>
                        Archived {p.archived_at || "—"} · {p.storage_path || "storage/archive"}
                      </div>
                    </div>
                    <button
                      className="btn primary"
                      type="button"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true);
                        try {
                          await api(`/api/projects/${p.id}/restore`, { method: "POST" });
                          setMessage(`Restored ${p.title}`);
                          await loadProjects();
                          await loadArchived();
                        } catch (err) {
                          setError(err.message);
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      Restore
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="panel stack">
          <h2 style={{ margin: 0 }}>Start new research</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            Choose a template from the dropdown based on the topic you are researching this week.
          </p>
          <form className="stack" onSubmit={startResearch}>
            <label>
              Template
              <select value={templateKey} onChange={(e) => setTemplateKey(e.target.value)}>
                {(templates.length
                  ? templates
                  : [{ key: "blank", title: "Blank research" }]
                ).map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.title}
                  </option>
                ))}
              </select>
            </label>
            {selectedTemplate && (
              <div className="alert ok" style={{ margin: 0 }}>
                {selectedTemplate.description}
                <div className="muted" style={{ marginTop: "0.4rem" }}>
                  {selectedTemplate.sections?.length || 0} sections
                </div>
              </div>
            )}
            <label>
              Research title
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Exposure prioritization for internet-facing SaaS"
                required
              />
            </label>
            <label>
              Short description (optional)
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Client problem, audience, or interview panel angle"
                style={{ minHeight: 90 }}
              />
            </label>
            <button className="btn primary" type="submit" disabled={busy || !title.trim()}>
              {busy ? "Starting…" : "Start research"}
            </button>
          </form>
        </div>
      </div>

      <div className="panel stack">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <h2 style={{ margin: 0 }}>Research radar</h2>
            <p className="muted" style={{ margin: "0.25rem 0 0" }}>
              Live Google News RSS + recent papers for topics you follow. Default window: last 7 days.
            </p>
          </div>
          <div className="row">
            <label style={{ margin: 0 }}>
              Window
              <select
                value={feedDays}
                disabled={feedBusy}
                onChange={(e) => {
                  const d = Number(e.target.value) || 7;
                  setFeedDays(d);
                  loadFeed(d);
                }}
              >
                <option value={1}>Last 24 hours</option>
                <option value={3}>Last 3 days</option>
                <option value={7}>Last 7 days</option>
                <option value={14}>Last 14 days</option>
                <option value={30}>Last 30 days</option>
              </select>
            </label>
            <button
              className="btn primary"
              type="button"
              onClick={() => loadFeed(feedDays, { force: true })}
              disabled={feedBusy}
              title="Force live re-pull (bypasses short cache)"
            >
              {feedBusy ? "Updating…" : "Update now"}
            </button>
            <button className="btn" type="button" onClick={() => navigate("/settings")}>
              Follow topics
            </button>
            <button className="btn" type="button" onClick={() => navigate("/search?tab=scholar")}>
              Scholar search
            </button>
          </div>
        </div>
        {feed?.topics?.length > 0 && (
          <div className="row">
            {feed.topics.map((t) => (
              <span className="badge" key={t}>
                {t}
              </span>
            ))}
          </div>
        )}
        <p className="muted" style={{ margin: 0 }}>
          {feed?.message || ""}
          {feed?.generated_at
            ? ` · Updated ${formatLocalDateTime(feed.generated_at)}`
            : ""}
          {feed?.cached
            ? ` · cached (~${feed.cache_ttl_sec || "?"}s left)`
            : feed?.live
              ? " · live pull"
              : ""}
        </p>
        {feed?.note && (
          <p className="muted" style={{ margin: 0, fontSize: "0.82rem" }}>
            {feed.note}
          </p>
        )}
        {!feed?.items?.length && !feedBusy && (
          <p className="muted">
            No items in this window. Click Update now, broaden topics in Settings, or widen the window.
          </p>
        )}
        <div className="stack" style={{ maxHeight: 420, overflow: "auto" }}>
          {(feed?.items || []).slice(0, 20).map((item, idx) => (
            <div
              key={`${item.kind}-${item.url || item.title}-${idx}`}
              className="panel stack"
              style={{ padding: "0.6rem" }}
            >
              <div className="row" style={{ justifyContent: "space-between" }}>
                <strong style={{ fontSize: "0.92rem" }}>{item.title}</strong>
                <span className={`badge ${item.kind === "news" ? "good" : ""}`}>
                  {item.kind === "news" ? "news" : "paper"}
                </span>
              </div>
              <div className="muted" style={{ fontSize: "0.8rem" }}>
                {item.topic ? `Topic: ${item.topic} · ` : ""}
                {item.source || item.provider || ""}
                {item.published_at ? ` · ${item.published_at}` : ""}
                {item.cited_by_count ? ` · cited≈${item.cited_by_count}` : ""}
              </div>
              {item.snippet && (
                <div style={{ fontSize: "0.85rem" }}>
                  {item.snippet.slice(0, 200)}
                  {item.snippet.length > 200 ? "…" : ""}
                </div>
              )}
              <div className="row">
                {item.url && (
                  <a className="btn ghost" href={item.url} target="_blank" rel="noreferrer">
                    Open
                  </a>
                )}
                <button
                  className="btn"
                  type="button"
                  onClick={() =>
                    navigate(
                      `/search?tab=scholar&q=${encodeURIComponent(item.topic || item.title || "")}`
                    )
                  }
                >
                  Search scholar
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
