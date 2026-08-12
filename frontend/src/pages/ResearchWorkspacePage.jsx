import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../api/auth";
import TextDiffPanes from "../components/TextDiffPanes";

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
  /** Pending humanize rewrite: accept/reject before writing to the section */
  const [humanizeDraft, setHumanizeDraft] = useState(null);
  /** One-level undo after Accept humanize */
  const [humanizeUndo, setHumanizeUndo] = useState(null);
  const [saveState, setSaveState] = useState("saved"); // saved | saving | dirty | error
  const [saveToast, setSaveToast] = useState("");
  const [sectionVersions, setSectionVersions] = useState([]);
  const [checklistMd, setChecklistMd] = useState("");
  const [scholarQ, setScholarQ] = useState("");
  const [scholarHits, setScholarHits] = useState([]);
  const [scholarNote, setScholarNote] = useState("");
  const humanizeRef = useRef(null);
  const autosaveTimer = useRef(null);
  const saveToastTimer = useRef(null);

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

  // Drop a pending rewrite when the user switches sections
  useEffect(() => {
    setHumanizeDraft(null);
    setHumanizeUndo(null);
    setSaveState("saved");
    setSaveToast("");
  }, [sectionId]);

  useEffect(() => {
    if (humanizeDraft && humanizeRef.current) {
      humanizeRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [humanizeDraft]);

  function flashSaveToast(text) {
    setSaveToast(text);
    if (saveToastTimer.current) clearTimeout(saveToastTimer.current);
    saveToastTimer.current = setTimeout(() => setSaveToast(""), 2500);
  }

  async function loadSectionVersions() {
    if (!project || !sectionId) {
      setSectionVersions([]);
      return;
    }
    try {
      const res = await api(
        `/api/projects/${project.id}/sections/${sectionId}/versions?limit=12`
      );
      setSectionVersions(res.versions || []);
    } catch {
      setSectionVersions([]);
    }
  }

  useEffect(() => {
    loadSectionVersions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id, sectionId]);

  // Debounced autosave when dirty (3s after last keystroke)
  useEffect(() => {
    if (isReviewer || !activeSection || saveState !== "dirty") return;
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
    autosaveTimer.current = setTimeout(() => {
      saveSectionContent(activeSection.content_md || "", { reason: "autosave" }).catch(() => {});
    }, 3000);
    return () => {
      if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSection?.content_md, saveState, sectionId]);

  async function saveSectionContent(content_md, opts = {}) {
    if (!project || !activeSection) return;
    setSaveState("saving");
    try {
      const updated = await api(`/api/projects/${project.id}/sections/${activeSection.id}`, {
        method: "PATCH",
        body: JSON.stringify({ content_md, prompt }),
      });
      setSections((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      await loadProject();
      setSaveState("saved");
      flashSaveToast(opts.reason === "autosave" ? "Autosaved" : "Saved");
      await loadSectionVersions();
    } catch (e) {
      setSaveState("error");
      flashSaveToast("Save failed");
      throw e;
    }
  }

  async function appendToSection(snippet, note) {
    if (!activeSection || !snippet) return;
    const next = `${activeSection.content_md || ""}${snippet}`;
    setSections((prev) =>
      prev.map((s) => (s.id === sectionId ? { ...s, content_md: next } : s))
    );
    await saveSectionContent(next);
    setMessage(note || "Inserted into paper.");
    setRightTab("paper");
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

  async function humanizeSection(mode = "local") {
    if (!activeSection) return;
    const original = activeSection.content_md || "";
    if (!original.trim()) {
      setError("Section is empty. Write or apply research content first.");
      return;
    }
    const rewriteMode = mode === "live" ? "live" : "local";
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const before = await api("/api/research/ai-check", {
        method: "POST",
        body: JSON.stringify({
          text: original,
          source_label: `section-before:${activeSection.id}`,
          mode: "quick",
        }),
      });
      const result = await api("/api/research/rewrite", {
        method: "POST",
        body: JSON.stringify({ text: original, strength: "high", mode: rewriteMode }),
      });
      const proposed = result.content || "";
      if (!proposed.trim()) {
        throw new Error("Rewrite returned empty text.");
      }
      const after = await api("/api/research/ai-check", {
        method: "POST",
        body: JSON.stringify({
          text: proposed,
          source_label: `section-after-humanize-${rewriteMode}:${activeSection.id}`,
          mode: "quick",
        }),
      });
      setHumanizeDraft({
        sectionId: activeSection.id,
        sectionTitle: activeSection.title,
        original,
        proposed,
        before,
        after,
        provider: result.provider || null,
        model: result.model || null,
        used_live: !!result.used_live,
        mode: result.mode || rewriteMode,
        note: result.note || "",
      });
      const delta = Number((before.ai_pct - after.ai_pct).toFixed(1));
      const via = result.used_live
        ? `via live ${result.provider || "model"}${result.model ? ` (${result.model})` : ""}`
        : "via local rules";
      setMessage(
        `Humanize draft ready ${via}. AI likelihood ${before.ai_pct}% → ${after.ai_pct}%` +
          (delta > 0 ? ` (↓ ${delta} pts).` : delta < 0 ? ` (↑ ${Math.abs(delta)} pts).` : ".") +
          " Review red/green diff, then Accept or Reject."
      );
      setRightTab("paper");
    } catch (e) {
      setError(e.message || "Humanize failed.");
    } finally {
      setBusy(false);
    }
  }

  async function acceptHumanize() {
    if (!humanizeDraft || !activeSection) return;
    if (humanizeDraft.sectionId !== activeSection.id) {
      setError("Section changed. Re-run Humanize on this section.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const previous = humanizeDraft.original || "";
      setHumanizeUndo({
        sectionId: humanizeDraft.sectionId,
        content: previous,
        at: new Date().toISOString(),
      });
      await saveSectionContent(humanizeDraft.proposed, { reason: "humanize-accept" });
      setHumanizeDraft(null);
      setMessage(
        "Humanized text accepted into the section. Use Undo humanize if you need the prior body back."
      );
      await loadProjectDetails();
      await loadSectionVersions();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function rejectHumanize() {
    setHumanizeDraft(null);
    setMessage("Humanize draft discarded. Section unchanged.");
  }

  async function undoHumanizeAccept() {
    if (!humanizeUndo || !activeSection) return;
    if (humanizeUndo.sectionId !== activeSection.id) {
      setError("Undo is for a different section. Switch back or use Version history.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await saveSectionContent(humanizeUndo.content, { reason: "humanize-undo" });
      setHumanizeUndo(null);
      setMessage("Reverted to the pre-humanize section body.");
      await loadProjectDetails();
      await loadSectionVersions();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function restoreSectionVersion(versionId) {
    if (!project || !sectionId || !versionId) return;
    if (!window.confirm("Restore this version into the paper? Current body is snapshot first.")) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await api(
        `/api/projects/${project.id}/sections/${sectionId}/versions/${versionId}/restore`,
        { method: "POST" }
      );
      setSections((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      setSaveState("saved");
      flashSaveToast("Version restored");
      setMessage("Restored paper from version history.");
      setHumanizeUndo(null);
      await loadProject();
      await loadSectionVersions();
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
      setChecklistMd(res.checklist_md || "");
      const uncited = res.evidence?.uncited_count ?? 0;
      setMessage(
        `Evidence coverage ${res.evidence.coverage_pct}% · AI likelihood ${res.ai_check.ai_pct}%` +
          (uncited ? ` · ${uncited} uncited claim(s) — insert evidence notes below.` : "")
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function insertEvidenceNote(claim) {
    const snippet =
      claim?.insert_snippet ||
      `\n\n> **Evidence note**\n> Claim: ${claim?.text || "Claim"}\n> Source: [title](https://)\n> Confidence: low\n`;
    await appendToSection(snippet, "Evidence note inserted under the paper. Fill in the real source.");
  }

  async function insertEvidenceChecklist() {
    let md = checklistMd;
    if (!md) {
      const res = await api(
        `/api/workspace/evidence/checklist?topic=${encodeURIComponent(activeSection?.title || "")}`
      );
      md = res.markdown || "";
      setChecklistMd(md);
    }
    if (!md) return;
    await appendToSection(`\n\n${md}\n`, "Evidence checklist inserted into paper.");
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

  async function searchScholar(topicOverride) {
    const q = (topicOverride ?? scholarQ).trim();
    if (q.length < 2) {
      setError("Enter a topic of at least 2 characters for scholar search.");
      return;
    }
    setBusy(true);
    setError("");
    setScholarNote("");
    try {
      const res = await api(`/api/workspace/scholar/search?q=${encodeURIComponent(q)}&limit=12`);
      setScholarHits(res.results || []);
      setScholarQ(q);
      setScholarNote(
        res.message ||
          `Found ${res.total || 0} scholarly hit(s)` +
            (res.sources_tried?.length ? ` via ${res.sources_tried.join(", ")}` : "") +
            ". Ranked by topic fit + citations + recency."
      );
      if (res.source_errors?.length) {
        setMessage((res.note || "") + " " + res.source_errors.join(" · "));
      } else if (res.note) {
        setMessage(res.note);
      }
    } catch (e) {
      setError(e.message || "Scholar search failed.");
    } finally {
      setBusy(false);
    }
  }

  async function searchScholarForSection() {
    const topic = [activeSection?.title, prompt, project?.title].filter(Boolean).join(" ").trim();
    if (!topic) {
      setError("Open a section with a title or prompt first.");
      return;
    }
    setScholarQ(topic);
    await searchScholar(topic);
  }

  async function addScholarCitation(item) {
    if (!activeId || !item) return;
    setBusy(true);
    setError("");
    try {
      const row = await api("/api/workspace/scholar/add-citation", {
        method: "POST",
        body: JSON.stringify({
          project_id: activeId,
          style: citeForm.style || "apa",
          item,
        }),
      });
      await loadProjectDetails();
      setMessage(`Added citation: ${row.title || item.title}`);
    } catch (e) {
      setError(e.message || "Could not add citation.");
    } finally {
      setBusy(false);
    }
  }

  async function insertScholarIntoPaper(item) {
    if (!activeSection || !item) return;
    const authors = item.author || "Author";
    const year = item.year || "n.d.";
    const title = item.title || "Untitled";
    const url = item.url || (item.doi ? `https://doi.org/${item.doi}` : "");
    const line = url
      ? `${authors} (${year}). ${title}. ${url}`
      : `${authors} (${year}). ${title}.`;
    const snippet =
      `\n\n${line}\n` +
      (item.abstract ? `> ${item.abstract.slice(0, 280)}${item.abstract.length > 280 ? "…" : ""}\n` : "");
    await appendToSection(snippet, "Scholar source inserted into paper. Add citation to project library if you will reuse it.");
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
    setBusy(true);
    setError("");
    try {
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
      setMessage("Diagram generated. Insert into paper when ready.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function insertDiagramIntoPaper() {
    if (!diagram.trim()) {
      setError("Generate a diagram first.");
      return;
    }
    const block =
      `\n\n### Diagram\n\n` +
      "```mermaid\n" +
      diagram.trim() +
      "\n```\n";
    await appendToSection(block, "Diagram inserted into the active section as a Mermaid block.");
  }

  async function insertCitation(formatted) {
    if (!activeSection) return;
    await appendToSection(`\n\n${formatted}\n`, "Citation inserted into paper.");
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
            Panel research desk for OffSec · Exposure · VM.
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
      {saveToast && (
        <div className={`alert ${saveState === "error" ? "error" : "ok"}`} role="status">
          {saveToast}
        </div>
      )}
      {humanizeUndo && humanizeUndo.sectionId === sectionId && !isReviewer && (
        <div className="alert warn row" style={{ justifyContent: "space-between" }}>
          <span>
            Humanize was accepted. One-level undo available for this section
            {humanizeUndo.at ? ` (from ${new Date(humanizeUndo.at).toLocaleTimeString()})` : ""}.
          </span>
          <button className="btn" type="button" onClick={undoHumanizeAccept} disabled={busy}>
            Undo humanize
          </button>
        </div>
      )}
      {gate && (
        <div className={`alert ${gate.ready ? "ok" : "warn"}`}>
          <strong>Publish gate: {gate.ready ? "ready" : "blocked"}</strong>
          {gate.message && <div className="muted" style={{ marginTop: "0.25rem" }}>{gate.message}</div>}
          {!gate.ready && (
            <ul style={{ margin: "0.4rem 0 0" }}>
              {(gate.actions || []).length
                ? gate.actions.map((a) => (
                    <li key={a.blocker}>
                      <strong>{a.blocker}</strong>
                      <div className="muted">{a.action}</div>
                      {a.desk_hint === "humanize" && !isReviewer && (
                        <div className="row" style={{ marginTop: "0.3rem" }}>
                          <button className="btn" type="button" onClick={() => humanizeSection("local")} disabled={busy}>
                            Local humanize
                          </button>
                          <button className="btn" type="button" onClick={() => humanizeSection("live")} disabled={busy}>
                            Live humanize
                          </button>
                        </div>
                      )}
                      {a.desk_hint === "evidence" && !isReviewer && (
                        <button className="btn" type="button" style={{ marginTop: "0.3rem" }} onClick={runEvidence} disabled={busy}>
                          Run Evidence check
                        </button>
                      )}
                    </li>
                  ))
                : (gate.blockers || []).map((b) => <li key={b}>{b}</li>)}
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
                    <button
                      className="btn"
                      onClick={() => humanizeSection("local")}
                      disabled={busy || !activeSection}
                      title="Free local style cleanup, then review before save"
                    >
                      Local humanize
                    </button>
                    <button
                      className="btn"
                      onClick={() => humanizeSection("live")}
                      disabled={busy || !activeSection}
                      title="Live research model rewrite, then review before save"
                    >
                      Live humanize
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

              {humanizeDraft && !isReviewer && (
                <div className="panel stack" ref={humanizeRef} style={{ borderColor: "rgba(46, 204, 113, 0.35)" }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <h3 style={{ margin: 0 }}>
                      Humanize review · {humanizeDraft.sectionTitle || "section"}
                    </h3>
                    <div className="row">
                      <button className="btn" type="button" onClick={rejectHumanize} disabled={busy}>
                        Reject
                      </button>
                      <button className="btn primary" type="button" onClick={acceptHumanize} disabled={busy}>
                        Accept into section
                      </button>
                    </div>
                  </div>
                  <p className="muted" style={{ margin: 0 }}>
                    {humanizeDraft.used_live
                      ? `Rewrite mode: live · ${humanizeDraft.provider || "provider"}${
                          humanizeDraft.model ? ` · ${humanizeDraft.model}` : ""
                        }.`
                      : "Rewrite mode: local rules only."}{" "}
                    {humanizeDraft.note ? `${humanizeDraft.note} ` : ""}
                    Not saved until you Accept. Red = removed, green = added.
                  </p>
                  <div className="grid-3">
                    <div className="metric">
                      <span className="muted">Before AI %</span>
                      <strong
                        className={
                          humanizeDraft.before.ai_pct >= 10 ? "badge bad" : "badge good"
                        }
                      >
                        {humanizeDraft.before.ai_pct}%
                      </strong>
                    </div>
                    <div className="metric">
                      <span className="muted">After AI %</span>
                      <strong
                        className={
                          humanizeDraft.after.ai_pct >= 10 ? "badge bad" : "badge good"
                        }
                      >
                        {humanizeDraft.after.ai_pct}%
                      </strong>
                    </div>
                    <div className="metric">
                      <span className="muted">Delta</span>
                      <strong style={{ fontSize: "1rem" }}>
                        {(() => {
                          const d = Number(
                            (humanizeDraft.before.ai_pct - humanizeDraft.after.ai_pct).toFixed(1)
                          );
                          if (d > 0) return `↓ ${d} pts`;
                          if (d < 0) return `↑ ${Math.abs(d)} pts`;
                          return "No change";
                        })()}
                      </strong>
                    </div>
                  </div>
                  <TextDiffPanes
                    original={humanizeDraft.original}
                    proposed={humanizeDraft.proposed}
                    originalLabel="Original (in section now)"
                    proposedLabel="Proposed rewrite"
                    editableProposed
                    onProposedChange={(next) =>
                      setHumanizeDraft((d) => (d ? { ...d, proposed: next } : d))
                    }
                  />
                </div>
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
                <div className="alert warn stack">
                  <strong>
                    Judge {judgeOut.overall_score}/10
                    {judgeOut.used_live ? " · multi-model panel" : " · local only"}
                  </strong>
                  {!!(judgeOut.models_used || []).length && (
                    <div className="row">
                      {(judgeOut.models_used || []).map((m) => (
                        <span className="badge" key={m}>
                          {m}
                        </span>
                      ))}
                    </div>
                  )}
                  {judgeOut.publish_ready_hint === true && (
                    <div className="badge good">Live judges lean publish-ready</div>
                  )}
                  {judgeOut.publish_ready_hint === false && (
                    <div className="badge bad">Live judges say not publish-ready</div>
                  )}
                  {(judgeOut.panel || []).length > 0 && (
                    <div className="stack">
                      <strong>Panel roles</strong>
                      {(judgeOut.panel || []).map((p, idx) => (
                        <div key={`${p.provider}-${idx}`} className="panel" style={{ padding: "0.6rem" }}>
                          <div className="row" style={{ justifyContent: "space-between" }}>
                            <span>
                              <strong>{p.provider}</strong> · {p.model || "default"}
                            </span>
                            <span className={p.ok ? "badge good" : "badge bad"}>
                              {p.ok ? "ok" : "failed"}
                            </span>
                          </div>
                          <pre
                            style={{
                              whiteSpace: "pre-wrap",
                              margin: "0.4rem 0 0",
                              fontFamily: "var(--mono)",
                              fontSize: "0.8rem",
                            }}
                          >
                            {p.feedback}
                          </pre>
                        </div>
                      ))}
                    </div>
                  )}
                  <div style={{ whiteSpace: "pre-wrap" }}>{judgeOut.feedback}</div>
                </div>
              )}
              {evidence && (
                <div className="alert ok stack">
                  <strong>
                    Evidence {evidence.coverage_pct}% · claims {evidence.claim_count} · uncited{" "}
                    {evidence.uncited_count}
                  </strong>
                  <ul>
                    {(evidence.recommendations || []).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                  <div className="row">
                    <button className="btn" type="button" onClick={insertEvidenceChecklist} disabled={busy || isReviewer}>
                      Insert checklist into paper
                    </button>
                  </div>
                  {(evidence.uncited_claims || evidence.claims || [])
                    .filter((c) => !c.has_citation)
                    .slice(0, 8)
                    .map((c) => (
                      <div key={`${c.line}-${c.text.slice(0, 24)}`} className="panel stack" style={{ padding: "0.55rem" }}>
                        <div className="muted" style={{ fontSize: "0.8rem" }}>
                          Line {c.line} · uncited
                        </div>
                        <div style={{ fontSize: "0.88rem" }}>{c.text}</div>
                        {!isReviewer && (
                          <button
                            className="btn"
                            type="button"
                            onClick={() => insertEvidenceNote(c)}
                            disabled={busy}
                          >
                            Insert evidence note
                          </button>
                        )}
                      </div>
                    ))}
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
                <button className="btn" type="button" onClick={() => makeDiagram("attack")} disabled={busy}>
                  Attack path
                </button>
                <button className="btn" type="button" onClick={() => makeDiagram("stride")} disabled={busy}>
                  STRIDE map
                </button>
                <button className="btn" type="button" onClick={() => makeDiagram("controls")} disabled={busy}>
                  Control gaps
                </button>
                <button
                  className="btn primary"
                  type="button"
                  onClick={insertDiagramIntoPaper}
                  disabled={busy || !diagram || isReviewer}
                  title="Insert the generated Mermaid diagram into the active section"
                >
                  Insert diagram into paper
                </button>
              </div>

              <h3>Citations</h3>
              <div className="panel stack" style={{ padding: "0.75rem" }}>
                <strong>Scholar search</strong>
                <p className="muted" style={{ margin: 0 }}>
                  Find papers for this topic (Crossref + Semantic Scholar + OpenAlex). Ranked by topic fit,
                  citations, and recency. Not Google Scholar (no official API).
                </p>
                <div className="row">
                  <input
                    style={{ flex: 1 }}
                    value={scholarQ}
                    onChange={(e) => setScholarQ(e.target.value)}
                    placeholder="e.g. exposure management prioritization exploitability"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        searchScholar();
                      }
                    }}
                  />
                  <button className="btn" type="button" onClick={() => searchScholar()} disabled={busy}>
                    Search
                  </button>
                  <button
                    className="btn primary"
                    type="button"
                    onClick={searchScholarForSection}
                    disabled={busy}
                    title="Use section title + prompt + project title"
                  >
                    Best for this section
                  </button>
                </div>
                {scholarNote && <p className="muted" style={{ margin: 0 }}>{scholarNote}</p>}
                {scholarHits.map((hit, idx) => (
                  <div key={`${hit.doi || hit.title}-${idx}`} className="panel stack" style={{ padding: "0.55rem" }}>
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <strong style={{ fontSize: "0.92rem" }}>{hit.title}</strong>
                      <span className="badge">score {hit.score}</span>
                    </div>
                    <div className="muted" style={{ fontSize: "0.82rem" }}>
                      {hit.author || "Author"} · {hit.year || "n.d."}
                      {hit.venue ? ` · ${hit.venue}` : ""}
                      {hit.cited_by_count != null ? ` · cited≈${hit.cited_by_count}` : ""}
                      {hit.sources?.length ? ` · ${hit.sources.join("+")}` : ""}
                    </div>
                    {hit.abstract && (
                      <div style={{ fontSize: "0.85rem" }}>
                        {hit.abstract.slice(0, 220)}
                        {hit.abstract.length > 220 ? "…" : ""}
                      </div>
                    )}
                    <div className="row">
                      {hit.url && (
                        <a className="btn ghost" href={hit.url} target="_blank" rel="noreferrer">
                          Open
                        </a>
                      )}
                      <button
                        className="btn"
                        type="button"
                        disabled={busy || isReviewer}
                        onClick={() => addScholarCitation(hit)}
                      >
                        Add citation
                      </button>
                      <button
                        className="btn primary"
                        type="button"
                        disabled={busy || isReviewer || !activeSection}
                        onClick={() => insertScholarIntoPaper(hit)}
                      >
                        Insert into paper
                      </button>
                    </div>
                  </div>
                ))}
              </div>
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
                <div className="row">
                  <span className="badge">{activeSection?.title || "markdown"}</span>
                  <span
                    className={
                      saveState === "saved"
                        ? "badge good"
                        : saveState === "saving"
                          ? "badge"
                          : "badge bad"
                    }
                    title={
                      saveState === "dirty"
                        ? "Unsaved — autosaves in a few seconds, or blur the editor"
                        : saveState === "saving"
                          ? "Saving to server"
                          : saveState === "error"
                            ? "Last save failed"
                            : "All changes saved"
                    }
                  >
                    {saveState === "saved"
                      ? "Saved"
                      : saveState === "saving"
                        ? "Saving…"
                        : saveState === "error"
                          ? "Save failed"
                          : "Unsaved (autosave soon)"}
                  </span>
                  {!isReviewer && (
                    <button
                      className="btn ghost"
                      type="button"
                      disabled={busy || saveState === "saving" || !activeSection}
                      onClick={() =>
                        saveSectionContent(activeSection?.content_md || "", { reason: "manual" })
                      }
                    >
                      Save now
                    </button>
                  )}
                </div>
              </div>
              {rightTab === "paper" ? (
                <>
                  <textarea
                    style={{ minHeight: 560 }}
                    value={activeSection?.content_md || ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      setSaveState("dirty");
                      setSections((prev) =>
                        prev.map((s) => (s.id === sectionId ? { ...s, content_md: val } : s))
                      );
                    }}
                    onBlur={(e) => {
                      if (saveState === "dirty" || saveState === "error") {
                        saveSectionContent(e.target.value, { reason: "blur" }).catch(() => {});
                      }
                    }}
                    readOnly={isReviewer}
                  />
                  <p className="footer-note">
                    Autosaves ~3s after you pause typing; also saves on blur and Save now. Humanize
                    requires Accept (then Undo humanize once if needed).
                  </p>
                  {!isReviewer && (
                    <div className="panel stack" style={{ padding: "0.65rem" }}>
                      <div className="row" style={{ justifyContent: "space-between" }}>
                        <strong>Version snippets</strong>
                        <button
                          className="btn ghost"
                          type="button"
                          onClick={loadSectionVersions}
                          disabled={busy}
                        >
                          Refresh
                        </button>
                      </div>
                      <p className="muted" style={{ margin: 0, fontSize: "0.82rem" }}>
                        Light history of prior bodies (before save / restore). Not full VCS.
                      </p>
                      {!sectionVersions.length && (
                        <p className="muted" style={{ margin: 0 }}>
                          No versions yet. Edit and save to create snippets.
                        </p>
                      )}
                      {sectionVersions.map((v) => (
                        <div
                          key={v.id}
                          className="row"
                          style={{ justifyContent: "space-between", alignItems: "flex-start" }}
                        >
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div>
                              <span className="badge">{v.label}</span>{" "}
                              <span className="muted" style={{ fontSize: "0.8rem" }}>
                                {v.char_count} chars
                                {v.created_at
                                  ? ` · ${new Date(v.created_at).toLocaleString()}`
                                  : ""}
                              </span>
                            </div>
                            <div
                              className="muted"
                              style={{
                                fontSize: "0.82rem",
                                whiteSpace: "nowrap",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                              }}
                            >
                              {v.snippet}
                            </div>
                          </div>
                          <button
                            className="btn"
                            type="button"
                            disabled={busy}
                            onClick={() => restoreSectionVersion(v.id)}
                          >
                            Restore
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="stack">
                  <div className="row">
                    <button
                      className="btn primary"
                      type="button"
                      onClick={insertDiagramIntoPaper}
                      disabled={busy || !diagram || isReviewer}
                    >
                      Insert diagram into paper
                    </button>
                  </div>
                  <pre
                    style={{
                      minHeight: 600,
                      whiteSpace: "pre-wrap",
                      fontFamily: "var(--mono)",
                      fontSize: "0.85rem",
                      margin: 0,
                    }}
                  >
                    {diagram || "Generate a diagram from the left tools."}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
