import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { appendScholarDateParams, scholarDatePreset } from "../utils/scholarDates";

export default function SearchPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const initial = params.get("q") || "";
  const tabParam = params.get("tab");
  const initialTab =
    tabParam === "scholar" ? "scholar" : tabParam === "summarize" ? "summarize" : "library";
  const [tab, setTab] = useState(initialTab);
  const [q, setQ] = useState(initial);
  const [hits, setHits] = useState([]);
  const [scholarHits, setScholarHits] = useState([]);
  const [scholarYearFrom, setScholarYearFrom] = useState("");
  const [scholarYearTo, setScholarYearTo] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [projects, setProjects] = useState([]);
  const [artifactProjectId, setArtifactProjectId] = useState("");

  // Summarize tab state
  const [sumUrl, setSumUrl] = useState("");
  const [sumText, setSumText] = useState("");
  const [sumResult, setSumResult] = useState(null);
  const fileRef = useRef(null);

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

  function applyScholarYearPreset(preset) {
    const { from, to } = scholarDatePreset(preset);
    setScholarYearFrom(from);
    setScholarYearTo(to);
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
      const params = appendScholarDateParams(
        new URLSearchParams({ q: query, limit: "15" }),
        scholarYearFrom,
        scholarYearTo
      );
      const res = await api(`/api/workspace/scholar/search?${params.toString()}`);
      setScholarHits(res.results || []);
      const yearBit =
        res.date_from || res.date_to || res.year_from || res.year_to
          ? ` · published ${res.date_from || res.year_from || "…"}–${res.date_to || res.year_to || "…"}`
          : "";
      let msg =
        res.message ||
        `Found ${res.total || 0} scholarly hit(s)` +
          (res.sources_tried?.length ? ` via ${res.sources_tried.join(", ")}` : "") +
          yearBit +
          ". Ranked by topic fit + citations + recency.";
      if (res.note) msg = `${msg} ${res.note}`;
      if (res.source_errors?.length) msg = `${msg} ${res.source_errors.join(" · ")}`;
      setMessage(msg);
      setParams({ q: query, tab: "scholar" });
    } catch (e) {
      setError(e.message || "Scholar search failed.");
    } finally {
      setBusy(false);
    }
  }

  async function runSearch(term) {
    if (tab === "scholar") return runScholarSearch(term);
    if (tab === "summarize") return;
    return runLibrarySearch(term);
  }

  async function summarizeUrl(mode = "auto") {
    const url = sumUrl.trim();
    if (!url) {
      setError("Paste a public http(s) URL to summarize.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    setSumResult(null);
    try {
      const res = await api("/api/research/summarize", {
        method: "POST",
        body: JSON.stringify({ url, mode }),
      });
      setSumResult(res);
      setMessage(
        res.note ||
          `Summary ready (${res.mode})${res.used_live ? ` via ${res.provider}` : " local"}.`
      );
      setParams({ tab: "summarize" });
    } catch (e) {
      setError(e.message || "URL summarize failed.");
    } finally {
      setBusy(false);
    }
  }

  async function summarizeText(mode = "auto") {
    if (!sumText.trim()) {
      setError("Paste text to summarize, or use a URL / file.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    setSumResult(null);
    try {
      const res = await api("/api/research/summarize", {
        method: "POST",
        body: JSON.stringify({ text: sumText, mode, title: "Pasted text" }),
      });
      setSumResult(res);
      setMessage(res.note || `Summary ready (${res.mode}).`);
      setParams({ tab: "summarize" });
    } catch (e) {
      setError(e.message || "Text summarize failed.");
    } finally {
      setBusy(false);
    }
  }

  async function summarizeFile(mode = "auto") {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Choose a document first (PDF, Word, etc.).");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    setSumResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api(`/api/research/summarize/upload?mode=${encodeURIComponent(mode)}`, {
        method: "POST",
        body: form,
      });
      setSumResult(res);
      if (res.text_preview) setSumText(res.text_preview);
      setMessage(
        (res.note || "Document summarized.") +
          (res.ocr_used ? " OCR was used on this file." : "")
      );
      setParams({ tab: "summarize" });
    } catch (e) {
      setError(e.message || "Document summarize failed.");
    } finally {
      setBusy(false);
    }
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

  async function saveSummaryToProject() {
    if (!sumResult?.summary) {
      setError("Run a summary first.");
      return;
    }
    if (!artifactProjectId) {
      setError("Select a project to attach the summary.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      const name = `summary-${stamp}.md`;
      const header =
        `# ${sumResult.title || "Summary"}\n\n` +
        `_Source: ${sumResult.source_type} · ${sumResult.source_ref || ""} · mode ${sumResult.mode}_\n\n---\n\n`;
      const blob = new Blob([header + sumResult.summary], {
        type: "text/markdown;charset=utf-8",
      });
      const form = new FormData();
      form.append("file", blob, name);
      await api(`/api/research/projects/${artifactProjectId}/artifacts`, {
        method: "POST",
        body: form,
      });
      setMessage(`Saved summary artifact on project #${artifactProjectId}.`);
    } catch (e) {
      setError(e.message || "Could not save summary artifact.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (initial.trim().length >= 2 && initialTab !== "summarize") {
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
          Local library, world scholar papers, or summarize a public URL / uploaded document.
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
        <button
          className={`tab ${tab === "summarize" ? "active" : ""}`}
          type="button"
          onClick={() => setTab("summarize")}
        >
          Summarize
        </button>
      </div>

      {tab !== "summarize" && (
        <form
          className="panel stack"
          onSubmit={(e) => {
            e.preventDefault();
            runSearch();
          }}
        >
          <div className="row">
            <label style={{ flex: 1 }}>
              Query
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={
                  tab === "scholar"
                    ? "e.g. cybersecurity exposure management prioritization (add domain words)"
                    : "e.g. residual risk, BAS, exposure ownership"
                }
                autoFocus
              />
            </label>
            <button className="btn primary" type="submit" disabled={busy}>
              {busy ? "Searching…" : tab === "scholar" ? "Search scholar" : "Search library"}
            </button>
          </div>
          {tab === "scholar" && (
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
          )}
        </form>
      )}

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
            Crossref + Semantic Scholar + OpenAlex + Google Scholar (SerpAPI key in Settings).
            Month-level dates (Crossref/OpenAlex exact; S2/Google Scholar by year). Add domain words to stay on-topic.
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
                  className="btn"
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setSumUrl(hit.url || (hit.doi ? `https://doi.org/${hit.doi}` : ""));
                    setTab("summarize");
                    setMessage("URL loaded into Summarize. Run Local or Live summarize.");
                  }}
                >
                  Summarize URL
                </button>
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

      {tab === "summarize" && (
        <div className="stack">
          <div className="panel stack">
            <h2 style={{ margin: 0 }}>Summarize source</h2>
            <p className="muted" style={{ margin: 0 }}>
              Fetch a public URL, upload a document (PDF/Word/etc., OCR if needed), or paste text.
              Local is free/extractive. Live uses a research-enabled model for analyst-style summary.
            </p>

            <label>
              URL
              <input
                value={sumUrl}
                onChange={(e) => setSumUrl(e.target.value)}
                placeholder="https://example.com/article-or-pdf"
              />
            </label>
            <div className="row">
              <button className="btn" type="button" disabled={busy} onClick={() => summarizeUrl("local")}>
                Local summarize URL
              </button>
              <button
                className="btn primary"
                type="button"
                disabled={busy}
                onClick={() => summarizeUrl("live")}
              >
                Live summarize URL
              </button>
            </div>

            <label>
              Or upload document
              <input ref={fileRef} type="file" disabled={busy} />
            </label>
            <div className="row">
              <button className="btn" type="button" disabled={busy} onClick={() => summarizeFile("local")}>
                Local summarize file
              </button>
              <button
                className="btn primary"
                type="button"
                disabled={busy}
                onClick={() => summarizeFile("live")}
              >
                Live summarize file
              </button>
            </div>

            <label>
              Or paste text
              <textarea
                style={{ minHeight: 140 }}
                value={sumText}
                onChange={(e) => setSumText(e.target.value)}
                placeholder="Paste article text, notes, or extracted content"
                disabled={busy}
              />
            </label>
            <div className="row">
              <button className="btn" type="button" disabled={busy} onClick={() => summarizeText("local")}>
                Local summarize text
              </button>
              <button
                className="btn primary"
                type="button"
                disabled={busy}
                onClick={() => summarizeText("live")}
              >
                Live summarize text
              </button>
            </div>

            <div className="row" style={{ alignItems: "flex-end" }}>
              <label style={{ minWidth: 220, flex: 1 }}>
                Save summary to project artifacts
                <select
                  value={artifactProjectId}
                  onChange={(e) => setArtifactProjectId(e.target.value)}
                  disabled={!projects.length || busy}
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
                disabled={busy || !sumResult?.summary || !artifactProjectId}
                onClick={saveSummaryToProject}
              >
                Save summary artifact
              </button>
            </div>
          </div>

          {sumResult && (
            <div className="panel stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <h2 style={{ margin: 0 }}>{sumResult.title || "Summary"}</h2>
                <div className="row">
                  <span className="badge">{sumResult.mode}</span>
                  {sumResult.used_live && (
                    <span className="badge good">
                      {sumResult.provider}
                      {sumResult.model ? ` · ${sumResult.model}` : ""}
                    </span>
                  )}
                  {sumResult.ocr_used && <span className="badge">OCR</span>}
                </div>
              </div>
              <p className="muted" style={{ margin: 0 }}>
                {sumResult.source_type} · {sumResult.source_ref} · {sumResult.char_count} chars
                {sumResult.note ? ` · ${sumResult.note}` : ""}
              </p>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  fontFamily: "var(--mono)",
                  fontSize: "0.88rem",
                  margin: 0,
                }}
              >
                {sumResult.summary}
              </pre>
              {sumResult.text_preview && (
                <details>
                  <summary className="muted">Source preview</summary>
                  <pre
                    style={{
                      whiteSpace: "pre-wrap",
                      fontFamily: "var(--mono)",
                      fontSize: "0.8rem",
                    }}
                  >
                    {sumResult.text_preview}
                  </pre>
                </details>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
