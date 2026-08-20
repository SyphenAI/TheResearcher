import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, getToken } from "../api/client";
import { useAuth } from "../api/auth";
import TextDiffPanes from "../components/TextDiffPanes";
import { formatLocalDateTime } from "../utils/datetime";
import { appendScholarDateParams, scholarDatePreset } from "../utils/scholarDates";

/** Compact help control — hover/focus for tooltip, click toggles short panel. */
function HelpIcon({ label = "Help", mark = "?", wide = false, children }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="help-icon-wrap">
      <button
        type="button"
        className={`help-icon${mark !== "?" ? " help-pill" : ""}`}
        aria-label={label}
        title={typeof children === "string" ? children : label}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        {mark}
      </button>
      {open && (
        <span className={`help-pop${wide ? " help-pop-wide" : ""}`} role="note">
          {children}
          <button type="button" className="btn ghost" style={{ marginTop: "0.35rem" }} onClick={() => setOpen(false)}>
            Close
          </button>
        </span>
      )}
    </span>
  );
}

const MD_SNIPPETS = [
  {
    label: "# Title",
    hint: "Main title / H1",
    kind: "heading",
    prefix: "# ",
    placeholder: "Title",
  },
  {
    label: "## Section",
    hint: "Section heading / H2",
    kind: "heading",
    prefix: "## ",
    placeholder: "Section",
  },
  {
    label: "### Subsection",
    hint: "Subheading / H3",
    kind: "heading",
    prefix: "### ",
    placeholder: "Subsection",
  },
  { label: "**bold**", hint: "Bold", kind: "wrap", before: "**", after: "**", placeholder: "bold" },
  { label: "*italic*", hint: "Italic", kind: "wrap", before: "*", after: "*", placeholder: "italic" },
  {
    label: "***bold italic***",
    hint: "Bold + italic",
    kind: "wrap",
    before: "***",
    after: "***",
    placeholder: "bold italic",
  },
  { label: "`code`", hint: "Inline code / monospace", kind: "wrap", before: "`", after: "`", placeholder: "code" },
  { label: "- item", hint: "Bullet list", kind: "line", text: "- item", select: "item" },
  { label: "1. item", hint: "Numbered list", kind: "line", text: "1. item", select: "item" },
  {
    label: "[text](https://…)",
    hint: "Link",
    kind: "link",
    placeholder: "text",
    url: "https://example.com",
  },
  { label: "> quote", hint: "Block quote", kind: "line", text: "> quote", select: "quote" },
  { label: "---", hint: "Horizontal rule", kind: "block", text: "\n---\n", select: null },
];

function MarkdownFormatHelp({ onInsert, canInsert = true }) {
  return (
    <div className="stack" style={{ gap: "0.45rem" }}>
      <strong>Markdown for the paper editor</strong>
      <div className="muted" style={{ fontSize: "0.8rem" }}>
        {canInsert
          ? "Click a row to paste it into the paper at the cursor (selected text gets wrapped when it fits)."
          : "Type these in the paper window. Word download keeps headings, lists, and emphasis."}
      </div>
      <table className="md-help-table">
        <tbody>
          {MD_SNIPPETS.map((snip) => (
            <tr key={snip.label}>
              <td colSpan={2} style={{ padding: 0 }}>
                <button
                  type="button"
                  className="md-help-insert"
                  disabled={!canInsert || !onInsert}
                  title={canInsert ? `Insert ${snip.label} into paper` : snip.hint}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (onInsert) onInsert(snip);
                  }}
                >
                  <code>{snip.label}</code>
                  <span>{snip.hint}</span>
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ fontSize: "0.8rem" }}>
        <strong>Paragraphs:</strong> blank line between blocks.
        <br />
        <strong>Line break:</strong> end a line with two spaces, then Enter.
        <br />
        <strong>Color:</strong> plain markdown has no text color — use headings/bold for emphasis, or note
        color only in Word after download.
      </div>
      <pre className="md-help-sample">{`# Exposure management note

## Summary
Buyers need **fix proof**, not only discovery.

### Recommendations
1. Validate exploitability first
2. Retest after remediation

> Residual risk remains if ownership is unclear.

See [MITRE ATT&CK](https://attack.mitre.org/).`}</pre>
    </div>
  );
}

/** Desk tool tile — collapsed until needed so the left column stays readable. */
function CollapsibleTile({ title, summary = "", defaultOpen = false, children }) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <div className={`collapse-tile ${open ? "open" : "closed"}`}>
      <button
        type="button"
        className="collapse-tile-head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="collapse-tile-title">{title}</span>
        {!!summary && !open && <span className="collapse-tile-summary muted">{summary}</span>}
        <span className="collapse-tile-chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && <div className="collapse-tile-body stack">{children}</div>}
    </div>
  );
}

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
  /** Latest AI checker result for the active section body (refreshed on demand). */
  const [sectionAiCheck, setSectionAiCheck] = useState(null);
  const [paperAiCheck, setPaperAiCheck] = useState(null);
  const [aiCheckPanel, setAiCheckPanel] = useState(null); // last detailed result to show "why"
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [editingTaskId, setEditingTaskId] = useState(null);
  const [editingTaskTitle, setEditingTaskTitle] = useState("");
  /** Paper find / replace (manual flag + fix for misspellings). */
  const [findText, setFindText] = useState("");
  const [replaceText, setReplaceText] = useState("");
  const [findCaseSensitive, setFindCaseSensitive] = useState(false);
  const [findWholeWord, setFindWholeWord] = useState(true);
  const [findMatchCount, setFindMatchCount] = useState(null);
  const [spellIssues, setSpellIssues] = useState([]);
  const [spellMessage, setSpellMessage] = useState("");
  const paperEditorRef = useRef(null);
  const [busy, setBusy] = useState(false);
  /** What long-running desk action is in flight (shown in sticky banner). */
  const [busyLabel, setBusyLabel] = useState("");
  const [busyElapsedSec, setBusyElapsedSec] = useState(0);
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
  /** AI-check style fix preview (dashes/semicolons) before Accept */
  const [styleFixDraft, setStyleFixDraft] = useState(null);
  const styleFixRef = useRef(null);
  const [saveState, setSaveState] = useState("saved"); // saved | saving | dirty | error
  const [saveToast, setSaveToast] = useState("");
  const [sectionVersions, setSectionVersions] = useState([]);
  const [paperReleases, setPaperReleases] = useState([]);
  const [commitNote, setCommitNote] = useState("");
  const [diffLeftId, setDiffLeftId] = useState("");
  const [diffRightId, setDiffRightId] = useState("");
  const [newSectionTitle, setNewSectionTitle] = useState("");
  const [checklistMd, setChecklistMd] = useState("");
  const [scholarQ, setScholarQ] = useState("");
  const [scholarHits, setScholarHits] = useState([]);
  const [scholarNote, setScholarNote] = useState("");
  /** Optional publication year range for scholar search (empty = any year). */
  const [scholarYearFrom, setScholarYearFrom] = useState("");
  const [scholarYearTo, setScholarYearTo] = useState("");
  const [artifactUrl, setArtifactUrl] = useState("");
  const [artifactUrlTitle, setArtifactUrlTitle] = useState("");
  const [artifactUrlNote, setArtifactUrlNote] = useState("");
  const [liveModelOptions, setLiveModelOptions] = useState([
    { id: "auto", label: "Auto (token preferred / fallback)", provider: null, model: null },
  ]);
  const [liveModelId, setLiveModelId] = useState("auto");
  const humanizeRef = useRef(null);
  const assistantRef = useRef(null);
  const busyStartedAt = useRef(null);
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
    let nextSectionId = null;
    if (secs.length) {
      setSectionId((current) => {
        const still = secs.find((s) => s.id === current);
        nextSectionId = still ? still.id : secs[0].id;
        return nextSectionId;
      });
    } else {
      setSectionId(null);
    }
    // Restore last AI check results for this project / section after refresh
    await loadPersistedAiChecks(secs, nextSectionId);
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
      api("/api/workspace/live-models?purpose=research")
        .then((data) => {
          if (data.options?.length) setLiveModelOptions(data.options);
        })
        .catch(() => {}),
    ]).catch((e) => setError(e.message));
  }, [activeId]);

  // When switching sections, restore that section's last AI check (keep paper check)
  useEffect(() => {
    if (!activeId || !sectionId) return;
    let cancelled = false;
    (async () => {
      try {
        const secRows = await api(
          `/api/research/ai-check/history?limit=1&source_prefix=${encodeURIComponent(
            `desk-section:${sectionId}`
          )}`
        );
        if (cancelled) return;
        const secMeta = sections.find((s) => s.id === sectionId);
        if (secRows?.[0]) {
          const sectionCheck = hydrateAiCheck(
            secRows[0],
            "section",
            secMeta?.title || "Section"
          );
          setSectionAiCheck(sectionCheck);
          setAiCheckPanel((prev) =>
            prev?.scope === "paper" ? prev : sectionCheck
          );
        } else {
          setSectionAiCheck(null);
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, sectionId]);

  function liveModelPayload() {
    const sel = liveModelOptions.find((o) => o.id === liveModelId) || liveModelOptions[0];
    if (!sel || sel.id === "auto" || !sel.provider) return {};
    return { provider: sel.provider, model: sel.model || null };
  }

  useEffect(() => {
    if (activeSection) setPrompt(activeSection.prompt || "");
  }, [sectionId]);

  // Drop a pending rewrite when the user switches sections
  useEffect(() => {
    setHumanizeDraft(null);
    setHumanizeUndo(null);
    setJudgeOut(null);
    setSpellIssues([]);
    setSpellMessage("");
    setSaveState("saved");
    setSaveToast("");
  }, [sectionId]);

  function hydrateAiCheck(row, scope, scopeTitle) {
    if (!row) return null;
    return {
      ...row,
      scope,
      scope_title: scopeTitle,
      why: row.why || row.signals?.why || [],
      drivers: row.drivers || row.signals?.drivers || [],
      recommendations: row.recommendations || row.signals?.recommendations || [],
    };
  }

  async function loadPersistedAiChecks(secs, currentSectionId) {
    if (!activeId) return;
    try {
      const paperRows = await api(
        `/api/research/ai-check/history?limit=1&source_prefix=${encodeURIComponent(`desk-paper:${activeId}`)}`
      );
      if (paperRows?.[0]) {
        const paper = hydrateAiCheck(paperRows[0], "paper", project?.title || "Full paper");
        setPaperAiCheck(paper);
        setAiCheckPanel((prev) => prev || paper);
      }
      const sid = currentSectionId || sectionId || secs?.[0]?.id;
      if (sid) {
        const secRows = await api(
          `/api/research/ai-check/history?limit=1&source_prefix=${encodeURIComponent(`desk-section:${sid}`)}`
        );
        const secMeta = (secs || sections || []).find((s) => s.id === sid);
        if (secRows?.[0]) {
          const sectionCheck = hydrateAiCheck(
            secRows[0],
            "section",
            secMeta?.title || "Section"
          );
          setSectionAiCheck(sectionCheck);
          setAiCheckPanel((prev) => prev || sectionCheck);
        } else {
          setSectionAiCheck(null);
        }
      }
    } catch {
      // History restore is best-effort; desk still works without it.
    }
  }

  useEffect(() => {
    if (humanizeDraft && humanizeRef.current) {
      humanizeRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [humanizeDraft]);

  useEffect(() => {
    if (styleFixDraft && styleFixRef.current) {
      styleFixRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [styleFixDraft]);

  useEffect(() => {
    if (assistantOut && assistantRef.current) {
      assistantRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [assistantOut]);

  useEffect(() => {
    if (!busy) {
      busyStartedAt.current = null;
      setBusyElapsedSec(0);
      return;
    }
    busyStartedAt.current = Date.now();
    setBusyElapsedSec(0);
    const t = setInterval(() => {
      if (!busyStartedAt.current) return;
      setBusyElapsedSec(Math.floor((Date.now() - busyStartedAt.current) / 1000));
    }, 1000);
    return () => clearInterval(t);
  }, [busy]);

  function beginBusy(label) {
    setBusy(true);
    setBusyLabel(label || "Working…");
  }

  function endBusy() {
    setBusy(false);
    setBusyLabel("");
  }

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
        `/api/projects/${project.id}/sections/${sectionId}/versions?limit=20`
      );
      setSectionVersions(res.versions || []);
    } catch {
      setSectionVersions([]);
    }
  }

  async function loadPaperReleases() {
    if (!project?.id) {
      setPaperReleases([]);
      return;
    }
    try {
      const res = await api(`/api/projects/${project.id}/paper-releases?limit=40`);
      setPaperReleases(res.releases || []);
      if (res.working_version || res.primary_version !== undefined) {
        setProject((p) =>
          p
            ? {
                ...p,
                working_version: res.working_version || p.working_version,
                primary_version: res.primary_version,
                has_primary: !!res.has_primary,
              }
            : p
        );
      }
    } catch {
      setPaperReleases([]);
    }
  }

  useEffect(() => {
    loadSectionVersions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id, sectionId]);

  useEffect(() => {
    loadPaperReleases();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id]);

  async function commitPaper() {
    if (!project || isReviewer) return;
    beginBusy("Committing paper snapshot");
    setError("");
    try {
      // Flush current section first so commit includes latest editor text
      if (activeSection && (saveState === "dirty" || saveState === "error")) {
        await saveSectionContent(activeSection.content_md || "", { reason: "pre-commit" });
      }
      const res = await api(`/api/projects/${project.id}/paper/commit`, {
        method: "POST",
        body: JSON.stringify({ note: commitNote || "" }),
      });
      if (res.project) setProject(res.project);
      setCommitNote("");
      setMessage(res.message || `Committed. Working now v${res.working_version}`);
      await loadPaperReleases();
      await loadProject();
    } catch (e) {
      setError(e.message || "Commit failed.");
    } finally {
      endBusy();
    }
  }

  async function publishPrimaryPaper() {
    if (!project || isReviewer) return;
    const nextPrimary = project.has_primary
      ? `${(project.version_major || 0) + 1}.0.0`
      : "1.0.0";
    if (
      !window.confirm(
        `Publish primary ${nextPrimary} from the current paper?\n\n` +
          `This freezes a full snapshot as the official primary. ` +
          `Working version will move to the next workline (e.g. 1.1.1 after 1.0.0).`
      )
    ) {
      return;
    }
    beginBusy("Publishing primary version");
    setError("");
    try {
      if (activeSection && (saveState === "dirty" || saveState === "error")) {
        await saveSectionContent(activeSection.content_md || "", { reason: "pre-publish" });
      }
      const res = await api(`/api/projects/${project.id}/paper/publish-primary`, {
        method: "POST",
        body: JSON.stringify({ note: commitNote || "Primary published" }),
      });
      if (res.project) setProject(res.project);
      setCommitNote("");
      setMessage(res.message || `Primary published. Working v${res.working_version}`);
      await loadPaperReleases();
      await loadProject();
    } catch (e) {
      setError(e.message || "Publish primary failed.");
    } finally {
      endBusy();
    }
  }

  function openVersionDiffTab(leftId, rightId) {
    if (!project?.id) return;
    const L = leftId || diffLeftId;
    const R = rightId || diffRightId;
    if (!L || !R) {
      setError("Pick two commits/primary releases for the diff (Left and Right).");
      return;
    }
    if (String(L) === String(R)) {
      setError("Choose two different versions to compare.");
      return;
    }
    const url = `/app/research/${project.id}/diff?left=${encodeURIComponent(L)}&right=${encodeURIComponent(R)}`;
    window.open(url, "_blank", "noopener,noreferrer");
    setError("");
    setMessage("Opened version diff in a new tab.");
  }

  async function restorePaperRelease(releaseId, label) {
    if (!project || isReviewer) return;
    if (
      !window.confirm(
        `Restore paper from snapshot v${label || releaseId}?\n` +
          `Current bodies are auto-snapshotted first. Working version number stays the same.`
      )
    ) {
      return;
    }
    beginBusy("Restoring paper release");
    setError("");
    try {
      const res = await api(`/api/projects/${project.id}/paper-releases/${releaseId}/restore`, {
        method: "POST",
      });
      if (res.project) setProject(res.project);
      setMessage(res.message || "Restored.");
      await loadProjectDetails();
      await loadPaperReleases();
      await loadSectionVersions();
    } catch (e) {
      setError(e.message || "Restore failed.");
    } finally {
      endBusy();
    }
  }

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
    if (!prompt.trim()) {
      setError("Enter a research prompt for this section first.");
      return;
    }
    const hasUrl = /https?:\/\/\S+/i.test(prompt);
    beginBusy(hasUrl ? "Research Assistant (fetching URLs…)" : "Research Assistant (multi-agent)");
    setError("");
    setMessage(
      hasUrl
        ? "Fetching linked URL(s) from the prompt, then running the multi-agent panel. Often 1–3 minutes."
        : "Research Assistant is running. Multi-agent panel often takes 1–3 minutes; draft appears under the buttons when ready."
    );
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
      const src = result.source_urls || {};
      const failed = Array.isArray(src.failed) ? src.failed : [];
      const ok = Array.isArray(src.ok) ? src.ok : [];
      let msg = `${result.notes || "Assistant ready."}${
        result.used_live ? " (live providers)" : " (local scaffold)"
      } Review the draft below, then Apply to paper.`;
      if (ok.length) {
        msg += ` Linked sources ingested: ${ok.map((s) => s.title || s.url).join("; ")}.`;
      }
      setMessage(msg);
      if (failed.length) {
        setError(
          failed
            .map((f) => `${f.url}: ${f.error || "fetch failed"}`)
            .join(" · ")
        );
      }
      await loadProject();
      await loadProjectDetails();
    } catch (e) {
      setError(e.message);
    } finally {
      endBusy();
    }
  }

  async function applyAssistant() {
    if (!assistantOut || !sectionId) return;
    beginBusy("Applying assistant draft");
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
      endBusy();
    }
  }

  async function humanizeSection(mode = "local") {
    if (!activeSection) return;
    const original = activeSection.content_md || "";
    if (!original.trim()) {
      setError(
        "Section paper is empty. Run Research Assistant + Apply to paper first, or write in the paper editor — Live humanize rewrites the section body, not the prompt alone."
      );
      return;
    }
    const rewriteMode = mode === "live" ? "live" : "local";
    beginBusy(rewriteMode === "live" ? "Live humanize (AI rewrite + AI check)" : "Local humanize");
    setError("");
    setMessage(
      rewriteMode === "live"
        ? "Live humanize running: score → rewrite → re-score. Review panel opens below when ready."
        : "Local humanize running…"
    );
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
        body: JSON.stringify({
          text: original,
          strength: "high",
          mode: rewriteMode,
          ...(rewriteMode === "live" ? liveModelPayload() : {}),
        }),
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
      endBusy();
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
    setError("");
    setMessage("Humanize rewrite discarded. Section paper was not changed.");
    // Nudge viewport back to the action row so it is obvious the review panel closed.
    window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  async function runStyleFixFromAiCheck() {
    if (isReviewer) return;
    const scope = aiCheckPanel?.scope === "paper" ? "paper" : "section";
    beginBusy(scope === "paper" ? "Style fix (full paper)" : "Style fix (section)");
    setError("");
    setMessage(
      scope === "paper"
        ? "Building smart style-fix preview across sections…"
        : "Building smart style-fix preview for this section…"
    );
    try {
      const targets =
        scope === "paper"
          ? (sections || []).filter((s) => (s.content_md || "").trim())
          : activeSection
            ? [activeSection]
            : [];
      if (!targets.length) {
        setError("Nothing to fix — paper/section is empty.");
        return;
      }
      const items = [];
      const allOps = [];
      for (const sec of targets) {
        const original = sec.content_md || "";
        const res = await api("/api/research/style-fix", {
          method: "POST",
          body: JSON.stringify({ text: original }),
        });
        if (res.changed) {
          items.push({
            sectionId: sec.id,
            title: sec.title || "Section",
            original,
            proposed: res.proposed || original,
            ops: res.ops || [],
            before: res.before || {},
            after: res.after || {},
          });
          (res.ops || []).forEach((op) => allOps.push(`${sec.title || "Section"}: ${op}`));
        }
      }
      if (!items.length) {
        setMessage("No dash/semicolon style tells to fix in this scope.");
        setStyleFixDraft(null);
        return;
      }
      // Score the joined changed text via style-fix (does not write AI-check history).
      const joinedOriginal = items.map((i) => i.original).join("\n\n");
      const joinedScore = await api("/api/research/style-fix", {
        method: "POST",
        body: JSON.stringify({ text: joinedOriginal }),
      });
      setStyleFixDraft({
        scope,
        items,
        previewIndex: 0,
        ops: allOps,
        before: {
          ai_pct: joinedScore.before?.ai_pct,
          human_pct: joinedScore.before?.human_pct,
        },
        after: {
          ai_pct: joinedScore.after?.ai_pct,
          human_pct: joinedScore.after?.human_pct,
        },
      });
      setRightTab("paper");
      setMessage(
        `Style fix ready: ${items.length} section(s) changed. Review the diff, then Accept.`
      );
    } catch (e) {
      setError(e.message || "Style fix failed.");
    } finally {
      endBusy();
    }
  }

  async function acceptStyleFix() {
    if (!styleFixDraft?.items?.length || !activeId) return;
    const count = styleFixDraft.items.length;
    beginBusy("Applying style fix");
    setError("");
    try {
      for (const item of styleFixDraft.items) {
        const updated = await api(`/api/projects/${activeId}/sections/${item.sectionId}`, {
          method: "PATCH",
          body: JSON.stringify({ content_md: item.proposed }),
        });
        setSections((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      }
      setStyleFixDraft(null);
      setSaveState("saved");
      setMessage(`Applied style fix to ${count} section(s). Re-run AI check to confirm.`);
      await loadProjectDetails();
      await loadSectionVersions();
    } catch (e) {
      setError(e.message || "Could not apply style fix.");
    } finally {
      endBusy();
    }
  }

  function rejectStyleFix() {
    setStyleFixDraft(null);
    setMessage("Style fix discarded. Paper unchanged.");
  }

  function clearAssistantOutputs() {
    setAssistantOut("");
    setCritique("");
    setRedTeam("");
    setError("");
    setMessage("Cleared Assistant draft, Critic, and Red team. Paper and prompt unchanged.");
  }

  async function clearResearchPrompt() {
    if (!project || !activeSection) {
      setPrompt("");
      return;
    }
    setPrompt("");
    setError("");
    beginBusy("Clearing research prompt");
    try {
      const updated = await api(`/api/projects/${project.id}/sections/${activeSection.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          content_md: activeSection.content_md || "",
          prompt: "",
        }),
      });
      setSections((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      setMessage("Research prompt cleared (saved on this section).");
    } catch (e) {
      setError(e.message || "Could not clear prompt.");
    } finally {
      endBusy();
    }
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
    return res;
  }

  async function runSectionAiCheck() {
    const text = activeSection?.content_md || "";
    if (!text.trim()) {
      setSectionAiCheck(null);
      setError("Section paper is empty — nothing to AI-check. Write or apply research first.");
      return null;
    }
    const result = await api("/api/research/ai-check", {
      method: "POST",
      body: JSON.stringify({
        text,
        source_label: `desk-section:${activeSection?.id || sectionId}`,
        mode: "quick",
      }),
    });
    const enriched = { ...result, scope: "section", scope_title: activeSection?.title || "Section" };
    setSectionAiCheck(enriched);
    setAiCheckPanel(enriched);
    return enriched;
  }

  async function runPaperAiCheck() {
    const parts = (sections || [])
      .map((s) => (s.content_md || "").trim())
      .filter(Boolean);
    if (!parts.length) {
      setPaperAiCheck(null);
      setError("Full paper is empty — nothing to AI-check.");
      return null;
    }
    // Join with blank lines only — "---" separators match the dash heuristic and falsely inflate AI %.
    const text = parts.join("\n\n");
    const result = await api("/api/research/ai-check", {
      method: "POST",
      body: JSON.stringify({
        text,
        source_label: `desk-paper:${activeId}`,
        mode: "quick",
      }),
    });
    const enriched = {
      ...result,
      scope: "paper",
      scope_title: project?.title || "Full paper",
      section_count: parts.length,
      char_count: text.length,
    };
    setPaperAiCheck(enriched);
    setAiCheckPanel(enriched);
    return enriched;
  }

  async function refreshDesk({ withAiCheck = true } = {}) {
    if (!activeId) return;
    beginBusy("Refreshing desk metrics");
    setError("");
    try {
      // Realign agent/human ledgers to current paper bodies (fixes stuck 100% after deletes)
      const synced = await api(`/api/projects/${activeId}/resync-contributions`, {
        method: "POST",
      });
      setProject(synced);
      await loadProjectDetails();
      await refreshGate();
      let aiNote = "";
      if (withAiCheck && activeSection) {
        const ai = await runSectionAiCheck();
        if (ai) {
          aiNote = ` · AI likelihood (current paper) ${ai.ai_pct}%`;
        }
      }
      setMessage(
        `Desk refreshed. Agent contribution ${synced.agent_contribution_pct}% · human ${synced.human_contribution_pct}%${aiNote}.`
      );
      await loadSectionVersions();
    } catch (e) {
      setError(e.message || "Refresh failed.");
    } finally {
      endBusy();
    }
  }

  async function downloadDocxBlob(res, filename) {
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function safeFilename(name) {
    return String(name || "research")
      .replace(/[^\w\-]+/g, "_")
      .replace(/_+/g, "_")
      .slice(0, 48) || "research";
  }

  function escapeRegExp(s) {
    return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function paperFindRegex() {
    const raw = findText;
    if (!raw) return null;
    const flags = findCaseSensitive ? "g" : "gi";
    const body = findWholeWord ? `\\b${escapeRegExp(raw)}\\b` : escapeRegExp(raw);
    try {
      return new RegExp(body, flags);
    } catch {
      return null;
    }
  }

  function countPaperMatches() {
    const text = activeSection?.content_md || "";
    const re = paperFindRegex();
    if (!re || !text) {
      setFindMatchCount(0);
      return 0;
    }
    const n = (text.match(re) || []).length;
    setFindMatchCount(n);
    return n;
  }

  function findNextInPaper(overrideNeedle) {
    const el = paperEditorRef.current;
    const text = activeSection?.content_md || "";
    const needle = overrideNeedle != null ? overrideNeedle : findText;
    if (!el || !needle) {
      setError("Enter a word or phrase to find.");
      return;
    }
    const from = el.selectionEnd || 0;
    const hay = findCaseSensitive ? text : text.toLowerCase();
    const needleCmp = findCaseSensitive ? needle : needle.toLowerCase();
    let idx = hay.indexOf(needleCmp, from);
    if (idx < 0 && from > 0) idx = hay.indexOf(needleCmp, 0);
    if (idx < 0) {
      setMessage("No match for that word/phrase in this section.");
      countPaperMatches();
      return;
    }
    el.focus();
    el.setSelectionRange(idx, idx + needle.length);
    // Scroll the match into view roughly
    const before = text.slice(0, idx);
    const line = before.split("\n").length;
    const lineHeight = 18;
    el.scrollTop = Math.max(0, (line - 3) * lineHeight);
    countPaperMatches();
    setError("");
    setMessage(`Found at character ${idx + 1}.`);
  }

  function replaceSelectionOrNext() {
    if (isReviewer || !activeSection) return;
    const el = paperEditorRef.current;
    const text = activeSection.content_md || "";
    const needle = findText;
    if (!needle) {
      setError("Enter the word to replace (Find).");
      return;
    }
    let start = el ? el.selectionStart : 0;
    let end = el ? el.selectionEnd : 0;
    let selected = text.slice(start, end);
    const matchSelected =
      selected &&
      (findCaseSensitive
        ? selected === needle
        : selected.toLowerCase() === needle.toLowerCase());

    if (!matchSelected) {
      // Jump to next match then replace that range
      const hay = findCaseSensitive ? text : text.toLowerCase();
      const needleCmp = findCaseSensitive ? needle : needle.toLowerCase();
      let idx = hay.indexOf(needleCmp, end);
      if (idx < 0) idx = hay.indexOf(needleCmp, 0);
      if (idx < 0) {
        setMessage("No match to replace.");
        countPaperMatches();
        return;
      }
      start = idx;
      end = idx + needle.length;
    }

    const next = text.slice(0, start) + replaceText + text.slice(end);
    setSaveState("dirty");
    setSections((prev) =>
      prev.map((s) => (s.id === sectionId ? { ...s, content_md: next } : s))
    );
    setError("");
    setMessage(`Replaced one occurrence with “${replaceText || "(empty)"}”.`);
    requestAnimationFrame(() => {
      if (el) {
        el.focus();
        const caret = start + replaceText.length;
        el.setSelectionRange(caret, caret);
      }
      countPaperMatches();
    });
  }

  function replaceAllInPaper() {
    if (isReviewer || !activeSection) return;
    const text = activeSection.content_md || "";
    const re = paperFindRegex();
    if (!re || !findText) {
      setError("Enter the word to replace (Find).");
      return;
    }
    const matches = text.match(re) || [];
    if (!matches.length) {
      setMessage("No matches to replace.");
      setFindMatchCount(0);
      return;
    }
    const next = text.replace(re, replaceText);
    setSaveState("dirty");
    setSections((prev) =>
      prev.map((s) => (s.id === sectionId ? { ...s, content_md: next } : s))
    );
    setFindMatchCount(0);
    setError("");
    setMessage(`Replaced ${matches.length} occurrence(s).`);
  }

  function useSelectionAsFind() {
    const el = paperEditorRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    if (start === end) {
      setError("Select a word in the paper first, then click Use selection.");
      return;
    }
    const sel = (activeSection?.content_md || "").slice(start, end);
    setFindText(sel);
    setError("");
    setMessage(`Find set to “${sel}”. Type a replacement and Replace.`);
  }

  function insertMarkdownSnippet(snip) {
    if (isReviewer || !activeSection || !snip) return;
    const el = paperEditorRef.current;
    const text = activeSection.content_md || "";
    const start = el ? el.selectionStart : text.length;
    const end = el ? el.selectionEnd : text.length;
    const selected = text.slice(start, end);
    const beforeChar = start > 0 ? text[start - 1] : "\n";
    const needsLeadingNl = beforeChar && beforeChar !== "\n";

    let insert = "";
    let selFrom = 0;
    let selTo = 0;

    if (snip.kind === "wrap") {
      const inner = selected || snip.placeholder || "text";
      insert = `${snip.before}${inner}${snip.after}`;
      selFrom = start + snip.before.length;
      selTo = selFrom + inner.length;
    } else if (snip.kind === "heading") {
      const inner = selected || snip.placeholder || "Heading";
      const lead = needsLeadingNl ? "\n\n" : start === 0 ? "" : "\n";
      insert = `${lead}${snip.prefix}${inner}\n\n`;
      selFrom = start + lead.length + snip.prefix.length;
      selTo = selFrom + inner.length;
    } else if (snip.kind === "link") {
      const label = selected || snip.placeholder || "text";
      const url = snip.url || "https://example.com";
      insert = `[${label}](${url})`;
      if (selected) {
        selFrom = start + 1;
        selTo = start + 1 + label.length;
      } else {
        selFrom = start + 1;
        selTo = start + 1 + label.length;
      }
    } else if (snip.kind === "line") {
      const lead = needsLeadingNl ? "\n" : "";
      insert = `${lead}${snip.text}\n`;
      if (snip.select) {
        const idx = insert.indexOf(snip.select);
        selFrom = start + idx;
        selTo = selFrom + snip.select.length;
      } else {
        selFrom = selTo = start + insert.length;
      }
    } else if (snip.kind === "block") {
      const lead = needsLeadingNl ? "\n" : "";
      insert = `${lead}${snip.text}`;
      if (!insert.endsWith("\n")) insert += "\n";
      selFrom = selTo = start + insert.length;
    } else {
      insert = snip.text || snip.label || "";
      selFrom = selTo = start + insert.length;
    }

    const next = text.slice(0, start) + insert + text.slice(end);
    setSaveState("dirty");
    setSections((prev) =>
      prev.map((s) => (s.id === sectionId ? { ...s, content_md: next } : s))
    );
    setRightTab("paper");
    setMessage(`Inserted ${snip.label} — edit the highlighted text.`);
    requestAnimationFrame(() => {
      const editor = paperEditorRef.current;
      if (!editor) return;
      editor.focus();
      editor.setSelectionRange(selFrom, selTo);
    });
  }

  async function checkAllSpelling() {
    if (!activeSection) {
      setError("Open a section to spell-check.");
      return;
    }
    const text = activeSection.content_md || "";
    if (!text.trim()) {
      setSpellIssues([]);
      setSpellMessage("Section is empty.");
      return;
    }
    beginBusy("Spell check all");
    setError("");
    try {
      const res = await api("/api/research/spellcheck", {
        method: "POST",
        body: JSON.stringify({ text, max_issues: 80 }),
      });
      setSpellIssues(res.issues || []);
      setSpellMessage(res.message || "");
      setMessage(res.message || "Spell check finished.");
    } catch (e) {
      setError(e.message || "Spell check failed.");
    } finally {
      endBusy();
    }
  }

  function applySpellIssue(issue, suggestion) {
    if (!issue) return;
    const word = issue.word || issue.normalized || "";
    const fix = suggestion || (issue.suggestions || [])[0] || "";
    setFindText(word);
    setReplaceText(fix);
    setFindWholeWord(true);
    setFindCaseSensitive(false);
    setError("");
    setMessage(
      fix
        ? `Ready to replace “${word}” → “${fix}”. Click Replace or Replace all.`
        : `Find set to “${word}”. Pick a suggestion or type a fix.`
    );
    requestAnimationFrame(() => findNextInPaper(word));
  }

  /**
   * Markdown → Word download.
   * scope: "section" | "all"
   * asDraft: paper-area download (skips publish gate)
   * force: admin override on gated export
   */
  async function exportDocx(opts = {}) {
    if (!project) return;
    const scope = opts.scope || "all";
    const asDraft = !!opts.asDraft;
    const force = !!opts.force;
    let content_md = "";
    let title = project.title || "Research";
    if (scope === "section") {
      if (!activeSection) {
        setError("Select a section to export.");
        return;
      }
      content_md = activeSection.content_md || "";
      title = `${project.title} — ${activeSection.title || "section"}`;
    } else {
      content_md = sections
        .map((s) => s.content_md || "")
        .filter((t) => t.trim())
        .join("\n\n---\n\n");
    }
    if (!content_md.trim()) {
      setError("Nothing to export — paper is empty.");
      return;
    }
    beginBusy(asDraft ? "Converting markdown to Word…" : "Exporting Word…");
    setError("");
    try {
      const res = await api("/api/research/export/docx", {
        method: "POST",
        body: JSON.stringify({
          title,
          content_md,
          project_id: activeId,
          force,
          as_draft: asDraft,
        }),
      });
      const suffix = asDraft ? "_draft" : "";
      const base =
        scope === "section"
          ? `${safeFilename(project.title)}_${safeFilename(activeSection?.title || "section")}`
          : safeFilename(project.title);
      await downloadDocxBlob(res, `${base}${suffix}.docx`);
      setMessage(
        asDraft
          ? `Word download ready (${scope === "section" ? "this section" : "full paper"}). Markdown converted to .docx.`
          : force
            ? "Exported with force override."
            : "Exported. Publish gate passed."
      );
    } catch (e) {
      setError(typeof e.message === "string" ? e.message : JSON.stringify(e.message));
    } finally {
      endBusy();
    }
  }

  function taskIsDone(task) {
    const s = String(task?.status || "").toLowerCase();
    return s === "done" || s === "completed";
  }

  async function addSection() {
    if (!project || isReviewer) return;
    const title = (newSectionTitle || "").trim() || "New section";
    beginBusy("Adding section");
    setError("");
    try {
      const created = await api(`/api/projects/${project.id}/sections`, {
        method: "POST",
        body: JSON.stringify({
          title,
          prompt: "",
          content_md: `# ${title}\n\n`,
        }),
      });
      setNewSectionTitle("");
      await loadProjectDetails();
      await loadProject();
      if (created?.id) setSectionId(created.id);
      setMessage(`Added section “${title}”. Template sections stay; this one is extra.`);
      setRightTab("paper");
    } catch (e) {
      setError(e.message || "Could not add section.");
    } finally {
      endBusy();
    }
  }

  async function deleteSection(section) {
    if (!project || !section || isReviewer) return;
    if (sections.length <= 1) {
      setError("Keep at least one section in the paper.");
      return;
    }
    if (!window.confirm(`Delete section “${section.title}”? Its paper text will be removed.`)) {
      return;
    }
    beginBusy("Deleting section");
    setError("");
    try {
      await api(`/api/projects/${project.id}/sections/${section.id}`, { method: "DELETE" });
      if (sectionId === section.id) setSectionId(null);
      await loadProjectDetails();
      await loadProject();
      setMessage(`Deleted section “${section.title}”.`);
    } catch (e) {
      setError(e.message || "Could not delete section.");
    } finally {
      endBusy();
    }
  }

  async function renameSection(section) {
    if (!project || !section || isReviewer) return;
    const next = window.prompt("Section title", section.title || "");
    if (next == null) return;
    const title = next.trim();
    if (!title || title === section.title) return;
    beginBusy("Renaming section");
    setError("");
    try {
      const updated = await api(`/api/projects/${project.id}/sections/${section.id}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      });
      setSections((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      setMessage(`Renamed section to “${title}”.`);
    } catch (e) {
      setError(e.message || "Could not rename section.");
    } finally {
      endBusy();
    }
  }

  async function moveSection(section, direction) {
    if (!project || !section || isReviewer) return;
    beginBusy(direction === "up" ? "Moving section up" : "Moving section down");
    setError("");
    try {
      const ordered = await api(
        `/api/projects/${project.id}/sections/${section.id}/move?direction=${encodeURIComponent(direction)}`,
        { method: "POST" }
      );
      if (Array.isArray(ordered)) {
        setSections(ordered);
      } else {
        await loadProjectDetails();
      }
      setMessage(
        direction === "up"
          ? `Moved “${section.title}” up.`
          : `Moved “${section.title}” down.`
      );
      await loadProject();
    } catch (e) {
      setError(e.message || "Could not reorder section.");
    } finally {
      endBusy();
    }
  }

  function exportTasksCsv() {
    if (!tasks.length) {
      setError("No tasks to export.");
      return;
    }
    const esc = (v) => {
      const s = String(v ?? "");
      if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
      return s;
    };
    const header = ["id", "title", "status", "priority", "description", "created_at", "updated_at"];
    const lines = [header.join(",")];
    for (const t of tasks) {
      lines.push(
        [
          t.id,
          t.title || "",
          taskIsDone(t) ? "done" : t.status || "todo",
          t.priority || "",
          t.description || "",
          t.created_at || "",
          t.updated_at || "",
        ]
          .map(esc)
          .join(",")
      );
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${safeFilename(project?.title || "research")}_tasks.csv`;
    a.click();
    URL.revokeObjectURL(url);
    setError("");
    setMessage(`Exported ${tasks.length} task(s) to CSV.`);
  }

  async function addTask() {
    if (!taskTitle.trim() || !activeId || isReviewer) return;
    beginBusy("Adding task");
    setError("");
    try {
      await api(`/api/projects/${activeId}/tasks`, {
        method: "POST",
        body: JSON.stringify({ title: taskTitle.trim(), status: "todo" }),
      });
      setTaskTitle("");
      await loadProjectDetails();
      await loadProject();
      setMessage("Task added.");
    } catch (e) {
      setError(e.message || "Could not add task.");
    } finally {
      endBusy();
    }
  }

  async function toggleTaskDone(task) {
    if (!activeId || !task || isReviewer) return;
    const next = taskIsDone(task) ? "todo" : "done";
    beginBusy(next === "done" ? "Marking task done" : "Reopening task");
    setError("");
    try {
      const updated = await api(`/api/projects/${activeId}/tasks/${task.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: next }),
      });
      setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
      await loadProject();
      setMessage(next === "done" ? "Task completed." : "Task reopened.");
    } catch (e) {
      setError(e.message || "Could not update task.");
    } finally {
      endBusy();
    }
  }

  function startEditTask(task) {
    if (!task || isReviewer) return;
    setEditingTaskId(task.id);
    setEditingTaskTitle(task.title || "");
  }

  function cancelEditTask() {
    setEditingTaskId(null);
    setEditingTaskTitle("");
  }

  async function saveTaskTitle(task) {
    if (!activeId || !task || isReviewer) return;
    const title = editingTaskTitle.trim();
    if (!title) {
      setError("Task title cannot be empty.");
      return;
    }
    if (title === task.title) {
      cancelEditTask();
      return;
    }
    beginBusy("Saving task");
    setError("");
    try {
      const updated = await api(`/api/projects/${activeId}/tasks/${task.id}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      });
      setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
      cancelEditTask();
      setMessage("Task updated.");
    } catch (e) {
      setError(e.message || "Could not update task.");
    } finally {
      endBusy();
    }
  }

  async function deleteTask(task) {
    if (!activeId || !task || isReviewer) return;
    if (!window.confirm(`Delete task “${task.title}”?`)) return;
    beginBusy("Deleting task");
    setError("");
    try {
      await api(`/api/projects/${activeId}/tasks/${task.id}`, { method: "DELETE" });
      setTasks((prev) => prev.filter((t) => t.id !== task.id));
      if (editingTaskId === task.id) cancelEditTask();
      await loadProject();
      setMessage("Task deleted.");
    } catch (e) {
      setError(e.message || "Could not delete task.");
    } finally {
      endBusy();
    }
  }

  async function uploadArtifact(e) {
    const file = e.target.files?.[0];
    if (!file || !activeId) return;
    beginBusy("Uploading artifact");
    try {
      const form = new FormData();
      form.append("file", file);
      await api(`/api/research/projects/${activeId}/artifacts`, {
        method: "POST",
        body: form,
      });
      await loadProjectDetails();
      setMessage(`Uploaded ${file.name}`);
    } catch (err) {
      setError(err.message || "Upload failed.");
    } finally {
      endBusy();
      e.target.value = "";
    }
  }

  async function saveArtifactUrl(e) {
    e?.preventDefault?.();
    if (!activeId) return;
    const url = artifactUrl.trim();
    if (!/^https?:\/\//i.test(url)) {
      setError("Enter a valid http(s) URL to save.");
      return;
    }
    beginBusy("Saving URL artifact");
    setError("");
    try {
      const row = await api(`/api/research/projects/${activeId}/artifacts/url`, {
        method: "POST",
        body: JSON.stringify({
          url,
          title: artifactUrlTitle.trim(),
          notes: artifactUrlNote.trim(),
        }),
      });
      setArtifactUrl("");
      setArtifactUrlTitle("");
      setArtifactUrlNote("");
      await loadProjectDetails();
      setMessage(`Saved URL: ${row.original_name || url}`);
    } catch (err) {
      setError(err.message || "Could not save URL.");
    } finally {
      endBusy();
    }
  }

  async function downloadArtifactFile(artifact) {
    if (!activeId || !artifact?.id) return;
    beginBusy("Downloading artifact");
    setError("");
    try {
      const token = getToken();
      const res = await fetch(
        `/api/research/projects/${activeId}/artifacts/${artifact.id}/download`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      if (!res.ok) {
        throw new Error((await res.text()) || "Download failed");
      }
      const blob = await res.blob();
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = artifact.original_name || "artifact.bin";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(href);
    } catch (err) {
      setError(err.message || "Download failed.");
    } finally {
      endBusy();
    }
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

  function scholarYearParams() {
    return appendScholarDateParams(new URLSearchParams(), scholarYearFrom, scholarYearTo);
  }

  function applyScholarYearPreset(preset) {
    const { from, to } = scholarDatePreset(preset);
    setScholarYearFrom(from);
    setScholarYearTo(to);
  }

  async function searchScholar(topicOverride) {
    const q = (topicOverride ?? scholarQ).trim();
    if (q.length < 2) {
      setError("Enter a topic of at least 2 characters for scholar search.");
      return;
    }
    beginBusy("Scholar search");
    setError("");
    setScholarNote("");
    try {
      const params = scholarYearParams();
      params.set("q", q);
      params.set("limit", "12");
      const res = await api(`/api/workspace/scholar/search?${params.toString()}`);
      setScholarHits(res.results || []);
      setScholarQ(q);
      const yearBit =
        res.date_from || res.date_to || res.year_from || res.year_to
          ? ` · published ${res.date_from || res.year_from || "…"}–${res.date_to || res.year_to || "…"}`
          : "";
      let note =
        res.message ||
        `Found ${res.total || 0} scholarly hit(s)` +
          (res.sources_tried?.length ? ` via ${res.sources_tried.join(", ")}` : "") +
          yearBit +
          ". Ranked by topic fit + citations + recency.";
      if (res.source_errors?.length) {
        note = `${note} ${res.source_errors.join(" · ")}`;
      }
      setScholarNote(note);
      if (res.note) setMessage(res.note);
    } catch (e) {
      setError(e.message || "Scholar search failed.");
    } finally {
      endBusy();
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
          <div className="row" style={{ marginTop: "0.35rem", flexWrap: "wrap", gap: "0.4rem", alignItems: "center" }}>
            <span className="badge good" title="Working line — Save does not bump this">
              Working v{project?.working_version || "0.1.1"}
            </span>
            {project?.primary_version ? (
              <span className="badge" title="Last official primary publish">
                Primary v{project.primary_version}
              </span>
            ) : (
              <span className="badge" title="No primary publish yet">
                Primary — none yet
              </span>
            )}
            <HelpIcon label="Version help">
              <strong>Versions</strong>
              <div style={{ marginTop: "0.35rem" }}>
                <div>
                  <strong>Save</strong> keeps the draft only (version stays the same).
                </div>
                <div>
                  <strong>Commit</strong> freezes a full-paper snapshot, then bumps patch (0.1.1 → 0.1.2).
                </div>
                <div>
                  <strong>Publish primary</strong> freezes official major.0.0 (e.g. 1.0.0); work continues on
                  major.1.1.
                </div>
                <div style={{ marginTop: "0.35rem" }}>
                  Example: work 0.1.1…0.1.19 → Publish → primary 1.0.0, then next commits on 1.1.1…
                </div>
              </div>
            </HelpIcon>
          </div>
          <p className="muted" style={{ margin: "0.25rem 0 0" }}>
            Panel research desk for OffSec · Exposure · VM.
          </p>
        </div>
        <div className="row" style={{ flexWrap: "wrap" }}>
          <span className="badge">{providers.length} live providers</span>
          {!isReviewer && (
            <>
              <input
                style={{ minWidth: 140, maxWidth: 200 }}
                placeholder="Commit note (optional)"
                value={commitNote}
                onChange={(e) => setCommitNote(e.target.value)}
                disabled={busy}
              />
              <button
                className="btn"
                type="button"
                disabled={busy}
                onClick={commitPaper}
                title="Snapshot full paper at current version, then bump patch (0.1.1 → 0.1.2)"
              >
                Commit
              </button>
              <button
                className="btn primary"
                type="button"
                disabled={busy}
                onClick={publishPrimaryPaper}
                title="Publish primary major.0.0 from current paper; work continues on major.1.1"
              >
                Publish primary
              </button>
            </>
          )}
          <button
            className="btn"
            type="button"
            onClick={() => refreshDesk({ withAiCheck: true })}
            disabled={busy}
            title="Resync agent/human % from current paper, refresh publish gate, re-run AI check on this section"
          >
            {busyLabel?.includes("Refreshing") ? "Refreshing…" : "Refresh desk"}
          </button>
          <button
            className="btn"
            type="button"
            onClick={async () => {
              beginBusy("AI check (current section)");
              setError("");
              try {
                const ai = await runSectionAiCheck();
                if (ai) {
                  setMessage(
                    `AI check (section “${ai.scope_title}”): ${ai.ai_pct}% likelihood — see Why below.`
                  );
                }
              } catch (e) {
                setError(e.message || "AI check failed.");
              } finally {
                endBusy();
              }
            }}
            disabled={busy || !activeSection}
            title="Local AI-likelihood check on the active section, with why breakdown"
          >
            {busyLabel?.includes("current section") ? "Checking…" : "AI check section"}
          </button>
          <button
            className="btn"
            type="button"
            onClick={async () => {
              beginBusy("AI check (full paper)");
              setError("");
              try {
                const ai = await runPaperAiCheck();
                if (ai) {
                  setMessage(
                    `AI check (full paper): ${ai.ai_pct}% likelihood across ${ai.section_count || "all"} sections — see Why below.`
                  );
                }
              } catch (e) {
                setError(e.message || "Full paper AI check failed.");
              } finally {
                endBusy();
              }
            }}
            disabled={busy || !sections.length}
            title="Local AI-likelihood check on all sections joined, with why breakdown"
          >
            {busyLabel?.includes("full paper") ? "Checking…" : "AI check full paper"}
          </button>
          <button className="btn" type="button" onClick={() => refreshGate()} disabled={busy}>
            Refresh publish gate
          </button>
          <button
            className="btn primary"
            type="button"
            onClick={() => exportDocx({ scope: "all", asDraft: false })}
            disabled={busy}
            title="Full paper Word export (publish gate applies)"
          >
            Export Word
          </button>
          {user?.role === "admin" && (
            <button
              className="btn ghost"
              type="button"
              onClick={() => exportDocx({ scope: "all", force: true })}
              disabled={busy}
            >
              Force export
            </button>
          )}
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}
      {busy && (
        <div className="alert warn busy-banner thinking-banner" role="status" aria-live="polite">
          <span className="thinking-dot" aria-hidden="true" />
          <div>
            <strong>Thinking… {busyLabel || "Working"}</strong>
            <div className="muted" style={{ marginTop: "0.2rem" }}>
              Button click registered · {busyElapsedSec}s elapsed
              {busyLabel?.includes("Research Assistant")
                ? " · multi-agent often takes 1–3 minutes; keep this tab open"
                : busyLabel?.includes("Live humanize")
                  ? " · rewrite + AI checks in progress"
                  : " · please wait"}
            </div>
          </div>
        </div>
      )}
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
              <div className="muted" style={{ fontSize: "0.75rem", marginTop: "0.25rem" }}>
                From paper body · Refresh desk after deletes
              </div>
            </div>
            <div className="metric">
              <span className="muted">Human contribution</span>
              <strong>{project.human_contribution_pct}%</strong>
            </div>
            <div className="metric">
              <span className="muted">AI check (this section)</span>
              <strong
                className={
                  sectionAiCheck
                    ? sectionAiCheck.ai_pct >= 10
                      ? "badge bad"
                      : "badge good"
                    : ""
                }
                style={{ fontSize: sectionAiCheck ? undefined : "1rem" }}
              >
                {sectionAiCheck ? `${sectionAiCheck.ai_pct}%` : "Not run"}
              </strong>
              <div className="muted" style={{ fontSize: "0.75rem", marginTop: "0.25rem" }}>
                {sectionAiCheck ? "Latest section scan" : "AI check section"}
              </div>
            </div>
            <div className="metric">
              <span className="muted">AI check (full paper)</span>
              <strong
                className={
                  paperAiCheck
                    ? paperAiCheck.ai_pct >= 10
                      ? "badge bad"
                      : "badge good"
                    : ""
                }
                style={{ fontSize: paperAiCheck ? undefined : "1rem" }}
              >
                {paperAiCheck ? `${paperAiCheck.ai_pct}%` : "Not run"}
              </strong>
              <div className="muted" style={{ fontSize: "0.75rem", marginTop: "0.25rem" }}>
                {paperAiCheck ? "All sections joined" : "AI check full paper"}
              </div>
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

          {aiCheckPanel && (
            <div className="panel stack" style={{ borderColor: "rgba(79, 140, 255, 0.35)" }}>
              <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
                <div className="row" style={{ gap: "0.4rem", alignItems: "center", flexWrap: "wrap" }}>
                  <strong>
                    AI check why · {aiCheckPanel.scope === "paper" ? "full paper" : "section"}
                  </strong>
                  <span
                    className={
                      aiCheckPanel.ai_pct >= 10 ? "badge bad" : "badge good"
                    }
                  >
                    {aiCheckPanel.ai_pct}% AI · {aiCheckPanel.human_pct}% human
                  </span>
                  <span className="muted" style={{ fontSize: "0.85rem" }}>
                    {aiCheckPanel.scope_title || ""}
                    {aiCheckPanel.section_count
                      ? ` · ${aiCheckPanel.section_count} sections`
                      : ""}
                  </span>
                </div>
                <div className="row" style={{ gap: "0.35rem" }}>
                  {!isReviewer &&
                    ((aiCheckPanel.signals?.dash_hits || 0) > 0 ||
                      (aiCheckPanel.signals?.semicolon_hits || 0) > 0 ||
                      (aiCheckPanel.why || []).some((w) => /dash|semicolon/i.test(String(w)))) && (
                      <button
                        className="btn primary"
                        type="button"
                        disabled={busy}
                        onClick={runStyleFixFromAiCheck}
                        title="Preview smart fixes for en/em dashes, --, and semicolons (Accept required)"
                      >
                        Fix style tells
                      </button>
                    )}
                  <button
                    className="btn ghost"
                    type="button"
                    onClick={() => setAiCheckPanel(null)}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
              <p className="muted" style={{ margin: 0, fontSize: "0.85rem" }}>
                Local heuristic (not a forensic detector). Score starts at a baseline, then style
                signals push it up or down. Last run is restored after refresh from AI check history.
                Fix converts date ranges like 1–30 to 1-30, other banned dashes to commas, and
                semicolons to periods — preview before Accept. Does not add contractions.
              </p>
              {(aiCheckPanel.why || []).length > 0 && (
                <div>
                  <strong style={{ fontSize: "0.9rem" }}>Why this score</strong>
                  <ul style={{ margin: "0.35rem 0 0", paddingLeft: "1.1rem" }}>
                    {(aiCheckPanel.why || []).map((line, idx) => (
                      <li key={`why-${idx}`} style={{ marginBottom: "0.2rem" }}>
                        {line}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {(aiCheckPanel.recommendations || []).length > 0 && (
                <div>
                  <strong style={{ fontSize: "0.9rem" }}>What to do</strong>
                  <ul style={{ margin: "0.35rem 0 0", paddingLeft: "1.1rem" }}>
                    {(aiCheckPanel.recommendations || []).map((line, idx) => (
                      <li key={`rec-${idx}`} style={{ marginBottom: "0.2rem" }}>
                        {line}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {aiCheckPanel.signals && (
                <div className="row" style={{ flexWrap: "wrap", gap: "0.35rem" }}>
                  <span className="badge">
                    words {aiCheckPanel.signals.word_count ?? "—"}
                  </span>
                  <span className="badge">
                    avg sentence {aiCheckPanel.signals.avg_sentence_len ?? "—"}
                  </span>
                  <span className="badge">
                    stock phrases {aiCheckPanel.signals.banned_phrase_hits ?? 0}
                  </span>
                  <span className="badge">
                    dashes {aiCheckPanel.signals.dash_hits ?? 0}
                  </span>
                  <span className="badge">
                    contractions {aiCheckPanel.signals.contraction_hits ?? 0}
                  </span>
                  <span className="badge">
                    unique ratio {aiCheckPanel.signals.unique_word_ratio ?? "—"}
                  </span>
                </div>
              )}
            </div>
          )}

          <div className="grid-2">
            <div className="panel stack">
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <h2 style={{ margin: 0 }}>Sections (panel structure)</h2>
                <HelpIcon label="Sections help">
                  Templates give you a starting outline. Add more sections anytime. Use ↑ / ↓ to reorder
                  tiles (for example move Quick actions above Conclusion). Rename or delete from each row.
                </HelpIcon>
              </div>
              <div className="section-list" style={{ maxHeight: 360 }}>
                {sections.map((s, idx) => (
                  <div
                    key={s.id}
                    className={`section-item ${s.id === sectionId ? "active" : ""}`}
                    style={{ display: "flex", gap: "0.35rem", alignItems: "stretch" }}
                  >
                    {!isReviewer && (
                      <div className="stack" style={{ gap: "0.15rem", justifyContent: "center" }}>
                        <button
                          className="btn ghost"
                          type="button"
                          style={{ padding: "0.1rem 0.35rem", fontSize: "0.75rem", minWidth: "1.6rem" }}
                          disabled={busy || idx === 0}
                          title="Move section up"
                          onClick={(e) => {
                            e.stopPropagation();
                            moveSection(s, "up");
                          }}
                        >
                          ↑
                        </button>
                        <button
                          className="btn ghost"
                          type="button"
                          style={{ padding: "0.1rem 0.35rem", fontSize: "0.75rem", minWidth: "1.6rem" }}
                          disabled={busy || idx >= sections.length - 1}
                          title="Move section down"
                          onClick={(e) => {
                            e.stopPropagation();
                            moveSection(s, "down");
                          }}
                        >
                          ↓
                        </button>
                      </div>
                    )}
                    <button
                      type="button"
                      className="section-item-main"
                      style={{
                        flex: 1,
                        textAlign: "left",
                        background: "transparent",
                        border: "none",
                        color: "inherit",
                        cursor: "pointer",
                        padding: 0,
                      }}
                      onClick={() => setSectionId(s.id)}
                    >
                      <div>{s.title}</div>
                      <div className="muted" style={{ fontSize: "0.8rem" }}>
                        agent {s.agent_chars} · human {s.human_chars}
                      </div>
                    </button>
                    {!isReviewer && (
                      <div className="stack" style={{ gap: "0.2rem", justifyContent: "center" }}>
                        <button
                          className="btn ghost"
                          type="button"
                          style={{ padding: "0.15rem 0.4rem", fontSize: "0.75rem" }}
                          disabled={busy}
                          title="Rename section"
                          onClick={(e) => {
                            e.stopPropagation();
                            renameSection(s);
                          }}
                        >
                          Rename
                        </button>
                        <button
                          className="btn ghost"
                          type="button"
                          style={{ padding: "0.15rem 0.4rem", fontSize: "0.75rem" }}
                          disabled={busy || sections.length <= 1}
                          title="Delete section"
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteSection(s);
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {!isReviewer && (
                <>
                  <div className="row" style={{ alignItems: "flex-end", flexWrap: "wrap" }}>
                    <label style={{ flex: 1, minWidth: 160 }}>
                      Add section
                      <input
                        value={newSectionTitle}
                        onChange={(e) => setNewSectionTitle(e.target.value)}
                        placeholder="e.g. Appendix · Buyer implications"
                        disabled={busy}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            addSection();
                          }
                        }}
                      />
                    </label>
                    <button
                      className="btn primary"
                      type="button"
                      disabled={busy}
                      onClick={addSection}
                      title="Append a new section after the template outline"
                    >
                      Add section
                    </button>
                  </div>
                  <div className="stack" style={{ gap: "0.35rem" }}>
                    <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                      <strong style={{ fontSize: "0.92rem" }}>Research prompt for this section</strong>
                      <button
                        className="btn ghost"
                        type="button"
                        onClick={clearResearchPrompt}
                        disabled={busy || !String(prompt || "").trim()}
                        title="Clear the saved research prompt on this section (paper unchanged)"
                      >
                        Clear prompt
                      </button>
                    </div>
                    <textarea
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      onBlur={() => {
                        if (!project || !activeSection || isReviewer) return;
                        const saved = activeSection.prompt || "";
                        if (saved === (prompt || "")) return;
                        api(`/api/projects/${project.id}/sections/${activeSection.id}`, {
                          method: "PATCH",
                          body: JSON.stringify({
                            content_md: activeSection.content_md || "",
                            prompt: prompt || "",
                          }),
                        })
                          .then((updated) => {
                            setSections((prev) =>
                              prev.map((s) => (s.id === updated.id ? updated : s))
                            );
                          })
                          .catch(() => {});
                      }}
                      placeholder="What should the panel explore? Paste article URLs here — they are fetched and summarized into context."
                      lang="en"
                      spellCheck
                    />
                  </div>
                  <p className="muted" style={{ margin: 0, fontSize: "0.82rem" }}>
                    Tip: paste http(s) links (up to 3) for a research-paper source note (article
                    synopsis + implications for exposure management writing). Add{" "}
                    <code>full framing</code> / <code>with ATT&amp;CK</code> only when you want deeper
                    threat/program sections. Cloudflare pages may need a free Jina key, or paste the
                    article text. Prompt is saved on this section — use Clear prompt if a test URL sticks.
                  </p>
                  <div className="row">
                    <button className="btn primary" onClick={runAssistant} disabled={busy}>
                      {busyLabel?.includes("Research Assistant") ? "Researching…" : "Research Assistant"}
                    </button>
                    <button className="btn" onClick={applyAssistant} disabled={!assistantOut || busy}>
                      Apply to paper
                    </button>
                    <button
                      className="btn ghost"
                      type="button"
                      onClick={clearAssistantOutputs}
                      disabled={busy || (!assistantOut && !critique && !redTeam)}
                      title="Clear Assistant draft, Critic, and Red team (does not change the paper or prompt)"
                    >
                      Clear
                    </button>
                    <label style={{ minWidth: 220 }}>
                      Live model
                      <select
                        value={liveModelId}
                        onChange={(e) => setLiveModelId(e.target.value)}
                        disabled={busy}
                      >
                        {liveModelOptions.map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      className="btn"
                      onClick={() => humanizeSection("local")}
                      disabled={busy || !activeSection}
                      title="Free local style cleanup, then review before save"
                    >
                      {busyLabel === "Local humanize" ? "Humanizing…" : "Local humanize"}
                    </button>
                    <button
                      className="btn"
                      onClick={() => humanizeSection("live")}
                      disabled={busy || !activeSection}
                      title="Live rewrite with selected model (same API key). Rewrites paper body, not the prompt."
                    >
                      {busyLabel?.includes("Live humanize") ? "Humanizing…" : "Live humanize"}
                    </button>
                    <button className="btn" onClick={judgeSection} disabled={busy}>
                      Judge
                    </button>
                    <button className="btn" onClick={runEvidence} disabled={busy}>
                      Evidence check
                    </button>
                  </div>
                  {busy && (
                    <div className="thinking-inline" role="status" aria-live="polite">
                      <span className="thinking-dot" aria-hidden="true" />
                      <div>
                        <strong>Thinking…</strong> {busyLabel || "Working"}
                        <div className="muted" style={{ fontSize: "0.85rem" }}>
                          You hit the button · {busyElapsedSec}s · draft/review appears below when finished
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}

              {(assistantOut || critique || redTeam) && !isReviewer && (
                <div className="stack" ref={assistantRef}>
                  {assistantOut && (
                    <>
                      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                        <strong>Assistant draft</strong>
                        <div className="row">
                          <button
                            className="btn ghost"
                            type="button"
                            onClick={clearAssistantOutputs}
                            disabled={busy}
                            title="Clear Assistant draft, Critic, and Red team"
                          >
                            Clear
                          </button>
                          <button className="btn" type="button" onClick={applyAssistant} disabled={busy}>
                            Apply to paper
                          </button>
                        </div>
                      </div>
                      <textarea
                        value={assistantOut}
                        onChange={(e) => setAssistantOut(e.target.value)}
                        lang="en"
                        spellCheck
                      />
                      <p className="muted" style={{ margin: 0, fontSize: "0.8rem" }}>
                        Not in the paper until you Apply. Clear removes draft + Critic + Red team only.
                      </p>
                    </>
                  )}
                </div>
              )}

              {styleFixDraft && !isReviewer && (
                <div
                  className="panel stack"
                  ref={styleFixRef}
                  style={{ borderColor: "rgba(79, 140, 255, 0.4)" }}
                >
                  <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
                    <h3 style={{ margin: 0 }}>
                      Style fix preview ·{" "}
                      {styleFixDraft.scope === "paper"
                        ? `full paper (${styleFixDraft.items.length} section${
                            styleFixDraft.items.length === 1 ? "" : "s"
                          })`
                        : styleFixDraft.items[0]?.title || "section"}
                    </h3>
                    <div className="row">
                      <button className="btn" type="button" onClick={rejectStyleFix} disabled={busy}>
                        Reject
                      </button>
                      <button
                        className="btn primary"
                        type="button"
                        onClick={acceptStyleFix}
                        disabled={busy}
                      >
                        Accept fix
                      </button>
                    </div>
                  </div>
                  <p className="muted" style={{ margin: 0 }}>
                    Smart fixes only (range dashes → hyphen, other banned dashes → comma, semicolons →
                    period). Not saved until Accept. Red = removed, green = added.
                  </p>
                  {(styleFixDraft.ops || []).length > 0 && (
                    <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.85rem" }}>
                      {styleFixDraft.ops.slice(0, 8).map((op, idx) => (
                        <li key={`op-${idx}`}>{op}</li>
                      ))}
                    </ul>
                  )}
                  <div className="grid-3">
                    <div className="metric">
                      <span className="muted">Before AI %</span>
                      <strong
                        className={
                          (styleFixDraft.before?.ai_pct || 0) >= 10 ? "badge bad" : "badge good"
                        }
                      >
                        {styleFixDraft.before?.ai_pct ?? "—"}%
                      </strong>
                    </div>
                    <div className="metric">
                      <span className="muted">After AI %</span>
                      <strong
                        className={
                          (styleFixDraft.after?.ai_pct || 0) >= 10 ? "badge bad" : "badge good"
                        }
                      >
                        {styleFixDraft.after?.ai_pct ?? "—"}%
                      </strong>
                    </div>
                    <div className="metric">
                      <span className="muted">Delta</span>
                      <strong style={{ fontSize: "1rem" }}>
                        {(() => {
                          const b = Number(styleFixDraft.before?.ai_pct);
                          const a = Number(styleFixDraft.after?.ai_pct);
                          if (Number.isNaN(b) || Number.isNaN(a)) return "—";
                          const d = Number((b - a).toFixed(1));
                          if (d > 0) return `↓ ${d} pts`;
                          if (d < 0) return `↑ ${Math.abs(d)} pts`;
                          return "No change";
                        })()}
                      </strong>
                    </div>
                  </div>
                  {styleFixDraft.items.length > 1 && (
                    <label>
                      Preview section
                      <select
                        value={String(styleFixDraft.previewIndex || 0)}
                        onChange={(e) =>
                          setStyleFixDraft((d) =>
                            d ? { ...d, previewIndex: Number(e.target.value) || 0 } : d
                          )
                        }
                      >
                        {styleFixDraft.items.map((item, idx) => (
                          <option key={item.sectionId} value={idx}>
                            {item.title}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <TextDiffPanes
                    original={
                      styleFixDraft.items[styleFixDraft.previewIndex || 0]?.original || ""
                    }
                    proposed={
                      styleFixDraft.items[styleFixDraft.previewIndex || 0]?.proposed || ""
                    }
                    originalLabel="Original"
                    proposedLabel="Proposed style fix"
                    editableProposed
                    onProposedChange={(next) =>
                      setStyleFixDraft((d) => {
                        if (!d) return d;
                        const idx = d.previewIndex || 0;
                        const items = d.items.map((it, i) =>
                          i === idx ? { ...it, proposed: next } : it
                        );
                        return { ...d, items };
                      })
                    }
                  />
                </div>
              )}

              {humanizeDraft && !isReviewer && (
                <div className="panel stack" ref={humanizeRef} style={{ borderColor: "rgba(46, 204, 113, 0.35)" }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <h3 style={{ margin: 0 }}>
                      Humanize review · {humanizeDraft.sectionTitle || "section"}
                    </h3>
                    <div className="row">
                      <button
                        className="btn"
                        type="button"
                        onClick={rejectHumanize}
                        disabled={busy}
                        title="Discard this rewrite. Paper stays as-is. Does not clear Research Assistant draft."
                      >
                        Reject rewrite
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
                  <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                    <strong>Critic</strong>
                    <button
                      className="btn ghost"
                      type="button"
                      onClick={clearAssistantOutputs}
                      disabled={busy}
                      title="Clear Assistant draft, Critic, and Red team"
                    >
                      Clear
                    </button>
                  </div>
                  <pre style={{ whiteSpace: "pre-wrap", margin: "0.4rem 0 0", fontFamily: "var(--mono)", fontSize: "0.82rem" }}>
                    {critique}
                  </pre>
                </div>
              )}
              {redTeam && (
                <div className="alert warn">
                  <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                    <strong>Red team</strong>
                    <button
                      className="btn ghost"
                      type="button"
                      onClick={clearAssistantOutputs}
                      disabled={busy}
                      title="Clear Assistant draft, Critic, and Red team"
                    >
                      Clear
                    </button>
                  </div>
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

              <CollapsibleTile
                title="Tasks"
                summary={
                  tasks.length
                    ? `${tasks.filter((t) => !taskIsDone(t)).length} open · ${tasks.length} total`
                    : "Collapsed · research checklist"
                }
                defaultOpen={false}
              >
                <p className="muted" style={{ margin: 0, fontSize: "0.85rem" }}>
                  Check to cross off when done. Edit title inline. Open tasks count toward project progress.
                </p>
                {!isReviewer && (
                  <div className="row">
                    <input
                      placeholder="Add research task"
                      value={taskTitle}
                      onChange={(e) => setTaskTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addTask();
                        }
                      }}
                      disabled={busy}
                    />
                    <button className="btn" type="button" onClick={addTask} disabled={busy || !taskTitle.trim()}>
                      Add
                    </button>
                    <button
                      className="btn primary"
                      type="button"
                      onClick={exportTasksCsv}
                      disabled={busy || !tasks.length}
                      title="Download tasks as CSV"
                    >
                      Export CSV
                    </button>
                  </div>
                )}
                {isReviewer && (
                  <div className="row">
                    <button
                      className="btn primary"
                      type="button"
                      onClick={exportTasksCsv}
                      disabled={busy || !tasks.length}
                      title="Download tasks as CSV"
                    >
                      Export CSV
                    </button>
                  </div>
                )}
                <div className="task-list stack">
                  {!tasks.length && <p className="muted" style={{ margin: 0 }}>No tasks yet.</p>}
                  {tasks.map((t) => {
                    const done = taskIsDone(t);
                    const editing = editingTaskId === t.id;
                    return (
                      <div
                        key={t.id}
                        className={`task-row row ${done ? "task-done" : ""}`}
                        style={{ alignItems: "center", gap: "0.5rem" }}
                      >
                        <label
                          className="task-check"
                          title={done ? "Mark as not done" : "Cross off as done"}
                          style={{ display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}
                        >
                          <input
                            type="checkbox"
                            checked={done}
                            onChange={() => toggleTaskDone(t)}
                            disabled={busy || editing || isReviewer}
                          />
                          <span className="sr-only">{done ? "Done" : "Todo"}</span>
                        </label>
                        {editing && !isReviewer ? (
                          <>
                            <input
                              style={{ flex: 1 }}
                              value={editingTaskTitle}
                              onChange={(e) => setEditingTaskTitle(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  saveTaskTitle(t);
                                } else if (e.key === "Escape") {
                                  e.preventDefault();
                                  cancelEditTask();
                                }
                              }}
                              disabled={busy}
                              autoFocus
                            />
                            <button className="btn primary" type="button" disabled={busy} onClick={() => saveTaskTitle(t)}>
                              Save
                            </button>
                            <button className="btn ghost" type="button" disabled={busy} onClick={cancelEditTask}>
                              Cancel
                            </button>
                          </>
                        ) : (
                          <>
                            <span
                              className="task-title"
                              style={{
                                flex: 1,
                                textDecoration: done ? "line-through" : "none",
                                opacity: done ? 0.65 : 1,
                              }}
                            >
                              {t.title}
                            </span>
                            <span className={`badge ${done ? "good" : ""}`} style={{ fontSize: "0.75rem" }}>
                              {done ? "done" : t.status || "todo"}
                            </span>
                            {!isReviewer && (
                              <>
                                <button
                                  className="btn ghost"
                                  type="button"
                                  disabled={busy}
                                  onClick={() => startEditTask(t)}
                                  title="Edit task title"
                                >
                                  Edit
                                </button>
                                <button
                                  className="btn ghost"
                                  type="button"
                                  disabled={busy}
                                  onClick={() => deleteTask(t)}
                                  title="Delete task"
                                >
                                  Delete
                                </button>
                              </>
                            )}
                          </>
                        )}
                      </div>
                    );
                  })}
                </div>
              </CollapsibleTile>

              <CollapsibleTile
                title="MITRE / STRIDE"
                summary={maps.length ? `${maps.length} mapped` : "Collapsed · ATT&CK + STRIDE maps"}
                defaultOpen={false}
              >
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
                {!maps.length && <p className="muted" style={{ margin: 0 }}>No framework maps yet.</p>}
              </CollapsibleTile>

              <CollapsibleTile
                title="Diagrams"
                summary={diagram ? "Generated · ready to insert" : "Collapsed · attack / STRIDE / controls"}
                defaultOpen={false}
              >
                <div className="row" style={{ flexWrap: "wrap" }}>
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
                <p className="muted" style={{ margin: 0, fontSize: "0.82rem" }}>
                  Generated diagrams also open on the right <strong>Diagram</strong> tab.
                </p>
              </CollapsibleTile>

              <CollapsibleTile
                title="Citations"
                summary={
                  citations.length
                    ? `${citations.length} in library`
                    : "Collapsed · scholar search + manual cite"
                }
                defaultOpen={false}
              >
                <div className="panel stack" style={{ padding: "0.75rem" }}>
                  <strong>Scholar search</strong>
                  <p className="muted" style={{ margin: 0 }}>
                    Crossref + Semantic Scholar + OpenAlex + Google Scholar (SerpAPI key in Settings).
                    Month-level date range (Crossref/OpenAlex use exact months; S2/Google Scholar use years).
                    Tip: add domain words so results stay on-topic.
                  </p>
                  <div className="row">
                    <input
                      style={{ flex: 1 }}
                      value={scholarQ}
                      onChange={(e) => setScholarQ(e.target.value)}
                      placeholder="e.g. cybersecurity exposure management prioritization (add domain words)"
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
                  <div className="row" style={{ alignItems: "flex-end", flexWrap: "wrap" }}>
                    <label style={{ minWidth: 130 }}>
                      Published from
                      <input
                        type="month"
                        value={scholarYearFrom}
                        onChange={(e) => setScholarYearFrom(e.target.value)}
                        disabled={busy}
                        title="Earliest publication month (YYYY-MM)"
                      />
                    </label>
                    <label style={{ minWidth: 130 }}>
                      Published to
                      <input
                        type="month"
                        value={scholarYearTo}
                        onChange={(e) => setScholarYearTo(e.target.value)}
                        disabled={busy}
                        title="Latest publication month (YYYY-MM)"
                      />
                    </label>
                    <button className="btn ghost" type="button" disabled={busy} onClick={() => applyScholarYearPreset("6m")}>
                      6 mo
                    </button>
                    <button className="btn ghost" type="button" disabled={busy} onClick={() => applyScholarYearPreset("ytd")}>
                      YTD
                    </button>
                    <button className="btn ghost" type="button" disabled={busy} onClick={() => applyScholarYearPreset("1y")}>
                      1y
                    </button>
                    <button className="btn ghost" type="button" disabled={busy} onClick={() => applyScholarYearPreset("2y")}>
                      2y
                    </button>
                    <button className="btn ghost" type="button" disabled={busy} onClick={() => applyScholarYearPreset("3y")}>
                      3y
                    </button>
                    <button className="btn ghost" type="button" disabled={busy} onClick={() => applyScholarYearPreset("5y")}>
                      5y
                    </button>
                    <button className="btn ghost" type="button" disabled={busy} onClick={() => applyScholarYearPreset("10y")}>
                      10y
                    </button>
                    <button className="btn ghost" type="button" disabled={busy} onClick={() => applyScholarYearPreset("clear")}>
                      Any date
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
                  <strong>Manual citation</strong>
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
                {!citations.length && (
                  <p className="muted" style={{ margin: 0 }}>No citations in the project library yet.</p>
                )}
              </CollapsibleTile>

              <CollapsibleTile
                title="SaaS / control review"
                summary={controls.length ? `${controls.length} controls` : "Collapsed · control packs"}
                defaultOpen={false}
              >
                <p className="muted" style={{ margin: 0, fontSize: "0.82rem" }}>
                  Track vendor / SaaS control status against a pack. Expand only when you need it.
                </p>
                <form className="stack" onSubmit={addControl}>
                  <div className="row" style={{ flexWrap: "wrap" }}>
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
                {!controls.length && (
                  <p className="muted" style={{ margin: 0 }}>No controls logged yet.</p>
                )}
              </CollapsibleTile>

              <CollapsibleTile
                title="Peer review"
                summary={reviews.length ? `${reviews.length} reviews` : "Collapsed · comments"}
                defaultOpen={false}
              >
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
              </CollapsibleTile>

              {!isReviewer && (
                <CollapsibleTile
                  title="Artifacts"
                  summary={(() => {
                    const files = artifacts.filter((a) => (a.kind || "file") !== "url").length;
                    const links = artifacts.filter((a) => a.kind === "url").length;
                    if (!artifacts.length) return "Collapsed · files + saved URLs";
                    const bits = [];
                    if (files) bits.push(`${files} file${files === 1 ? "" : "s"}`);
                    if (links) bits.push(`${links} link${links === 1 ? "" : "s"}`);
                    return bits.join(" · ") || `${artifacts.length} item(s)`;
                  })()}
                  defaultOpen={false}
                >
                  <div className="stack">
                    <div className="stack" style={{ gap: "0.35rem" }}>
                      <strong style={{ fontSize: "0.9rem" }}>Upload file</strong>
                      <input type="file" onChange={uploadArtifact} disabled={busy} />
                    </div>
                    <form className="stack" onSubmit={saveArtifactUrl} style={{ gap: "0.35rem" }}>
                      <strong style={{ fontSize: "0.9rem" }}>Save URL to reference later</strong>
                      <input
                        type="url"
                        placeholder="https://…"
                        value={artifactUrl}
                        onChange={(e) => setArtifactUrl(e.target.value)}
                        disabled={busy}
                      />
                      <input
                        placeholder="Title (optional)"
                        value={artifactUrlTitle}
                        onChange={(e) => setArtifactUrlTitle(e.target.value)}
                        disabled={busy}
                      />
                      <input
                        placeholder="Note (optional)"
                        value={artifactUrlNote}
                        onChange={(e) => setArtifactUrlNote(e.target.value)}
                        disabled={busy}
                      />
                      <button className="btn" type="submit" disabled={busy || !artifactUrl.trim()}>
                        Save URL
                      </button>
                    </form>
                    {!artifacts.length && (
                      <p className="muted" style={{ margin: 0 }}>
                        No artifacts yet. Upload a file or save a URL for later reference.
                      </p>
                    )}
                    {!!artifacts.length && (
                      <div className="stack" style={{ gap: "0.45rem" }}>
                        {artifacts.map((a) => {
                          const isUrl = a.kind === "url" || !!a.source_url;
                          return (
                            <div
                              key={a.id}
                              className="row"
                              style={{
                                justifyContent: "space-between",
                                alignItems: "flex-start",
                                gap: "0.5rem",
                              }}
                            >
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div>
                                  <span className="badge">{isUrl ? "url" : "file"}</span>{" "}
                                  <strong style={{ fontSize: "0.9rem" }}>{a.original_name}</strong>
                                </div>
                                <div className="muted" style={{ fontSize: "0.8rem" }}>
                                  {isUrl
                                    ? a.source_url
                                    : `${a.size_bytes || 0} bytes`}
                                  {a.created_at ? ` · ${formatLocalDateTime(a.created_at)}` : ""}
                                </div>
                                {isUrl && a.notes ? (
                                  <div className="muted" style={{ fontSize: "0.8rem" }}>
                                    {a.notes}
                                  </div>
                                ) : null}
                              </div>
                              {isUrl && a.source_url ? (
                                <a
                                  className="btn ghost"
                                  href={a.source_url}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  Open
                                </a>
                              ) : (
                                <button
                                  className="btn ghost"
                                  type="button"
                                  disabled={busy}
                                  onClick={() => downloadArtifactFile(a)}
                                >
                                  Download
                                </button>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </CollapsibleTile>
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
                  {rightTab === "paper" && (
                    <HelpIcon label="Markdown formatting help" mark="MD" wide>
                      <MarkdownFormatHelp
                        canInsert={!isReviewer && !!activeSection}
                        onInsert={insertMarkdownSnippet}
                      />
                    </HelpIcon>
                  )}
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
                  {!isReviewer && (
                    <button
                      className="btn primary"
                      type="button"
                      disabled={busy || !activeSection}
                      onClick={() => exportDocx({ scope: "section", asDraft: true })}
                      title="Convert this section markdown to Word and download (no publish gate)"
                    >
                      Download Word
                    </button>
                  )}
                  {!isReviewer && (
                    <button
                      className="btn"
                      type="button"
                      disabled={busy}
                      onClick={() => exportDocx({ scope: "all", asDraft: true })}
                      title="Convert full paper markdown to Word and download (no publish gate)"
                    >
                      Download full paper
                    </button>
                  )}
                </div>
              </div>
              {rightTab === "paper" ? (
                <>
                  <textarea
                    ref={paperEditorRef}
                    style={{ minHeight: 560 }}
                    lang="en"
                    spellCheck
                    autoCorrect="on"
                    autoCapitalize="sentences"
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
                  {!isReviewer && (
                    <div className="panel stack spell-tools" style={{ padding: "0.65rem" }}>
                      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                        <div className="row" style={{ gap: "0.4rem", alignItems: "center" }}>
                          <strong>Spell check · find &amp; replace</strong>
                          <HelpIcon label="Spell check help">
                            <div>
                              <strong>Inline:</strong> red underlines while you type (browser spellcheck —
                              right‑click a word for suggestions). Needs English enabled in OS/browser.
                            </div>
                            <div style={{ marginTop: "0.35rem" }}>
                              <strong>Check all:</strong> scans the section with a local dictionary and
                              lists possible misspellings with clickable fixes.
                            </div>
                            <div style={{ marginTop: "0.35rem" }}>
                              Manual: double‑click a word → <strong>Use selection</strong> → type the fix →{" "}
                              <strong>Replace</strong> / <strong>Replace all</strong>.
                            </div>
                          </HelpIcon>
                        </div>
                      </div>
                      <div className="row" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
                        <label style={{ minWidth: 140, flex: 1 }}>
                          Find (flag a word)
                          <input
                            value={findText}
                            onChange={(e) => {
                              setFindText(e.target.value);
                              setFindMatchCount(null);
                            }}
                            placeholder="misspelled word"
                            disabled={busy}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                findNextInPaper();
                              }
                            }}
                          />
                        </label>
                        <label style={{ minWidth: 140, flex: 1 }}>
                          Replace with
                          <input
                            value={replaceText}
                            onChange={(e) => setReplaceText(e.target.value)}
                            placeholder="correct spelling"
                            disabled={busy}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                replaceSelectionOrNext();
                              }
                            }}
                          />
                        </label>
                        <button className="btn ghost" type="button" disabled={busy} onClick={useSelectionAsFind}>
                          Use selection
                        </button>
                        <button className="btn" type="button" disabled={busy || !findText} onClick={findNextInPaper}>
                          Find next
                        </button>
                        <button
                          className="btn"
                          type="button"
                          disabled={busy || !findText}
                          onClick={replaceSelectionOrNext}
                        >
                          Replace
                        </button>
                        <button
                          className="btn primary"
                          type="button"
                          disabled={busy || !findText}
                          onClick={replaceAllInPaper}
                        >
                          Replace all
                        </button>
                        <button className="btn ghost" type="button" disabled={busy || !findText} onClick={countPaperMatches}>
                          Count
                        </button>
                        <button
                          className="btn primary"
                          type="button"
                          disabled={busy || !activeSection}
                          onClick={checkAllSpelling}
                          title="Scan this section with the local English dictionary"
                        >
                          {busyLabel?.includes("Spell check") ? "Checking…" : "Check all"}
                        </button>
                      </div>
                      <div className="row" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
                        <label className="row" style={{ gap: "0.35rem", alignItems: "center" }}>
                          <input
                            type="checkbox"
                            checked={findWholeWord}
                            onChange={(e) => setFindWholeWord(e.target.checked)}
                          />
                          Whole word
                        </label>
                        <label className="row" style={{ gap: "0.35rem", alignItems: "center" }}>
                          <input
                            type="checkbox"
                            checked={findCaseSensitive}
                            onChange={(e) => setFindCaseSensitive(e.target.checked)}
                          />
                          Match case
                        </label>
                        {findMatchCount != null && (
                          <span className="badge">{findMatchCount} match(es) in this section</span>
                        )}
                      </div>
                      {spellMessage && (
                        <p className="muted" style={{ margin: 0, fontSize: "0.85rem" }}>
                          {spellMessage}{" "}
                          <span className="muted">(inline red underlines = browser spellcheck while you type)</span>
                        </p>
                      )}
                      {!!spellIssues.length && (
                        <div className="spell-issue-list stack" style={{ gap: "0.35rem", maxHeight: 220, overflow: "auto" }}>
                          {spellIssues.map((issue) => (
                            <div
                              key={issue.normalized || issue.word}
                              className="row"
                              style={{
                                justifyContent: "space-between",
                                alignItems: "center",
                                flexWrap: "wrap",
                                gap: "0.35rem",
                                borderBottom: "1px solid var(--border)",
                                paddingBottom: "0.3rem",
                              }}
                            >
                              <div>
                                <strong>{issue.word}</strong>
                                <span className="muted" style={{ marginLeft: "0.4rem", fontSize: "0.8rem" }}>
                                  ×{issue.count}
                                </span>
                              </div>
                              <div className="row" style={{ flexWrap: "wrap", gap: "0.25rem" }}>
                                {(issue.suggestions || []).length ? (
                                  (issue.suggestions || []).slice(0, 4).map((sug) => (
                                    <button
                                      key={`${issue.normalized}-${sug}`}
                                      className="btn ghost"
                                      type="button"
                                      style={{ padding: "0.15rem 0.45rem", fontSize: "0.78rem" }}
                                      disabled={busy}
                                      onClick={() => applySpellIssue(issue, sug)}
                                      title={`Replace with ${sug}`}
                                    >
                                      {sug}
                                    </button>
                                  ))
                                ) : (
                                  <button
                                    className="btn ghost"
                                    type="button"
                                    style={{ padding: "0.15rem 0.45rem", fontSize: "0.78rem" }}
                                    disabled={busy}
                                    onClick={() => applySpellIssue(issue, "")}
                                  >
                                    Flag only
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  <div className="row" style={{ justifyContent: "flex-end", alignItems: "center", gap: "0.35rem" }}>
                    <HelpIcon label="Paper editor help" wide>
                      <div>Autosaves ~3s after you pause typing; also on blur and Save now.</div>
                      <div style={{ marginTop: "0.35rem" }}>
                        <strong>Download Word</strong> converts this section markdown → .docx.{" "}
                        <strong>Download full paper</strong> joins all sections.
                      </div>
                      <div style={{ marginTop: "0.35rem" }}>
                        Spell tools sit under the editor: red underlines + find/replace.
                      </div>
                      <div style={{ marginTop: "0.55rem" }}>
                        <MarkdownFormatHelp
                          canInsert={!isReviewer && !!activeSection}
                          onInsert={insertMarkdownSnippet}
                        />
                      </div>
                    </HelpIcon>
                  </div>
                  <div className="panel stack" style={{ padding: "0.65rem" }}>
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <div className="row" style={{ gap: "0.4rem", alignItems: "center" }}>
                        <strong>Paper releases (Commit / Primary)</strong>
                        <HelpIcon label="Paper releases help">
                          <div>
                            Working <strong>v{project?.working_version || "0.1.1"}</strong>
                            {project?.primary_version ? (
                              <>
                                {" "}
                                · Primary <strong>v{project.primary_version}</strong>
                              </>
                            ) : (
                              " · no primary yet"
                            )}
                            .
                          </div>
                          <div style={{ marginTop: "0.35rem" }}>
                            Save never bumps version. <strong>Commit</strong> freezes a snapshot then
                            patches (0.1.1…0.1.19). <strong>Publish primary</strong> freezes official
                            major.0.0 and starts the next workline (1.1.1).
                          </div>
                          <div style={{ marginTop: "0.35rem" }}>
                            No commits yet? Hit <strong>Commit</strong> in the header when you want an
                            official working snapshot.
                          </div>
                          <div style={{ marginTop: "0.35rem" }}>
                            Pick two releases (left/right) and open <strong>Diff in new tab</strong> for
                            red/green changes.
                          </div>
                        </HelpIcon>
                      </div>
                      <div className="row">
                        <button
                          className="btn primary"
                          type="button"
                          disabled={busy || paperReleases.length < 2}
                          onClick={() => openVersionDiffTab()}
                          title="Open red/green diff of two saved versions in a new browser tab"
                        >
                          Diff in new tab
                        </button>
                        <button className="btn ghost" type="button" onClick={loadPaperReleases} disabled={busy}>
                          Refresh
                        </button>
                      </div>
                    </div>
                    <div className="row" style={{ gap: "0.35rem", flexWrap: "wrap" }}>
                      <span className="badge good">Working v{project?.working_version || "0.1.1"}</span>
                      {project?.primary_version ? (
                        <span className="badge">Primary v{project.primary_version}</span>
                      ) : (
                        <span className="muted" style={{ fontSize: "0.85rem" }}>
                          No primary yet
                        </span>
                      )}
                    </div>
                    {paperReleases.length >= 2 && (
                      <div className="row" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
                        <label style={{ minWidth: 160, flex: 1 }}>
                          Diff left (base)
                          <select
                            value={diffLeftId}
                            onChange={(e) => setDiffLeftId(e.target.value)}
                            disabled={busy}
                          >
                            <option value="">— choose —</option>
                            {paperReleases.map((r) => (
                              <option key={`L-${r.id}`} value={r.id}>
                                v{r.version_label} · {r.kind}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label style={{ minWidth: 160, flex: 1 }}>
                          Diff right (newer)
                          <select
                            value={diffRightId}
                            onChange={(e) => setDiffRightId(e.target.value)}
                            disabled={busy}
                          >
                            <option value="">— choose —</option>
                            {paperReleases.map((r) => (
                              <option key={`R-${r.id}`} value={r.id}>
                                v{r.version_label} · {r.kind}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button
                          className="btn"
                          type="button"
                          disabled={busy || !diffLeftId || !diffRightId}
                          onClick={() => openVersionDiffTab()}
                        >
                          Open diff
                        </button>
                      </div>
                    )}
                    {!paperReleases.length && (
                      <p className="muted row" style={{ margin: 0, alignItems: "center", gap: "0.4rem" }}>
                        <span>No commits yet</span>
                        <HelpIcon label="How to create a commit">
                          Hit <strong>Commit</strong> in the header when you want an official working
                          snapshot. That freezes the full paper and bumps the patch version (for example
                          0.1.1 → 0.1.2). Save alone does not create a release.
                        </HelpIcon>
                      </p>
                    )}
                    {paperReleases.map((r) => (
                      <div
                        key={r.id}
                        className="row"
                        style={{
                          justifyContent: "space-between",
                          alignItems: "flex-start",
                          gap: "0.5rem",
                          borderBottom: "1px solid var(--border)",
                          paddingBottom: "0.35rem",
                        }}
                      >
                        <div style={{ flex: 1 }}>
                          <div className="row" style={{ gap: "0.35rem", flexWrap: "wrap" }}>
                            <span className={`badge ${r.kind === "primary" ? "good" : ""}`}>
                              v{r.version_label}
                            </span>
                            <span className="badge">{r.kind}</span>
                            <span className="muted" style={{ fontSize: "0.78rem" }}>
                              {r.section_count} sections · {r.char_count} chars
                              {r.created_at ? ` · ${formatLocalDateTime(r.created_at)}` : ""}
                            </span>
                          </div>
                          {r.note && (
                            <div className="muted" style={{ fontSize: "0.82rem", marginTop: "0.2rem" }}>
                              {r.note}
                            </div>
                          )}
                        </div>
                        <div className="row">
                          <button
                            className="btn ghost"
                            type="button"
                            disabled={busy}
                            title="Use as left side of diff"
                            onClick={() => setDiffLeftId(String(r.id))}
                          >
                            As left
                          </button>
                          <button
                            className="btn ghost"
                            type="button"
                            disabled={busy}
                            title="Use as right side of diff"
                            onClick={() => setDiffRightId(String(r.id))}
                          >
                            As right
                          </button>
                          {!isReviewer && (
                            <button
                              className="btn ghost"
                              type="button"
                              disabled={busy}
                              onClick={() => restorePaperRelease(r.id, r.version_label)}
                            >
                              Restore
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  {!isReviewer && (
                    <div className="panel stack" style={{ padding: "0.65rem" }}>
                      <div className="row" style={{ justifyContent: "space-between" }}>
                        <strong>Section autosave snippets</strong>
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
                        Light per-section history (before save / restore). Does not change version
                        numbers. Latest five stay in view; scroll for older snippets.
                      </p>
                      {!sectionVersions.length && (
                        <p className="muted" style={{ margin: 0 }}>
                          No versions yet. Edit and save to create snippets.
                        </p>
                      )}
                      {!!sectionVersions.length && (
                        <div
                          className="stack"
                          style={{
                            maxHeight: "17.5rem",
                            overflowY: "auto",
                            paddingRight: "0.15rem",
                            borderTop: "1px solid rgba(255,255,255,0.06)",
                          }}
                          title="Scroll for older autosave snippets"
                        >
                          {sectionVersions.map((v) => (
                            <div
                              key={v.id}
                              className="row"
                              style={{
                                justifyContent: "space-between",
                                alignItems: "flex-start",
                                flexShrink: 0,
                              }}
                            >
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div>
                                  <span className="badge">{v.label}</span>{" "}
                                  <span className="muted" style={{ fontSize: "0.8rem" }}>
                                    {v.char_count} chars
                                    {v.created_at
                                      ? ` · ${formatLocalDateTime(v.created_at)}`
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
