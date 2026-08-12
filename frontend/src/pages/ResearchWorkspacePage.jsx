import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../api/auth";

export default function ResearchWorkspacePage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const activeId = Number(projectId);

  const [project, setProject] = useState(null);
  const [sections, setSections] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [artifacts, setArtifacts] = useState([]);
  const [sectionId, setSectionId] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [assistantOut, setAssistantOut] = useState("");
  const [critique, setCritique] = useState("");
  const [redTeam, setRedTeam] = useState("");
  const [judgeOut, setJudgeOut] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState([]);
  const [frameworks, setFrameworks] = useState({ mitre: [], stride: [], saas_packs: [] });
  const [maps, setMaps] = useState([]);
  const [citations, setCitations] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [controls, setControls] = useState([]);
  const [evidence, setEvidence] = useState(null);
  const [gate, setGate] = useState(null);
  const [diagram, setDiagram] = useState("");
  const [citeForm, setCiteForm] = useState({ title: "", url: "", author: "", year: "", style: "apa" });
  const [reviewText, setReviewText] = useState("");
  const [mitrePick, setMitrePick] = useState("T1190");
  const [stridePick, setStridePick] = useState("spoofing");
  const [controlPack, setControlPack] = useState("exposure_vm_ops");
  const [controlName, setControlName] = useState("");
  const [vendor, setVendor] = useState("");
  const [rightTab, setRightTab] = useState("paper");

  const activeSection = useMemo(
    () => sections.find((s) => s.id === sectionId) || null,
    [sections, sectionId]
  );
  const isReviewer = user?.role === "reviewer";

  async function loadProject() {
    if (!activeId) return;
    const p = await api(`/api/projects/${activeId}`);
    setProject(p);
  }

  async function loadProjectDetails() {
    if (!activeId) return;
    const [secs, tks, arts, m, c, r, ctrl] = await Promise.all([
      api(`/api/projects/${activeId}/sections`),
      api(`/api/projects/${activeId}/tasks`),
      api(`/api/projects/${activeId}/artifacts`),
      api(`/api/workspace/projects/${activeId}/framework-maps`),
      api(`/api/workspace/projects/${activeId}/citations`),
      api(`/api/workspace/projects/${activeId}/peer-reviews`),
      api(`/api/workspace/projects/${activeId}/controls`),
    ]);
    setSections(secs);
    setTasks(tks);
    setArtifacts(arts);
    setMaps(m);
    setCitations(c);
    setReviews(r);
    setControls(ctrl);
    if (secs.length) {
      setSectionId((current) => {
        const still = secs.find((s) => s.id === current);
        return still ? still.id : secs[0].id;
      });
    } else {
      setSectionId(null);
    }
  }

  useEffect(() => {
    if (!activeId) {
      setError("Missing project id");
      return;
    }
    Promise.all([
      loadProject(),
      loadProjectDetails(),
      api("/api/workspace/providers").then((p) => setProviders(p.active || [])),
      api("/api/workspace/frameworks").then(setFrameworks),
    ]).catch((e) => setError(e.message));
  }, [activeId]);

  useEffect(() => {
    if (activeSection) setPrompt(activeSection.prompt || "");
  }, [sectionId]);

  async function saveSectionContent(content_md) {
    if (!project || !activeSection) return;
    const updated = await api(`/api/projects/${project.id}/sections/${activeSection.id}`, {
      method: "PATCH",
      body: JSON.stringify({ content_md, prompt }),
    });
    setSections((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    await loadProject();
  }

  async function runAssistant() {
    if (!prompt.trim()) return;
    setBusy(true);
    setError("");
    try {
      if (activeSection) {
        await api(`/api/projects/${project.id}/sections/${activeSection.id}`, {
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
          multi_agent: true,
          evidence_mode: project?.evidence_mode !== false,
        }),
      });
      setAssistantOut(result.content);
      setCritique(result.critique || "");
      setRedTeam(result.red_team || "");
      setMessage(
        `${result.notes || "Assistant ready."}${
          result.used_live ? " (live providers)" : " (local scaffold)"
        }`
      );
      await loadProject();
      await loadProjectDetails();
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
      setMessage("Assistant output applied (counts as agent contribution).");
      await loadProject();
      await loadProjectDetails();
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
      setMessage(
        result.used_live
          ? `Humanized with ${result.provider}. Edit further before publish.`
          : "Humanized locally. Edit further before publish."
      );
      await loadProjectDetails();
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

  async function runEvidence() {
    const text = activeSection?.content_md || "";
    setBusy(true);
    try {
      const res = await api("/api/workspace/evidence/analyze", {
        method: "POST",
        body: JSON.stringify({ text, project_id: activeId }),
      });
      setEvidence(res.evidence);
      setGate(res.publish_gate);
      setMessage(`Evidence coverage ${res.evidence.coverage_pct}% · AI likelihood ${res.ai_check.ai_pct}%`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function refreshGate() {
    const res = await api(`/api/workspace/projects/${activeId}/publish-gate`);
    setGate(res.publish_gate);
    setEvidence(res.evidence);
    setProject((p) => (p ? { ...p, publish_ready: res.publish_ready } : p));
  }

  async function exportDocx(force = false) {
    if (!project) return;
    setBusy(true);
    setError("");
    try {
      const combined = sections.map((s) => s.content_md).join("\n\n---\n\n");
      const res = await api("/api/research/export/docx", {
        method: "POST",
        body: JSON.stringify({
          title: project.title,
          content_md: combined,
          project_id: activeId,
          force,
        }),
      });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${project.title.replace(/\s+/g, "_")}.docx`;
      a.click();
      URL.revokeObjectURL(url);
      setMessage(force ? "Exported with force override." : "Exported. Publish gate passed.");
    } catch (e) {
      setError(typeof e.message === "string" ? e.message : JSON.stringify(e.message));
    } finally {
      setBusy(false);
    }
  }

  async function addTask() {
    if (!taskTitle.trim() || !activeId) return;
    await api(`/api/projects/${activeId}/tasks`, {
      method: "POST",
      body: JSON.stringify({ title: taskTitle.trim() }),
    });
    setTaskTitle("");
    await loadProjectDetails();
    await loadProject();
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
    await loadProjectDetails();
    setMessage(`Uploaded ${file.name}`);
  }

  async function addMitre() {
    const tech = (frameworks.mitre || []).find((t) => t.id === mitrePick) || {
      id: mitrePick,
      name: mitrePick,
    };
    await api("/api/workspace/framework-maps", {
      method: "POST",
      body: JSON.stringify({
        project_id: activeId,
        framework: "mitre",
        ref_id: tech.id,
        name: tech.name,
        notes: activeSection?.title || "",
        severity: "medium",
      }),
    });
    await loadProjectDetails();
  }

  async function addStride() {
    const cat = (frameworks.stride || []).find((s) => s.id === stridePick) || {
      id: stridePick,
      name: stridePick,
    };
    await api("/api/workspace/framework-maps", {
      method: "POST",
      body: JSON.stringify({
        project_id: activeId,
        framework: "stride",
        ref_id: cat.id,
        name: cat.name,
        notes: activeSection?.title || "",
        severity: "medium",
      }),
    });
    await loadProjectDetails();
  }

  async function addCitation(e) {
    e.preventDefault();
    await api("/api/workspace/citations", {
      method: "POST",
      body: JSON.stringify({ project_id: activeId, ...citeForm }),
    });
    setCiteForm({ title: "", url: "", author: "", year: "", style: "apa" });
    await loadProjectDetails();
  }

  async function addReview(e) {
    e.preventDefault();
    if (!reviewText.trim()) return;
    await api("/api/workspace/peer-reviews", {
      method: "POST",
      body: JSON.stringify({
        project_id: activeId,
        section_id: sectionId,
        comments: reviewText,
        overall_score: 7,
        status: "open",
      }),
    });
    setReviewText("");
    await loadProjectDetails();
  }

  async function addControl(e) {
    e.preventDefault();
    if (!controlName.trim()) return;
    await api("/api/workspace/controls", {
      method: "POST",
      body: JSON.stringify({
        project_id: activeId,
        pack_id: controlPack,
        control_name: controlName,
        vendor,
        status: "unknown",
        residual_risk: "medium",
      }),
    });
    setControlName("");
    await loadProjectDetails();
  }

  async function makeDiagram(kind) {
    const res = await api("/api/workspace/diagrams", {
      method: "POST",
      body: JSON.stringify({
        kind,
        title: project?.title || "Attack path",
        project_id: activeId,
        section_id: sectionId,
        text: activeSection?.content_md || "",
      }),
    });
    setDiagram(res.mermaid || "");
    setRightTab("diagram");
  }

  async function insertCitation(formatted) {
    if (!activeSection) return;
    const next = `${activeSection.content_md}\n\n${formatted}\n`;
    await saveSectionContent(next);
    setMessage("Citation inserted into paper.");
  }

  if (!project && !error) {
    return <div className="muted">Loading research workspace…</div>;
  }

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <button className="btn ghost" type="button" onClick={() => navigate("/app")}>
            ← Back to dashboard
          </button>
          <h1 style={{ margin: "0.5rem 0 0" }}>{project?.title || "Research desk"}</h1>
          <p className="muted" style={{ margin: "0.25rem 0 0" }}>
            Panel research desk for OffSec · Exposure · VM. Keep final agent share under 10%.
          </p>
        </div>
        <div className="row">
          <span className="badge">{providers.length} live providers</span>
          <button className="btn" type="button" onClick={refreshGate} disabled={busy}>
            Refresh publish gate
          </button>
          <button className="btn primary" type="button" onClick={() => exportDocx(false)} disabled={busy}>
            Export Word
          </button>
          {user?.role === "admin" && (
            <button className="btn ghost" type="button" onClick={() => exportDocx(true)} disabled={busy}>
              Force export
            </button>
          )}
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}
      {gate && (
        <div className={`alert ${gate.ready ? "ok" : "warn"}`}>
          <strong>Publish gate: {gate.ready ? "ready" : "blocked"}</strong>
          {!gate.ready && (
            <ul style={{ margin: "0.4rem 0 0" }}>
              {(gate.blockers || []).map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {project && (
        <>
          <div className="grid-3">
            <div className="metric">
              <span className="muted">Progress</span>
              <strong>{project.progress_pct ?? 0}%</strong>
              <div className="progress-track" style={{ marginTop: "0.55rem" }}>
                <div
                  className="progress-fill"
                  style={{ width: `${Math.min(100, Math.max(0, project.progress_pct || 0))}%` }}
                />
              </div>
            </div>
            <div className="metric">
              <span className="muted">Agent contribution</span>
              <strong className={project.agent_contribution_pct >= 10 ? "badge bad" : ""}>
                {project.agent_contribution_pct}%
              </strong>
            </div>
            <div className="metric">
              <span className="muted">Human contribution</span>
              <strong>{project.human_contribution_pct}%</strong>
            </div>
            <div className="metric">
              <span className="muted">Template</span>
              <strong style={{ fontSize: "1rem" }}>{project.template_key || "blank"}</strong>
            </div>
            <div className="metric">
              <span className="muted">Evidence mode</span>
              <strong style={{ fontSize: "1rem" }}>{project.evidence_mode ? "on" : "off"}</strong>
            </div>
            <div className="metric">
              <span className="muted">Max agent target</span>
              <strong>{project.max_agent_pct ?? 10}%</strong>
              <div className="muted" style={{ fontSize: "0.75rem", marginTop: "0.25rem" }}>
                Change global default in Settings
              </div>
            </div>
          </div>

          <div className="grid-2">
            <div className="panel stack">
              <h2>Sections (panel structure)</h2>
              <div className="section-list" style={{ maxHeight: 360 }}>
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

              {!isReviewer && (
                <>
                  <label>
                    Research prompt for this section
                    <textarea
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      placeholder="What should the multi-agent panel explore here?"
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
                    <button className="btn" onClick={runEvidence} disabled={busy}>
                      Evidence check
                    </button>
                  </div>
                </>
              )}

              {assistantOut && !isReviewer && (
                <label>
                  Assistant draft
                  <textarea value={assistantOut} onChange={(e) => setAssistantOut(e.target.value)} />
                </label>
              )}
              {critique && (
                <div className="alert warn">
                  <strong>Critic</strong>
                  <pre style={{ whiteSpace: "pre-wrap", margin: "0.4rem 0 0", fontFamily: "var(--mono)", fontSize: "0.82rem" }}>
                    {critique}
                  </pre>
                </div>
              )}
              {redTeam && (
                <div className="alert warn">
                  <strong>Red team</strong>
                  <pre style={{ whiteSpace: "pre-wrap", margin: "0.4rem 0 0", fontFamily: "var(--mono)", fontSize: "0.82rem" }}>
                    {redTeam}
                  </pre>
                </div>
              )}
              {judgeOut && (
                <div className="alert warn">
                  <strong>Judge {judgeOut.overall_score}/10</strong>
                  <div>{judgeOut.feedback}</div>
                </div>
              )}
              {evidence && (
                <div className="alert ok">
                  <strong>
                    Evidence {evidence.coverage_pct}% · claims {evidence.claim_count} · uncited{" "}
                    {evidence.uncited_count}
                  </strong>
                  <ul>
                    {(evidence.recommendations || []).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}

              <h3>MITRE / STRIDE</h3>
              <div className="row">
                <select value={mitrePick} onChange={(e) => setMitrePick(e.target.value)}>
                  {(frameworks.mitre || []).map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.id} {t.name}
                    </option>
                  ))}
                </select>
                <button className="btn" type="button" onClick={addMitre}>
                  Add ATT&CK
                </button>
              </div>
              <div className="row">
                <select value={stridePick} onChange={(e) => setStridePick(e.target.value)}>
                  {(frameworks.stride || []).map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
                <button className="btn" type="button" onClick={addStride}>
                  Add STRIDE
                </button>
              </div>
              <ul className="muted">
                {maps.slice(0, 12).map((m) => (
                  <li key={m.id}>
                    [{m.framework}] {m.ref_id} {m.name}
                  </li>
                ))}
              </ul>

              <h3>Diagrams</h3>
              <div className="row">
                <button className="btn" type="button" onClick={() => makeDiagram("attack")}>
                  Attack path
                </button>
                <button className="btn" type="button" onClick={() => makeDiagram("stride")}>
                  STRIDE map
                </button>
                <button className="btn" type="button" onClick={() => makeDiagram("controls")}>
                  Control gaps
                </button>
              </div>

              <h3>Citations</h3>
              <form className="stack" onSubmit={addCitation}>
                <div className="grid-3">
                  <label>
                    Title
                    <input
                      value={citeForm.title}
                      onChange={(e) => setCiteForm({ ...citeForm, title: e.target.value })}
                      required
                    />
                  </label>
                  <label>
                    URL
                    <input
                      value={citeForm.url}
                      onChange={(e) => setCiteForm({ ...citeForm, url: e.target.value })}
                    />
                  </label>
                  <label>
                    Style
                    <select
                      value={citeForm.style}
                      onChange={(e) => setCiteForm({ ...citeForm, style: e.target.value })}
                    >
                      <option value="apa">APA</option>
                      <option value="mla">MLA</option>
                      <option value="chicago">Chicago</option>
                    </select>
                  </label>
                </div>
                <div className="row">
                  <input
                    placeholder="Author"
                    value={citeForm.author}
                    onChange={(e) => setCiteForm({ ...citeForm, author: e.target.value })}
                  />
                  <input
                    placeholder="Year"
                    value={citeForm.year}
                    onChange={(e) => setCiteForm({ ...citeForm, year: e.target.value })}
                  />
                  <button className="btn" type="submit">
                    Add citation
                  </button>
                </div>
              </form>
              <ul className="muted">
                {citations.map((c) => (
                  <li key={c.id}>
                    {c.formatted}{" "}
                    <button className="btn ghost" type="button" onClick={() => insertCitation(c.formatted)}>
                      Insert
                    </button>
                  </li>
                ))}
              </ul>

              <h3>SaaS / control review</h3>
              <form className="stack" onSubmit={addControl}>
                <div className="row">
                  <select value={controlPack} onChange={(e) => setControlPack(e.target.value)}>
                    {(frameworks.saas_packs || []).map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                  <input
                    placeholder="Control name"
                    value={controlName}
                    onChange={(e) => setControlName(e.target.value)}
                  />
                  <input placeholder="Vendor" value={vendor} onChange={(e) => setVendor(e.target.value)} />
                  <button className="btn" type="submit">
                    Add
                  </button>
                </div>
              </form>
              <ul className="muted">
                {controls.map((c) => (
                  <li key={c.id}>
                    [{c.status}] {c.control_name} · {c.vendor || "n/a"}
                  </li>
                ))}
              </ul>

              <h3>Peer review</h3>
              <form className="stack" onSubmit={addReview}>
                <textarea
                  value={reviewText}
                  onChange={(e) => setReviewText(e.target.value)}
                  placeholder="Peer review comments for this section or whole project"
                />
                <button className="btn" type="submit">
                  Submit review
                </button>
              </form>
              <ul className="muted">
                {reviews.map((r) => (
                  <li key={r.id}>
                    [{r.status}] {r.reviewer}: {r.comments}
                  </li>
                ))}
              </ul>

              {!isReviewer && (
                <>
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
                </>
              )}
            </div>

            <div className="panel stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div className="row">
                  <button
                    className={`tab ${rightTab === "paper" ? "active" : ""}`}
                    type="button"
                    onClick={() => setRightTab("paper")}
                  >
                    Paper
                  </button>
                  <button
                    className={`tab ${rightTab === "diagram" ? "active" : ""}`}
                    type="button"
                    onClick={() => setRightTab("diagram")}
                  >
                    Diagram
                  </button>
                </div>
                <span className="badge">{activeSection?.title || "markdown"}</span>
              </div>
              {rightTab === "paper" ? (
                <>
                  <textarea
                    style={{ minHeight: 640 }}
                    value={activeSection?.content_md || ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      setSections((prev) =>
                        prev.map((s) => (s.id === sectionId ? { ...s, content_md: val } : s))
                      );
                    }}
                    onBlur={(e) => saveSectionContent(e.target.value)}
                    readOnly={isReviewer}
                  />
                  <p className="footer-note">
                    Edits save on blur and count as human contribution unless applied from the assistant.
                    Use Humanize + evidence check before Export Word.
                  </p>
                </>
              ) : (
                <pre
                  style={{
                    minHeight: 640,
                    whiteSpace: "pre-wrap",
                    fontFamily: "var(--mono)",
                    fontSize: "0.85rem",
                    margin: 0,
                  }}
                >
                  {diagram || "Generate a diagram from the left tools."}
                </pre>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
