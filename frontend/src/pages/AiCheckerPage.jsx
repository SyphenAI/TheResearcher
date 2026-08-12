import React, { useEffect, useState } from "react";
import { api } from "../api/client";

export default function AiCheckerPage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadHistory() {
    const rows = await api("/api/research/ai-check/history");
    setHistory(rows);
  }

  useEffect(() => {
    loadHistory().catch(() => {});
  }, []);

  async function runCheck() {
    setBusy(true);
    setError("");
    try {
      const res = await api("/api/research/ai-check", {
        method: "POST",
        body: JSON.stringify({ text, source_label: "dashboard-paste" }),
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

  return (
    <div className="stack">
      <div>
        <h1>AI Checker</h1>
        <p className="muted">
          Local heuristic scan for AI-like writing. Target under 10% agent share on final research.
        </p>
      </div>

      {error && <div className="alert error">{error}</div>}

      <div className="panel stack">
        <label>
          Content to evaluate
          <textarea
            style={{ minHeight: 260 }}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste research text here"
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
