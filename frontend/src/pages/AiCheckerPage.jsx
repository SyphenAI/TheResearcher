import React, { useEffect, useRef, useState } from "react";
import { api, getToken } from "../api/client";
import TextDiffPanes from "../components/TextDiffPanes";

function slugName(name) {
  const base = (name || "ai-check")
    .replace(/\.[^.]+$/, "")
    .replace(/[^\w\-]+/g, "_")
    .replace(/_+/g, "_")
    .slice(0, 48);
  return base || "ai-check";
}

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function downloadText(filename, content, mime = "text/plain;charset=utf-8") {
  downloadBlob(filename, new Blob([content], { type: mime }));
}

export default function AiCheckerPage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState("");
  const [formats, setFormats] = useState([]);
  const [formatNotes, setFormatNotes] = useState([]);
  const [sourceName, setSourceName] = useState("");
  /** Side-by-side original vs humanized after Humanize + recheck */
  const [compare, setCompare] = useState(null);
  const [projects, setProjects] = useState([]);
  const [artifactProjectId, setArtifactProjectId] = useState("");
  const [keptVersion, setKeptVersion] = useState(null); // "humanized" | "original" | null
  const fileRef = useRef(null);
  const compareRef = useRef(null);
  const editorRef = useRef(null);
  const actionsRef = useRef(null);

  async function loadHistory() {
    const rows = await api("/api/research/ai-check/history");
    setHistory(rows);
  }

  async function deleteHistoryItem(id) {
    if (!id) return;
    setError("");
    try {
      await api(`/api/research/ai-check/history/${id}`, { method: "DELETE" });
      setHistory((prev) => prev.filter((h) => h.id !== id));
      setMessage(`Deleted check #${id}.`);
    } catch (e) {
      setError(e.message || "Could not delete check.");
    }
  }

  async function clearAllHistory() {
    if (!history.length) return;
    const ok = window.confirm(
      `Clear all ${history.length} recent AI checks? This cannot be undone.`
    );
    if (!ok) return;
    setError("");
    setBusy(true);
    setBusyLabel("Clearing history…");
    try {
      const res = await api("/api/research/ai-check/history", { method: "DELETE" });
      setHistory([]);
      setMessage(`Cleared ${res?.deleted ?? "all"} recent checks.`);
    } catch (e) {
      setError(e.message || "Could not clear history.");
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }

  useEffect(() => {
    loadHistory().catch(() => {});
    api("/api/research/extract/formats")
      .then((data) => {
        setFormats(data.extensions || []);
        setFormatNotes(data.notes || []);
      })
      .catch(() => {});
    api("/api/projects")
      .then((rows) => {
        setProjects(Array.isArray(rows) ? rows : []);
        if (rows?.length && !artifactProjectId) {
          setArtifactProjectId(String(rows[0].id));
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (compare && compareRef.current) {
      compareRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [compare]);

  async function runCheck() {
    setBusy(true);
    setBusyLabel("Checking…");
    setError("");
    setMessage("");
    try {
      const res = await api("/api/research/ai-check", {
        method: "POST",
        body: JSON.stringify({
          text,
          source_label: sourceName ? `text:${sourceName}` : "dashboard-paste",
        }),
      });
      setResult(res);
      setMessage(`AI likelihood ${res.ai_pct}% · human ${res.human_pct}%.`);
      await loadHistory();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }

  async function humanizeThenCheck() {
    const original = text;
    if (!original.trim()) {
      setError("Paste or load text first.");
      return;
    }

    setBusy(true);
    setBusyLabel("Humanizing…");
    setError("");
    setMessage("");
    setKeptVersion(null);
    try {
      const before = await api("/api/research/ai-check", {
        method: "POST",
        body: JSON.stringify({
          text: original,
          source_label: sourceName ? `before-humanize:${sourceName}` : "before-humanize",
        }),
      });

      setBusyLabel("Rewriting…");
      const rewritten = await api("/api/research/rewrite", {
        method: "POST",
        body: JSON.stringify({ text: original, strength: "high" }),
      });
      const humanized = rewritten.content || "";
      if (!humanized.trim()) {
        throw new Error("Rewrite returned empty text.");
      }

      setBusyLabel("Rechecking…");
      const after = await api("/api/research/ai-check", {
        method: "POST",
        body: JSON.stringify({ text: humanized, source_label: "after-humanize" }),
      });

      // Keep original in the main editor until user chooses Keep or Restore.
      // Proposed lives in the compare panel so Keep has a visible effect.
      setCompare({
        original,
        humanized,
        before,
        after,
        provider: rewritten.provider || null,
        used_live: !!rewritten.used_live,
        original_len: rewritten.original_len ?? original.length,
        rewritten_len: rewritten.rewritten_len ?? humanized.length,
      });
      setResult(after);

      const delta = Number((before.ai_pct - after.ai_pct).toFixed(1));
      const via = rewritten.used_live
        ? `via ${rewritten.provider || "live model"}`
        : "via local rewrite";
      const deltaText =
        delta > 0
          ? `AI likelihood dropped ${delta} points (${before.ai_pct}% → ${after.ai_pct}%).`
          : delta < 0
            ? `AI likelihood rose ${Math.abs(delta)} points (${before.ai_pct}% → ${after.ai_pct}%).`
            : `AI likelihood unchanged at ${after.ai_pct}%.`;
      setMessage(
        `Humanize draft ready ${via}. ${deltaText} Review the red/green diff, then Keep humanized or Restore original.`
      );
      await loadHistory();
    } catch (e) {
      setError(e.message || "Humanize + recheck failed.");
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }

  async function useHumanized() {
    if (!compare) return;
    setBusy(true);
    setBusyLabel("Applying humanized…");
    setError("");
    try {
      const finalText = compare.humanized || "";
      // Recheck so the score matches whatever is in the proposed pane (including edits).
      const finalResult = await api("/api/research/ai-check", {
        method: "POST",
        body: JSON.stringify({ text: finalText, source_label: "kept-humanized" }),
      });
      setText(finalText);
      setResult(finalResult);
      setCompare(null);
      setKeptVersion("humanized");
      setSourceName((n) => (n && !n.includes("humanized") ? `${n} (humanized)` : n || "humanized"));
      setMessage(
        `Kept humanized version in the editor (AI ${finalResult.ai_pct}%). ` +
          `You can Export or Add to project artifacts below.`
      );
      await loadHistory();
      requestAnimationFrame(() => {
        editorRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        editorRef.current?.focus?.();
        actionsRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    } catch (e) {
      setError(e.message || "Could not keep humanized text.");
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }

  function restoreOriginal() {
    if (!compare) return;
    setText(compare.original);
    setResult(compare.before);
    setCompare(null);
    setKeptVersion("original");
    setMessage("Restored original text into the editor. Humanize draft discarded.");
    requestAnimationFrame(() => {
      editorRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  function clearCompare() {
    setCompare(null);
    setMessage("Compare dismissed. Editor text was not changed by Dismiss.");
  }

  async function loadFileIntoEditor(file) {
    if (!file) return;
    setBusy(true);
    setBusyLabel("Loading file…");
    setError("");
    setMessage("");
    setCompare(null);
    setKeptVersion(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const extracted = await api("/api/research/extract-text", {
        method: "POST",
        body: form,
      });
      setText(extracted.text || "");
      setSourceName(extracted.filename || file.name);
      setResult(null);
      setMessage(
        `Loaded ${extracted.filename} (${extracted.char_count} chars` +
          `${extracted.truncated ? ", truncated" : ""}). Review text, then run AI check.`
      );
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }

  async function checkFileDirect(file) {
    if (!file) return;
    setBusy(true);
    setBusyLabel("Checking file…");
    setError("");
    setMessage("");
    setCompare(null);
    setKeptVersion(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api("/api/research/ai-check/upload", {
        method: "POST",
        body: form,
      });
      if (res.extracted_text) {
        setText(res.extracted_text);
      }
      setSourceName(res.filename || file.name);
      setResult(res);
      setMessage(
        `Checked ${res.filename || file.name}` +
          `${res.char_count != null ? ` (${res.char_count} chars)` : ""}` +
          `${res.truncated ? " (truncated for size)" : ""}. AI likelihood ${res.ai_pct}%.`
      );
      await loadHistory();
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }

  function onFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    loadFileIntoEditor(file);
  }

  function exportBaseName() {
    return slugName(sourceName || "ai-check-export");
  }

  function exportTxt() {
    if (!text.trim()) {
      setError("Nothing to export.");
      return;
    }
    downloadText(`${exportBaseName()}.txt`, text, "text/plain;charset=utf-8");
    setMessage(`Downloaded ${exportBaseName()}.txt`);
  }

  function exportMd() {
    if (!text.trim()) {
      setError("Nothing to export.");
      return;
    }
    const meta = result
      ? `\n\n---\n\n_AI likelihood ${result.ai_pct}% · human ${result.human_pct}% · source: ${sourceName || "paste"}_\n`
      : "";
    downloadText(`${exportBaseName()}.md`, text + meta, "text/markdown;charset=utf-8");
    setMessage(`Downloaded ${exportBaseName()}.md`);
  }

  async function exportDocx() {
    if (!text.trim()) {
      setError("Nothing to export.");
      return;
    }
    setBusy(true);
    setBusyLabel("Exporting Word…");
    setError("");
    try {
      const title = sourceName ? slugName(sourceName).replace(/_/g, " ") : "AI Checker export";
      const res = await fetch("/api/research/export/docx", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          title,
          content_md: text,
          force: true,
        }),
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const data = await res.json();
          detail =
            typeof data.detail === "string"
              ? data.detail
              : data.detail?.message || JSON.stringify(data.detail || data);
        } catch {
          /* ignore */
        }
        throw new Error(detail || "Export failed");
      }
      const blob = await res.blob();
      downloadBlob(`${exportBaseName()}.docx`, blob);
      setMessage(`Downloaded ${exportBaseName()}.docx`);
    } catch (e) {
      setError(e.message || "Word export failed.");
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }

  async function addToProjectArtifacts() {
    if (!text.trim()) {
      setError("Nothing to save.");
      return;
    }
    if (!artifactProjectId) {
      setError("Choose a project first.");
      return;
    }
    setBusy(true);
    setBusyLabel("Saving artifact…");
    setError("");
    try {
      const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      const filename = `${exportBaseName()}-humanized-${stamp}.md`;
      const header =
        `# ${sourceName || "AI Checker export"}\n\n` +
        (result
          ? `_AI likelihood ${result.ai_pct}% · human ${result.human_pct}% · saved ${stamp}_\n\n`
          : "") +
        `---\n\n`;
      const blob = new Blob([header + text], { type: "text/markdown;charset=utf-8" });
      const form = new FormData();
      form.append("file", blob, filename);
      const art = await api(`/api/research/projects/${artifactProjectId}/artifacts`, {
        method: "POST",
        body: form,
      });
      const project = projects.find((p) => String(p.id) === String(artifactProjectId));
      setMessage(
        `Saved artifact "${art.original_name || filename}" on project ` +
          `"${project?.title || artifactProjectId}". Open that project desk to see it under Artifacts.`
      );
    } catch (e) {
      setError(e.message || "Could not save to project artifacts.");
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }

  const accept = formats.length
    ? formats.join(",")
    : ".pdf,.docx,.pptx,.odt,.txt,.md,.csv,.html,.htm,.rtf,.json,.log";

  const scoreDelta =
    compare && compare.before && compare.after
      ? Number((compare.before.ai_pct - compare.after.ai_pct).toFixed(1))
      : null;

  return (
    <div className="stack">
      <div>
        <h1>AI Checker</h1>
        <p className="muted">
          Two steps: <strong>Run AI check</strong> scores the text; <strong>Humanize + recheck</strong> drafts a
          rewrite and shows a red/green side-by-side. Keep or restore, then export or attach to a project.
        </p>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}
      {busy && busyLabel && (
        <div className="alert ok" role="status">
          {busyLabel}
        </div>
      )}
      {keptVersion && !compare && (
        <div className="badge good">
          Active editor version: {keptVersion === "humanized" ? "Humanized" : "Original"}
        </div>
      )}

      <div className="panel stack">
        <h2 style={{ margin: 0 }}>Upload document</h2>
        <p className="muted" style={{ margin: 0 }}>
          Supported: {formats.length ? formats.join(", ") : "pdf, docx, pptx, odt, txt, md, csv, html, rtf, json"}.
          Legacy .doc is not supported (save as .docx). Scanned PDFs need OCR first.
        </p>
        {!!formatNotes.length && (
          <ul className="muted" style={{ margin: 0 }}>
            {formatNotes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        )}
        <label>
          Choose file
          <input
            ref={fileRef}
            type="file"
            accept={accept}
            onChange={onFileChange}
            disabled={busy}
          />
        </label>
        <div className="row">
          <button
            className="btn"
            type="button"
            disabled={busy}
            onClick={() => {
              const file = fileRef.current?.files?.[0];
              if (!file) {
                setError("Choose a file first.");
                return;
              }
              loadFileIntoEditor(file);
            }}
          >
            Load into editor
          </button>
          <button
            className="btn primary"
            type="button"
            disabled={busy}
            onClick={() => {
              const file = fileRef.current?.files?.[0];
              if (!file) {
                setError("Choose a file first.");
                return;
              }
              checkFileDirect(file);
            }}
          >
            Check file now
          </button>
        </div>
        {sourceName && <div className="badge">Source: {sourceName}</div>}
      </div>

      <div className="panel stack" ref={editorRef}>
        <label>
          Content to evaluate
          <textarea
            style={{ minHeight: 220 }}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setKeptVersion(null);
            }}
            placeholder="Paste research text here, or upload a document above"
            disabled={busy}
          />
        </label>
        <div className="row">
          <button className="btn primary" onClick={runCheck} disabled={busy || !text.trim()}>
            {busy && busyLabel.includes("Check") ? busyLabel : "1. Run AI check"}
          </button>
          <button className="btn" onClick={humanizeThenCheck} disabled={busy || !text.trim()}>
            {busy &&
            (busyLabel.includes("Humaniz") ||
              busyLabel.includes("Rewrit") ||
              busyLabel.includes("Recheck"))
              ? busyLabel
              : "2. Humanize + recheck"}
          </button>
        </div>
      </div>

      {compare && (
        <div className="panel stack" ref={compareRef}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>Side-by-side compare</h2>
            <div className="row">
              <button className="btn" type="button" onClick={restoreOriginal} disabled={busy}>
                Restore original
              </button>
              <button className="btn primary" type="button" onClick={useHumanized} disabled={busy}>
                {busy && busyLabel.includes("Applying") ? busyLabel : "Keep humanized"}
              </button>
              <button className="btn" type="button" onClick={clearCompare} disabled={busy}>
                Dismiss compare
              </button>
            </div>
          </div>
          <p className="muted" style={{ margin: 0 }}>
            {compare.used_live
              ? `Rewrite used live model (${compare.provider || "provider"}).`
              : "Rewrite used local rules only (no live model)."}{" "}
            Length {compare.original_len} → {compare.rewritten_len} chars.{" "}
            <strong>Keep humanized</strong> loads the proposed text into the editor and closes this panel.
          </p>

          <div className="grid-3">
            <div className="metric">
              <span className="muted">Before (AI %)</span>
              <strong className={compare.before.ai_pct >= 10 ? "badge bad" : "badge good"}>
                {compare.before.ai_pct}%
              </strong>
            </div>
            <div className="metric">
              <span className="muted">After (AI %)</span>
              <strong className={compare.after.ai_pct >= 10 ? "badge bad" : "badge good"}>
                {compare.after.ai_pct}%
              </strong>
            </div>
            <div className="metric">
              <span className="muted">Delta</span>
              <strong style={{ fontSize: "1rem" }}>
                {scoreDelta == null
                  ? "—"
                  : scoreDelta > 0
                    ? `↓ ${scoreDelta} pts (better)`
                    : scoreDelta < 0
                      ? `↑ ${Math.abs(scoreDelta)} pts (worse)`
                      : "No change"}
              </strong>
            </div>
          </div>

          <TextDiffPanes
            original={compare.original}
            proposed={compare.humanized}
            originalLabel="Original"
            proposedLabel="Humanized (editable)"
            editableProposed
            onProposedChange={(next) => {
              setCompare((c) => (c ? { ...c, humanized: next } : c));
            }}
          />
        </div>
      )}

      <div className="panel stack" ref={actionsRef}>
        <h2 style={{ margin: 0 }}>Export & project artifacts</h2>
        <p className="muted" style={{ margin: 0 }}>
          Download the current editor text, or attach it as a markdown artifact on a research project.
        </p>
        <div className="row">
          <button className="btn" type="button" onClick={exportTxt} disabled={busy || !text.trim()}>
            Export .txt
          </button>
          <button className="btn" type="button" onClick={exportMd} disabled={busy || !text.trim()}>
            Export .md
          </button>
          <button className="btn" type="button" onClick={exportDocx} disabled={busy || !text.trim()}>
            Export .docx
          </button>
        </div>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label style={{ minWidth: 220, flex: 1 }}>
            Project for artifact
            <select
              value={artifactProjectId}
              onChange={(e) => setArtifactProjectId(e.target.value)}
              disabled={busy || !projects.length}
            >
              {!projects.length && <option value="">No projects yet</option>}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn primary"
            type="button"
            onClick={addToProjectArtifacts}
            disabled={busy || !text.trim() || !artifactProjectId}
          >
            Add to project artifacts
          </button>
        </div>
      </div>

      {result && (
        <div className="grid-3">
          <div className="metric">
            <span className="muted">AI likelihood</span>
            <strong className={result.ai_pct >= 10 ? "badge bad" : "badge good"}>
              {result.ai_pct}%
            </strong>
          </div>
          <div className="metric">
            <span className="muted">Human likelihood</span>
            <strong>{result.human_pct}%</strong>
          </div>
          <div className="metric">
            <span className="muted">Publish bar</span>
            <strong style={{ fontSize: "1rem" }}>
              {result.ai_pct < 10 ? "Under 10% target" : "Needs more human edit"}
            </strong>
          </div>
          <div className="panel" style={{ gridColumn: "1 / -1" }}>
            <h3>Signals</h3>
            <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--mono)", fontSize: "0.85rem" }}>
              {JSON.stringify(result.signals, null, 2)}
            </pre>
            <h3>Recommendations</h3>
            <ul>
              {(result.recommendations || []).map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <div className="panel stack">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>Recent checks</h2>
          <button
            className="btn"
            type="button"
            disabled={busy || !history.length}
            onClick={clearAllHistory}
            title="Remove all stored AI check history"
          >
            Clear all
          </button>
        </div>
        <p className="muted" style={{ margin: 0 }}>
          History is local. Delete single rows or clear all when the list gets long.
        </p>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Source</th>
              <th>AI %</th>
              <th>Human %</th>
              <th>When</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {history.map((h) => (
              <tr key={h.id}>
                <td>{h.id}</td>
                <td>{h.source_label}</td>
                <td>{h.ai_pct}</td>
                <td>{h.human_pct}</td>
                <td className="muted">{h.created_at}</td>
                <td>
                  <button
                    className="btn ghost"
                    type="button"
                    disabled={busy}
                    onClick={() => deleteHistoryItem(h.id)}
                    title={`Delete check #${h.id}`}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {!history.length && (
              <tr>
                <td colSpan={6} className="muted">
                  No checks yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
