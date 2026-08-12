import React, { useEffect, useRef, useState } from "react";
import { api } from "../api/client";

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
  const fileRef = useRef(null);
  const compareRef = useRef(null);

  async function loadHistory() {
    const rows = await api("/api/research/ai-check/history");
    setHistory(rows);
  }

  useEffect(() => {
    loadHistory().catch(() => {});
    api("/api/research/extract/formats")
      .then((data) => {
        setFormats(data.extensions || []);
        setFormatNotes(data.notes || []);
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
    try {
      // Baseline score on the current text (even if we already have a result).
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

      setText(humanized);
      setResult(after);
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
      setMessage(`Humanize complete ${via}. ${deltaText} Side-by-side compare is below.`);
      await loadHistory();
    } catch (e) {
      setError(e.message || "Humanize + recheck failed.");
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }

  function useHumanized() {
    if (!compare) return;
    setText(compare.humanized);
    setResult(compare.after);
    setMessage("Editor set to humanized version. Edit further in your own voice before publish.");
  }

  function restoreOriginal() {
    if (!compare) return;
    setText(compare.original);
    setResult(compare.before);
    setMessage("Restored original text into the editor.");
  }

  function clearCompare() {
    setCompare(null);
  }

  async function loadFileIntoEditor(file) {
    if (!file) return;
    setBusy(true);
    setBusyLabel("Loading file…");
    setError("");
    setMessage("");
    setCompare(null);
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
          Local heuristic scan for AI-like writing. Paste text or upload PDF, Word, and other common formats.
          Humanize shows a side-by-side original vs rewrite so you can see what changed.
        </p>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}
      {busy && busyLabel && (
        <div className="alert ok" role="status">
          {busyLabel}
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

      <div className="panel stack">
        <label>
          Content to evaluate
          <textarea
            style={{ minHeight: 220 }}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste research text here, or upload a document above"
            disabled={busy}
          />
        </label>
        <div className="row">
          <button className="btn primary" onClick={runCheck} disabled={busy || !text.trim()}>
            {busy && busyLabel.includes("Check") ? busyLabel : "Run AI check"}
          </button>
          <button className="btn" onClick={humanizeThenCheck} disabled={busy || !text.trim()}>
            {busy && (busyLabel.includes("Humaniz") || busyLabel.includes("Rewrit") || busyLabel.includes("Recheck"))
              ? busyLabel
              : "Humanize + recheck"}
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
                Keep humanized
              </button>
              <button className="btn" type="button" onClick={clearCompare} disabled={busy}>
                Dismiss
              </button>
            </div>
          </div>
          <p className="muted" style={{ margin: 0 }}>
            {compare.used_live
              ? `Rewrite used live model (${compare.provider || "provider"}).`
              : "Rewrite used local rules only (no live model)."}{" "}
            Length {compare.original_len} → {compare.rewritten_len} chars.
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

          <div className="grid-2 equal">
            <div className="stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <strong>Original</strong>
                <span className="muted">{compare.original.length} chars</span>
              </div>
              <textarea
                readOnly
                value={compare.original}
                style={{ minHeight: 280, fontFamily: "var(--mono)", fontSize: "0.85rem" }}
              />
            </div>
            <div className="stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <strong>Humanized</strong>
                <span className="muted">{compare.humanized.length} chars</span>
              </div>
              <textarea
                value={compare.humanized}
                onChange={(e) => {
                  const next = e.target.value;
                  setCompare((c) => (c ? { ...c, humanized: next } : c));
                  setText(next);
                }}
                style={{ minHeight: 280, fontFamily: "var(--mono)", fontSize: "0.85rem" }}
                disabled={busy}
              />
              <p className="muted" style={{ margin: 0 }}>
                Edit the humanized side freely. Edits sync into the main editor.
              </p>
            </div>
          </div>
        </div>
      )}

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

      <div className="panel">
        <h2>Recent checks</h2>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Source</th>
              <th>AI %</th>
              <th>Human %</th>
              <th>When</th>
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
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
