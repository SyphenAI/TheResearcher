import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import TextDiffPanes from "../components/TextDiffPanes";

/**
 * Full-page paper release diff (open in a new browser tab from the desk).
 * Query: ?left=<releaseId>&right=<releaseId>
 */
export default function PaperDiffPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const leftId = params.get("left") || "";
  const rightId = params.get("right") || "";

  const [projectTitle, setProjectTitle] = useState("");
  const [releases, setReleases] = useState([]);
  const [left, setLeft] = useState(null);
  const [right, setRight] = useState(null);
  const [pickLeft, setPickLeft] = useState(leftId);
  const [pickRight, setPickRight] = useState(rightId);
  const [view, setView] = useState("full"); // full | section
  const [sectionTitle, setSectionTitle] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    api(`/api/projects/${projectId}/paper-releases?limit=80`)
      .then((res) => {
        setReleases(res.releases || []);
        setProjectTitle((t) => t || `Project #${projectId}`);
      })
      .catch((e) => setError(e.message || "Could not load releases"));
    api(`/api/projects/${projectId}`)
      .then((p) => setProjectTitle(p.title || `Project #${projectId}`))
      .catch(() => {});
  }, [projectId]);

  useEffect(() => {
    setPickLeft(leftId);
    setPickRight(rightId);
  }, [leftId, rightId]);

  useEffect(() => {
    if (!projectId || !leftId || !rightId) {
      setLeft(null);
      setRight(null);
      return;
    }
    let cancelled = false;
    setBusy(true);
    setError("");
    api(`/api/projects/${projectId}/paper-diff?left=${leftId}&right=${rightId}`)
      .then((res) => {
        if (cancelled) return;
        setLeft(res.left);
        setRight(res.right);
        setProjectTitle(res.project_title || projectTitle);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message || "Diff failed");
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, leftId, rightId]);

  const sectionNames = useMemo(() => {
    const titles = new Set();
    for (const s of left?.sections || []) if (s.title) titles.add(s.title);
    for (const s of right?.sections || []) if (s.title) titles.add(s.title);
    return Array.from(titles);
  }, [left, right]);

  const leftText = useMemo(() => {
    if (!left) return "";
    if (view === "section" && sectionTitle) {
      const s = (left.sections || []).find((x) => x.title === sectionTitle);
      return s?.content_md || "";
    }
    return left.combined_md || "";
  }, [left, view, sectionTitle]);

  const rightText = useMemo(() => {
    if (!right) return "";
    if (view === "section" && sectionTitle) {
      const s = (right.sections || []).find((x) => x.title === sectionTitle);
      return s?.content_md || "";
    }
    return right.combined_md || "";
  }, [right, view, sectionTitle]);

  function applyPicks() {
    if (!pickLeft || !pickRight) {
      setError("Select two saved versions (left and right).");
      return;
    }
    if (String(pickLeft) === String(pickRight)) {
      setError("Pick two different versions to compare.");
      return;
    }
    setParams({ left: String(pickLeft), right: String(pickRight) });
  }

  function swapSides() {
    setParams({ left: rightId, right: leftId });
  }

  const leftLabel = left
    ? `v${left.version_label} (${left.kind})`
    : pickLeft
      ? `Release #${pickLeft}`
      : "Left (base)";
  const rightLabel = right
    ? `v${right.version_label} (${right.kind})`
    : pickRight
      ? `Release #${pickRight}`
      : "Right (newer)";

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
        <div>
          <button className="btn ghost" type="button" onClick={() => navigate(`/app/research/${projectId}`)}>
            ← Back to desk
          </button>
          <h1 style={{ margin: "0.5rem 0 0" }}>Version diff</h1>
          <p className="muted" style={{ margin: "0.25rem 0 0" }}>
            {projectTitle || `Project #${projectId}`} · red = removed from left · green = added on right
          </p>
        </div>
        <div className="row" style={{ flexWrap: "wrap" }}>
          <button className="btn ghost" type="button" onClick={swapSides} disabled={!leftId || !rightId || busy}>
            Swap sides
          </button>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}
      {busy && <div className="alert warn">Loading snapshots…</div>}

      <div className="panel stack">
        <strong>Select two saved versions</strong>
        <div className="row" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
          <label style={{ minWidth: 200, flex: 1 }}>
            Left (base / older)
            <select value={pickLeft} onChange={(e) => setPickLeft(e.target.value)} disabled={busy}>
              <option value="">— choose —</option>
              {releases.map((r) => (
                <option key={r.id} value={r.id}>
                  v{r.version_label} · {r.kind}
                  {r.created_at ? ` · ${new Date(r.created_at).toLocaleString()}` : ""}
                </option>
              ))}
            </select>
          </label>
          <label style={{ minWidth: 200, flex: 1 }}>
            Right (compare / newer)
            <select value={pickRight} onChange={(e) => setPickRight(e.target.value)} disabled={busy}>
              <option value="">— choose —</option>
              {releases.map((r) => (
                <option key={r.id} value={r.id}>
                  v{r.version_label} · {r.kind}
                  {r.created_at ? ` · ${new Date(r.created_at).toLocaleString()}` : ""}
                </option>
              ))}
            </select>
          </label>
          <button className="btn primary" type="button" onClick={applyPicks} disabled={busy}>
            Compare
          </button>
        </div>
        {!releases.length && (
          <p className="muted" style={{ margin: 0 }}>
            No commits yet. On the research desk, use <strong>Commit</strong> (or Publish primary) first.
          </p>
        )}
        <div className="row" style={{ flexWrap: "wrap" }}>
          <label className="row" style={{ gap: "0.35rem", alignItems: "center" }}>
            <input
              type="radio"
              name="diffview"
              checked={view === "full"}
              onChange={() => setView("full")}
            />
            Full paper
          </label>
          <label className="row" style={{ gap: "0.35rem", alignItems: "center" }}>
            <input
              type="radio"
              name="diffview"
              checked={view === "section"}
              onChange={() => {
                setView("section");
                if (!sectionTitle && sectionNames[0]) setSectionTitle(sectionNames[0]);
              }}
            />
            One section
          </label>
          {view === "section" && (
            <label style={{ minWidth: 180 }}>
              Section
              <select value={sectionTitle} onChange={(e) => setSectionTitle(e.target.value)}>
                {sectionNames.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </div>

      {left && right && (
        <div className="panel stack">
          <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
            <strong>
              {leftLabel} → {rightLabel}
              {view === "section" && sectionTitle ? ` · ${sectionTitle}` : ""}
            </strong>
            <span className="muted" style={{ fontSize: "0.85rem" }}>
              {(leftText || "").length} chars → {(rightText || "").length} chars
            </span>
          </div>
          {leftText === rightText ? (
            <div className="alert ok">No text differences for this selection.</div>
          ) : (
            <TextDiffPanes
              original={leftText}
              proposed={rightText}
              originalLabel={leftLabel}
              proposedLabel={rightLabel}
              editableProposed={false}
            />
          )}
        </div>
      )}
    </div>
  );
}
