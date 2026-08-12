import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

function formatWhen(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
}

export default function HomeDashboardPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  async function loadProjects() {
    const data = await api("/api/projects");
    setProjects(data);
  }

  useEffect(() => {
    loadProjects()
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
    const needsHumanEdit = projects.filter((p) => (p.agent_contribution_pct || 0) >= 10).length;
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
    };
  }, [projects]);

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

  function openResearch(id) {
    navigate(`/app/research/${id}`);
  }

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 style={{ marginBottom: 0 }}>Dashboard</h1>
          <p className="muted" style={{ margin: "0.35rem 0 0" }}>
            Pick up current research or start a new project. Open a card to enter the research desk.
          </p>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}

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
          <span className="muted">Completed</span>
          <strong>{metrics.completed}</strong>
        </div>
        <div className="metric">
          <span className="muted">Total projects</span>
          <strong>{metrics.total}</strong>
        </div>
        <div className="metric">
          <span className="muted">Need human edit (&gt;10% agent)</span>
          <strong className={metrics.needsHumanEdit ? "badge bad" : "badge good"}>
            {metrics.needsHumanEdit}
          </strong>
        </div>
      </div>

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
                Start a new project on the right. You'll land in the research desk with sections, prompts, and the paper view.
              </p>
            </div>
          )}

          <div className="project-cards">
            {projects.map((p) => (
              <button
                key={p.id}
                type="button"
                className="project-card"
                onClick={() => openResearch(p.id)}
              >
                <div className="row" style={{ justifyContent: "space-between", width: "100%" }}>
                  <div className="project-card-title">{p.title}</div>
                  <span className={`badge ${p.status === "active" ? "good" : ""}`}>{p.status}</span>
                </div>
                {p.description ? (
                  <p className="muted project-card-desc">{p.description}</p>
                ) : (
                  <p className="muted project-card-desc">No description yet.</p>
                )}

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
                  <span>
                    Sections {p.sections_with_content}/{p.section_count}
                  </span>
                  <span>
                    Tasks {p.tasks_done}/{p.task_count}
                  </span>
                  <span className={(p.agent_contribution_pct || 0) >= 10 ? "warn-text" : ""}>
                    Agent {p.agent_contribution_pct}%
                  </span>
                  <span>Updated {formatWhen(p.updated_at)}</span>
                </div>
                <div className="project-card-cta">Open research desk →</div>
              </button>
            ))}
          </div>
        </div>

        <div className="panel stack">
          <h2 style={{ margin: 0 }}>Start new research</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            Creates a project with default sections and opens the workspace.
          </p>
          <form className="stack" onSubmit={startResearch}>
            <label>
              Research title
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. SaaS exposure review for vendor X"
                required
              />
            </label>
            <label>
              Short description (optional)
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Scope, audience, or why this research matters"
                style={{ minHeight: 110 }}
              />
            </label>
            <button className="btn primary" type="submit" disabled={busy || !title.trim()}>
              {busy ? "Starting…" : "Start research"}
            </button>
          </form>
          <div className="alert warn" style={{ marginTop: "0.5rem" }}>
            Tip: keep published drafts under 10% agent contribution. Use Humanize and your own edits before export.
          </div>
        </div>
      </div>
    </div>
  );
}
