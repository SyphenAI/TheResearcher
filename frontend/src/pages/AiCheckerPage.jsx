import React, { useEffect, useRef, useState } from "react";
import { api } from "../api/client";

export default function AiCheckerPage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [formats, setFormats] = useState([]);
  const [formatNotes, setFormatNotes] = useState([]);
  const [sourceName, setSourceName] = useState("");
  const fileRef = useRef(null);

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

  async function runCheck() {
    setBusy(true);
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
      await loadHistory();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function humanizeThenCheck() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const rewritten = await api("/api/research/rewrite", {
        method: "POST",
        body: JSON.stringify({ text, strength: "high" }),
      });
      setText(rewritten.content);
      const res = await api("/api/research/ai-check", {
        method: "POST",
        body: JSON.stringify({ text: rewritten.content, source_label: "after-humanize" }),
      });
      setResult(res);
      await loadHistory();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function loadFileIntoEditor(file) {
    if (!file) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const form = new FormData();
      form.append("file", file);
      const extracted = await api("/api/research/extract-text", {
        method: "POST",
        body: form,
      });
      setText(extracted.text || "");
      setSourceName(extracted.filename || file.name);
      setMessage(
        `Loaded ${extracted.filename} (${extracted.char_count} chars` +
          `${extracted.truncated ? ", truncated" : ""}). Review text, then run AI check.`
      );
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function checkFileDirect(file) {
    if (!file) return;
    setBusy(true);
    setError("");
    setMessage("");
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
          `${res.truncated ? " (truncated for size)" : ""}.`
      );
      await loadHistory();
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function onFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    // Default path: extract into editor so researcher can review before scoring.
    loadFileIntoEditor(file);
  }

  const accept = formats.length
    ? formats.join(",")
    : ".pdf,.docx,.pptx,.odt,.txt,.md,.csv,.html,.htm,.rtf,.json,.log";

  return (
    <div className="stack">
      <div>
        <h1>AI Checker</h1>
        <p className="muted">
          Local heuristic scan for AI-like writing. Paste text or upload PDF, Word, and other common formats.
        </p>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}

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
        {sourceName && (
          <div className="badge">Source: {sourceName}</div>
        )}
      </div>

      <div className="panel stack">
        <label>
          Content to evaluate
          <textarea
            style={{ minHeight: 260 }}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste research text here, or upload a document above"
          />
        </label>
        <div className="row">
          <button className="btn primary" onClick={runCheck} disabled={busy || !text.trim()}>
            Run AI check
          </button>
          <button className="btn" onClick={humanizeThenCheck} disabled={busy || !text.trim()}>
            Humanize + recheck
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
