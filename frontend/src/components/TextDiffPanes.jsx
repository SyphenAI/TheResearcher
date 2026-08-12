import React, { useMemo } from "react";
import {
  diffStats,
  diffTokens,
  originalParts,
  proposedParts,
} from "../utils/textDiff";

function DiffText({ parts, side }) {
  return (
    <div className="diff-pane" aria-label={side === "original" ? "Original text" : "Proposed text"}>
      {parts.map((p, idx) => {
        if (p.type === "equal") {
          return (
            <span key={idx} className="diff-eq">
              {p.value}
            </span>
          );
        }
        if (side === "original" && p.type === "del") {
          return (
            <span key={idx} className="diff-del" title="Removed">
              {p.value}
            </span>
          );
        }
        if (side === "proposed" && p.type === "add") {
          return (
            <span key={idx} className="diff-add" title="Added">
              {p.value}
            </span>
          );
        }
        return null;
      })}
    </div>
  );
}

/**
 * Side-by-side original vs proposed with red (removed) / green (added) highlights.
 */
export default function TextDiffPanes({
  original,
  proposed,
  originalLabel = "Original",
  proposedLabel = "Proposed",
  editableProposed = false,
  onProposedChange,
}) {
  const parts = useMemo(() => diffTokens(original, proposed), [original, proposed]);
  const left = useMemo(() => originalParts(parts), [parts]);
  const right = useMemo(() => proposedParts(parts), [parts]);
  const stats = useMemo(() => diffStats(parts), [parts]);

  return (
    <div className="stack">
      <div className="row diff-legend">
        <span className="diff-legend-item">
          <span className="diff-swatch del" /> Removed ({stats.removed} words)
        </span>
        <span className="diff-legend-item">
          <span className="diff-swatch add" /> Added ({stats.added} words)
        </span>
        <span className="muted" style={{ fontSize: "0.85rem" }}>
          Unchanged {stats.equal} words
        </span>
      </div>

      <div className="grid-2 equal">
        <div className="stack">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <strong>{originalLabel}</strong>
            <span className="muted">{(original || "").length} chars</span>
          </div>
          <DiffText parts={left} side="original" />
        </div>
        <div className="stack">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <strong>{proposedLabel}</strong>
            <span className="muted">{(proposed || "").length} chars</span>
          </div>
          {editableProposed ? (
            <textarea
              className="diff-edit"
              value={proposed}
              onChange={(e) => onProposedChange?.(e.target.value)}
              style={{ minHeight: 280, fontFamily: "var(--mono)", fontSize: "0.85rem" }}
            />
          ) : (
            <DiffText parts={right} side="proposed" />
          )}
          {editableProposed && (
            <p className="muted" style={{ margin: 0, fontSize: "0.8rem" }}>
              Highlights refresh as you edit the proposed text.
            </p>
          )}
        </div>
      </div>

      {/* Always show highlighted proposed when editing, under the textarea for readability */}
      {editableProposed && (
        <div className="stack">
          <strong>Proposed with highlights</strong>
          <DiffText parts={right} side="proposed" />
        </div>
      )}
    </div>
  );
}
