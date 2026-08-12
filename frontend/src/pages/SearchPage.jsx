import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";

export default function SearchPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const initial = params.get("q") || "";
  const [q, setQ] = useState(initial);
  const [hits, setHits] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function runSearch(term) {
    const query = (term ?? q).trim();
    if (query.length < 2) {
      setHits([]);
      setMessage("Type at least 2 characters.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const res = await api(`/api/search?q=${encodeURIComponent(query)}&limit=50`);
      setHits(res.hits || []);
      setMessage(res.message || `${res.total || 0} result(s).`);
      setParams(query ? { q: query } : {});
    } catch (e) {
      setError(e.message || "Search failed.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (initial.trim().length >= 2) {
      runSearch(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="stack">
      <div>
        <h1>Search</h1>
        <p className="muted">
          Full-text style search across active projects, section paper text, citations, and artifact names.
        </p>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}

      <form
        className="panel row"
        onSubmit={(e) => {
          e.preventDefault();
          runSearch();
        }}
      >
        <label style={{ flex: 1 }}>
          Query
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. residual risk, BAS, exposure ownership"
            autoFocus
          />
        </label>
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? "Searching…" : "Search"}
        </button>
      </form>

      <div className="panel stack">
        <h2 style={{ margin: 0 }}>Results</h2>
        {!hits.length && <p className="muted">No hits yet.</p>}
        {hits.map((h, idx) => (
          <button
            key={`${h.type}-${h.project_id}-${h.section_id || h.title}-${idx}`}
            className="section-item"
            type="button"
            onClick={() => h.path && navigate(h.path)}
            style={{ textAlign: "left", width: "100%" }}
          >
            <div className="row" style={{ justifyContent: "space-between" }}>
              <strong>{h.title}</strong>
              <span className="badge">{h.type}</span>
            </div>
            <div className="muted" style={{ fontSize: "0.85rem" }}>
              {h.project_title}
              {h.section_id ? ` · section #${h.section_id}` : ""}
            </div>
            <div style={{ marginTop: "0.35rem", fontSize: "0.9rem" }}>{h.snippet}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
