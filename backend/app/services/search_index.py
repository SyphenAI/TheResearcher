"""Local full-text style search across projects, sections, citations, artifacts."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Artifact, Citation, Project, ResearchSection


def _snippet(text: str, query: str, radius: int = 90) -> str:
    raw = re.sub(r"\s+", " ", (text or "")).strip()
    if not raw:
        return ""
    low = raw.lower()
    q = query.lower()
    idx = low.find(q)
    if idx < 0:
        return raw[: radius * 2] + ("…" if len(raw) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(raw), idx + len(query) + radius)
    piece = raw[start:end]
    if start > 0:
        piece = "…" + piece
    if end < len(raw):
        piece = piece + "…"
    return piece


def _score(hay: str, terms: list[str]) -> int:
    low = (hay or "").lower()
    score = 0
    for t in terms:
        if not t:
            continue
        if t in low:
            score += 3 + low.count(t)
        # light boost for title-ish exact-ish
        if low.startswith(t):
            score += 2
    return score


def search_workspace(db: Session, query: str, *, limit: int = 40) -> dict[str, Any]:
    q = (query or "").strip()
    if len(q) < 2:
        return {"query": q, "total": 0, "hits": [], "message": "Type at least 2 characters."}

    terms = [t for t in re.split(r"\s+", q.lower()) if t]
    limit = max(1, min(int(limit or 40), 100))
    hits: list[dict[str, Any]] = []

    projects = (
        db.query(Project)
        .filter(Project.archived.is_(False))
        .order_by(Project.updated_at.desc())
        .limit(500)
        .all()
    )
    project_ids = [p.id for p in projects]
    project_title = {p.id: p.title for p in projects}

    for p in projects:
        blob = f"{p.title}\n{p.description}\n{p.template_key}"
        sc = _score(blob, terms)
        if sc <= 0:
            continue
        hits.append(
            {
                "type": "project",
                "score": sc + 5,
                "project_id": p.id,
                "project_title": p.title,
                "title": p.title,
                "snippet": _snippet(f"{p.title}. {p.description}", q),
                "path": f"/app/research/{p.id}",
            }
        )

    if project_ids:
        sections = (
            db.query(ResearchSection)
            .filter(ResearchSection.project_id.in_(project_ids))
            .order_by(ResearchSection.id.desc())
            .limit(2000)
            .all()
        )
        for s in sections:
            blob = f"{s.title}\n{s.prompt}\n{s.content_md}"
            sc = _score(blob, terms)
            if sc <= 0:
                continue
            hits.append(
                {
                    "type": "section",
                    "score": sc,
                    "project_id": s.project_id,
                    "project_title": project_title.get(s.project_id, ""),
                    "section_id": s.id,
                    "title": s.title,
                    "snippet": _snippet(f"{s.title}. {s.content_md or s.prompt}", q),
                    "path": f"/app/research/{s.project_id}",
                }
            )

        citations = (
            db.query(Citation)
            .filter(Citation.project_id.in_(project_ids))
            .order_by(Citation.id.desc())
            .limit(1000)
            .all()
        )
        for c in citations:
            blob = f"{c.title}\n{c.author}\n{c.formatted}\n{c.notes}\n{c.url}"
            sc = _score(blob, terms)
            if sc <= 0:
                continue
            hits.append(
                {
                    "type": "citation",
                    "score": sc,
                    "project_id": c.project_id,
                    "project_title": project_title.get(c.project_id, ""),
                    "title": c.title or c.formatted[:80],
                    "snippet": _snippet(c.formatted or c.title or c.url, q),
                    "path": f"/app/research/{c.project_id}",
                }
            )

        artifacts = (
            db.query(Artifact)
            .filter(Artifact.project_id.in_(project_ids))
            .order_by(Artifact.id.desc())
            .limit(1000)
            .all()
        )
        for a in artifacts:
            blob = f"{a.original_name}\n{a.filename}\n{a.notes}"
            sc = _score(blob, terms)
            if sc <= 0:
                continue
            hits.append(
                {
                    "type": "artifact",
                    "score": sc,
                    "project_id": a.project_id,
                    "project_title": project_title.get(a.project_id, ""),
                    "title": a.original_name,
                    "snippet": _snippet(a.original_name, q),
                    "path": f"/app/research/{a.project_id}",
                }
            )

    hits.sort(key=lambda h: (-h["score"], h.get("type", ""), h.get("title", "")))
    hits = hits[:limit]
    return {
        "query": q,
        "total": len(hits),
        "hits": hits,
        "message": "" if hits else "No matches in active projects.",
    }
