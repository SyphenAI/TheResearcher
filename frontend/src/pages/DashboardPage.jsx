import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";

export default function DashboardPage() {
  const [projects, setProjects] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [sections, setSections] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [artifacts, setArtifacts] = useState([]);
  const [sectionId, setSectionId] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [assistantOut, setAssistantOut] = useState("");
  const [judgeOut, setJudgeOut] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [newProjectTitle, setNewProjectTitle] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [busy, setBusy] = useState(false);

  const activeProject = useMemo(
    () => projects.find((p) => p.id === activeId) || null,
    [projects, activeId]
  );
  const activeSection = useMemo(
    () => sections.find((s) => s.id === sectionId) || null,
    [sections, sectionId]
  );

  async function loadProjects() {
    const data = await api("/api/projects");
    setProjects(data);
    if (!activeId && data.length) setActiveId(data[0].id);
  }

  async function loadProjectDetails(projectId) {
    if (!projectId) return;
    const [secs, tks, arts] = await Promise.all([
      api(`/api/projects/${projectId}/sections`),
      api(`/api/projects/${projectId}/tasks`),
      api(`/api/projects/${projectId}/artifacts`),
    ]);
    setSections(secs);
    setTasks(tks);
    setArtifacts(arts);
    if (secs.length) {
      const still = secs.find((s) => s.id === sectionId);
      setSectionId(still ? still.id : secs[0].id);
      if (!still) setPrompt(secs[0].prompt || "");
    } else {
      setSectionId(null);
    }
  }

  useEffect(() => {
    loadProjects().catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (activeId) {
      loadProjectDetails(activeId).catch((e) => setError(e.message));
    }
  }, [activeId]);

  useEffect(() => {
    if (activeSection) setPrompt(activeSection.prompt || "");
  }, [sectionId]);

  async function createProject() {
    if (!newProjectTitle.trim()) return;
    setBusy(true);
    try {
      const p = await api("/api/projects", {
        method: "POST",
        body: JSON.stringify({ title: newProjectTitle.trim(), description: "" }),
      });
      setNewProjectTitle("");
      await loadProjects();
      setActiveId(p.id);
      setMessage("Project created.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveSectionContent(content_md) {
    if (!activeProject || !activeSection) return;
    const updated = await api(
      `/api/projects/${activeProject.id}/sections/${activeSection.id}`,
      {
        method: "PATCH",
        body: JSON.stringify({ content_md, prompt }),
      }
    );
    setSections((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    await loadProjects();
  }

  async function runAssistant() {
    if (!prompt.trim()) return;
    setBusy(true);
    setError("");
    try {
      if (activeSection) {
        await api(`/api/projects/${activeProject.id}/sections/${activeSection.id}`, {
          method: "PATCH",
          body: JSON.stringify({ prompt }),
        });
      }
      const result = await api("/api/research/assistant", {
        method: "POST",
        body: JSON.stringify({
          prompt,
          section_id: sectionId,
          mode: "research",
          rewrite_human: true,
        }),
      });
      setAssistantOut(result.content);
      setMessage(result.notes || "Assistant draft ready.");
      await loadProjects();
      await loadProjectDetails(activeId);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function applyAssistant() {
    if (!assistantOut || !sectionId) return;
    setBusy(true);
    try {
      const updated = await api("/api/research/assistant/apply", {
        method: "POST",
        body: JSON.stringify({
          section_id: sectionId,
          content: assistantOut,
          mark_as_agent: true,
        }),
      });
      setSections((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      setMessage("Assistant output applied to the paper (counted as agent contribution).");
      await loadProjects();
      await loadProjectDetails(activeId);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function humanizeSection() {
    if (!activeSection) return;
    setBusy(true);
    try {
      const result = await api("/api/research/rewrite", {
        method: "POST",
        body: JSON.stringify({ text: activeSection.content_md, strength: "high" }),
      });
      await saveSectionContent(result.content);
      setMessage("Section rewritten toward a more human voice. Edit further before publish.");
      await loadProjectDetails(activeId);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function judgeSection() {
    if (!activeSection) return;
    setBusy(true);
    try {
      const result = await api("/api/research/judge", {
        method: "POST",
        body: JSON.stringify({
          text: activeSection.content_md,
          project_id: activeId,
          section_id: sectionId,
        }),
      });
      setJudgeOut(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function exportDocx() {
    if (!activeProject) return;
    const combined = sections
      .map((s) => s.content_md)
      .join("\n\n---\n\n");
    const res = await api("/api/research/export/docx", {
      method: "POST",
      body: JSON.stringify({ title: activeProject.title, content_md: combined }),
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${activeProject.title.replace(/\s+/g, "_")}.docx`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function addTask() {
    if (!taskTitle.trim() || !activeId) return;
    await api(`/api/projects/${activeId}/tasks`, {
      method: "POST",
      body: JSON.stringify({ title: taskTitle.trim() }),
    });
    setTaskTitle("");
    await loadProjectDetails(activeId);
  }

  async function uploadArtifact(e) {
    const file = e.target.files?.[0];
    if (!file || !activeId) return;
    const form = new FormData();
    form.append("file", file);
    await api(`/api/research/projects/${activeId}/artifacts`, {
      method: "POST",
      body: form,
    });
    await loadProjectDetails(activeId);
    setMessage(`Uploaded ${file.name}`);
  }

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1 style={{ marginBottom: 0 }}>Research desk</h1>
          <p className="muted" style={{ margin: "0.25rem 0 0" }}>
            Left prompt plane, right live paper. Keep final agent share under 10%.
          </p>
        </div>
        <div className="row">
          <input
            style={{ width: 220 }}
            placeholder="New project title"
            value={newProjectTitle}
            onChange={(e) => setNewProjectTitle(e.target.value)}
          />
          <button className="btn primary" onClick={createProject} disabled={busy}>
            New project
          </button>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}

      <div className="tabs">
        {projects.map((p) => (
          <button
            key={p.id}
            className={`tab ${p.id === activeId ? "active" : ""}`}
            onClick={() => setActiveId(p.id)}
          >
            {p.title}
          </button>
        ))}
      </div>

      {activeProject && (
        <>
          <div className="grid-3">
            <div className="metric">
              <span className="muted">Agent contribution</span>
              <strong className={activeProject.agent_contribution_pct >= 10 ? "badge bad" : ""}>
                {activeProject.agent_contribution_pct}%
              </strong>
            </div>
            <div className="metric">
              <span className="muted">Human contribution</span>
              <strong>{activeProject.human_contribution_pct}%</strong>
            </div>
            <div className="metric">
              <span className="muted">Status</span>
              <strong style={{ fontSize: "1rem" }}>{activeProject.status}</strong>
            </div>
          </div>

          <div className="grid-2">
            <div className="panel stack">
              <h2>Sections</h2>
              <div className="section-list">
                {sections.map((s) => (
                  <button
                    key={s.id}
                    className={`section-item ${s.id === sectionId ? "active" : ""}`}
                    onClick={() => setSectionId(s.id)}
                  >
                    <div>{s.title}</div>
                    <div className="muted" style={{ fontSize: "0.8rem" }}>
                      agent {s.agent_chars} · human {s.human_chars}
                    </div>
                  </button>
                ))}
              </div>

              <label>
                Research prompt
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="What should the assistant explore in this section?"
                />
              </label>

              <div className="row">
                <button className="btn primary" onClick={runAssistant} disabled={busy}>
                  Research Assistant
                </button>
                <button className="btn" onClick={applyAssistant} disabled={!assistantOut || busy}>
                  Apply to paper
                </button>
                <button className="btn" onClick={humanizeSection} disabled={busy}>
                  Humanize
                </button>
                <button className="btn" onClick={judgeSection} disabled={busy}>
                  Judge
                </button>
                <button className="btn" onClick={exportDocx}>
                  Export Word
                </button>
              </div>

              {assistantOut && (
                <label>
                  Assistant draft
                  <textarea value={assistantOut} onChange={(e) => setAssistantOut(e.target.value)} />
                </label>
              )}

              {judgeOut && (
                <div className="alert warn">
                  <strong>Judge {judgeOut.overall_score}/10</strong>
                  <div>{judgeOut.feedback}</div>
                  <div className="muted" style={{ marginTop: "0.4rem" }}>
                    {Object.entries(judgeOut.scores || {})
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(" · ")}
                  </div>
                </div>
              )}

              <h3>Tasks</h3>
              <div className="row">
                <input
                  placeholder="Add research task"
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                />
                <button className="btn" onClick={addTask}>
                  Add
                </button>
              </div>
              <ul className="muted">
                {tasks.map((t) => (
                  <li key={t.id}>
                    [{t.status}] {t.title}
                  </li>
                ))}
              </ul>

              <h3>Artifacts</h3>
              <input type="file" onChange={uploadArtifact} />
              <ul className="muted">
                {artifacts.map((a) => (
                  <li key={a.id}>
                    {a.original_name} ({a.size_bytes} bytes)
                  </li>
                ))}
              </ul>
            </div>

            <div className="panel stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <h2 style={{ margin: 0 }}>{activeSection?.title || "Paper"}</h2>
                <span className="badge">markdown</span>
              </div>
              <textarea
                style={{ minHeight: 560 }}
                value={activeSection?.content_md || ""}
                onChange={(e) => {
                  const val = e.target.value;
                  setSections((prev) =>
                    prev.map((s) => (s.id === sectionId ? { ...s, content_md: val } : s))
                  );
                }}
                onBlur={(e) => saveSectionContent(e.target.value)}
              />
              <p className="footer-note">
                Edits save on blur and count toward human contribution unless applied from the assistant.
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
