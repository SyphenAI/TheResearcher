import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";

export default function SearchPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const initial = params.get("q") || "";
  const initialTab = params.get("tab") === "scholar" ? "scholar" : "library";
  const [tab, setTab] = useState(initialTab);
  const [q, setQ] = useState(initial);
  const [hits, setHits] = useState([]);
  const [scholarHits, setScholarHits] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [projects, setProjects] = useState([]);
  const [artifactProjectId, setArtifactProjectId] = useState("");

  useEffect(() => {
    api("/api/projects")
      .then((rows) => {
        const list = Array.isArray(rows) ? rows : [];
        setProjects(list);
        if (list.length) setArtifactProjectId(String(list[0].id));
      })
      .catch(() => {});
  }, []);

  async function runLibrarySearch(term) {
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
      setMessage(res.message || `${res.total || 0} local result(s).`);
      setParams({ q: query, tab: "library" });
    } catch (e) {
      setError(e.message || "Search failed.");
    } finally {
      setBusy(false);
    }
  }

  async function runScholarSearch(term) {
    const query = (term ?? q).trim();
    if (query.length < 2) {
      setScholarHits([]);
      setMessage("Type at least 2 characters.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const res = await api(
        `/api/workspace/scholar/search?q=${encodeURIComponent(query)}&limit=15`
      );
      setScholarHits(res.results || []);
      setMessage(
        res.message ||
          `Found ${res.total || 0} scholarly hit(s)` +
            (res.sources_tried?.length ? ` via ${res.sources_tried.join(", ")}` : "") +
            ". Ranked by topic fit + citations + recency."
      );
      if (res.note) setMessage((m) => (m ? `${m} ${res.note}` : res.note));
      setParams({ q: query, tab: "scholar" });
    } catch (e) {
      setError(e.message || "Scholar search failed.");
    } finally {
      setBusy(false);
    }
  }

  async function runSearch(term) {
    if (tab === "scholar") return runScholarSearch(term);
    return runLibrarySearch(term);
  }

  async function addScholarCitation(item) {
    if (!artifactProjectId) {
      setError("Create or select a project first to save citations.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const row = await api("/api/workspace/scholar/add-citation", {
        method: "POST",
        body: JSON.stringify({
          project_id: Number(artifactProjectId),
          style: "apa",
          item,
        }),
      });
      setMessage(`Added citation to project: ${row.title || item.title}`);
    } catch (e) {
      setError(e.message || "Could not add citation.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (initial.trim().length >= 2) {
      if (initialTab === "scholar") runScholarSearch(initial);
      else runLibrarySearch(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="stack">
      <div>
        <h1>Search</h1>
        <p className="muted">
          Search your local research library, or search the world of scholarly papers (same engines as
          the project desk).
        </p>
      </div>

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert ok">{message}</div>}

      <div className="row">
        <button
          className={`tab ${tab === "library" ? "active" : ""}`}
          type="button"
          onClick={() => setTab("library")}
        >
          Local library
        </button>
        <button
          className={`tab ${tab === "scholar" ? "active" : ""}`}
          type="button"
          onClick={() => setTab("scholar")}
        >
          Scholar (world)
        </button>
      </div>

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
            placeholder={
              tab === "scholar"
                ? "e.g. exposure management prioritization exploitability"
                : "e.g. residual risk, BAS, exposure ownership"
            }
            autoFocus
          />
        </label>
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? "Searching…" : tab === "scholar" ? "Search scholar" : "Search library"}
        </button>
      </form>

      {tab === "library" && (
        <div className="panel stack">
          <h2 style={{ margin: 0 }}>Local results</h2>
          <p className="muted" style={{ margin: 0 }}>
            Projects, section paper text, citations, and artifact names.
          </p>
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
      )}

      {tab === "scholar" && (
        <div className="panel stack">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>Scholar results</h2>
            <label style={{ minWidth: 220 }}>
              Save citations to project
              <select
                value={artifactProjectId}
                onChange={(e) => setArtifactProjectId(e.target.value)}
                disabled={!projects.length}
              >
                {!projects.length && <option value="">No projects yet</option>}
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted" style={{ margin: 0 }}>
            Crossref + Semantic Scholar + OpenAlex. Ranked by topic fit, citations, and recency.
          </p>
          {!scholarHits.length && <p className="muted">No scholarly hits yet.</p>}
          {scholarHits.map((hit, idx) => (
            <div key={`${hit.doi || hit.title}-${idx}`} className="panel stack" style={{ padding: "0.65rem" }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <strong>{hit.title}</strong>
                <span className="badge">score {hit.score}</span>
              </div>
              <div className="muted" style={{ fontSize: "0.85rem" }}>
                {hit.author || "Author"} · {hit.year || "n.d."}
                {hit.venue ? ` · ${hit.venue}` : ""}
                {hit.cited_by_count != null ? ` · cited≈${hit.cited_by_count}` : ""}
                {hit.sources?.length ? ` · ${hit.sources.join("+")}` : ""}
              </div>
              {hit.abstract && (
                <div style={{ fontSize: "0.88rem" }}>
                  {hit.abstract.slice(0, 260)}
                  {hit.abstract.length > 260 ? "…" : ""}
                </div>
              )}
              <div className="row">
                {hit.url && (
                  <a className="btn ghost" href={hit.url} target="_blank" rel="noreferrer">
                    Open
                  </a>
                )}
                <button
                  className="btn primary"
                  type="button"
                  disabled={busy || !artifactProjectId}
                  onClick={() => addScholarCitation(hit)}
                >
                  Add to project citations
                </button>
                {artifactProjectId && (
                  <button
                    className="btn"
                    type="button"
                    onClick={() => navigate(`/app/research/${artifactProjectId}`)}
                  >
                    Open project
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
