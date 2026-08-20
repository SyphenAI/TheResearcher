"""Project paper semantic versions: save (no bump), commit (patch++), publish primary (major++).

Scheme:
  Start working at 0.1.1
  Commit → snapshot labeled with current version, then patch++ (0.1.1 → 0.1.2 …)
  Publish primary → snapshot as next major.0.0 (1.0.0), mark primary, set working to major.1.1 (1.1.1)
  Next publish cycle → 2.0.0 primary, working 2.1.1
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import PaperRelease, Project, ResearchSection
from app.services.timefmt import to_iso_utc

MAX_RELEASES = 80


def format_version(major: int, minor: int, patch: int) -> str:
    return f"{int(major)}.{int(minor)}.{int(patch)}"


def working_version(project: Project) -> str:
    return format_version(
        getattr(project, "version_major", 0) or 0,
        getattr(project, "version_minor", 1) or 1,
        getattr(project, "version_patch", 1) or 1,
    )


def primary_version(project: Project) -> str | None:
    if not getattr(project, "has_primary", False):
        return None
    return format_version(
        getattr(project, "primary_major", 0) or 0,
        getattr(project, "primary_minor", 0) or 0,
        getattr(project, "primary_patch", 0) or 0,
    )


def _snapshot_sections(db: Session, project_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(ResearchSection)
        .filter(ResearchSection.project_id == project_id)
        .order_by(ResearchSection.sort_order.asc(), ResearchSection.id.asc())
        .all()
    )
    out = []
    for s in rows:
        out.append(
            {
                "section_id": s.id,
                "title": s.title,
                "sort_order": s.sort_order,
                "prompt": s.prompt or "",
                "content_md": s.content_md or "",
            }
        )
    return out


def _char_count(snap: list[dict[str, Any]]) -> int:
    return sum(len(s.get("content_md") or "") for s in snap)


def _trim_releases(db: Session, project_id: int) -> None:
    ids = (
        db.query(PaperRelease.id)
        .filter(PaperRelease.project_id == project_id)
        .order_by(PaperRelease.id.desc())
        .all()
    )
    keep = {i[0] for i in ids[:MAX_RELEASES]}
    for (rid,) in ids:
        if rid not in keep:
            # Never drop the latest primary if it would fall off — keep all primaries longer
            row = db.query(PaperRelease).filter(PaperRelease.id == rid).first()
            if row and row.kind == "primary":
                continue
            db.query(PaperRelease).filter(PaperRelease.id == rid).delete(synchronize_session=False)


def commit_paper(
    db: Session,
    project: Project,
    *,
    note: str = "",
    created_by: str = "",
) -> dict[str, Any]:
    """Snapshot full paper at current working version, then bump patch."""
    snap = _snapshot_sections(db, project.id)
    if not any((s.get("content_md") or "").strip() for s in snap):
        raise ValueError("Paper is empty — write something before Commit.")

    label = working_version(project)
    row = PaperRelease(
        project_id=project.id,
        version_label=label,
        kind="commit",
        note=(note or "")[:2000],
        snapshot_json=json.dumps(snap),
        char_count=_char_count(snap),
        section_count=len(snap),
        created_by=(created_by or "")[:64],
    )
    db.add(row)

    # Bump working patch for continued drafting (0.1.1 → 0.1.2)
    project.version_patch = int(getattr(project, "version_patch", 1) or 1) + 1
    project.publish_ready = False
    db.flush()
    _trim_releases(db, project.id)
    db.refresh(row)
    return {
        "release": release_to_dict(row),
        "working_version": working_version(project),
        "primary_version": primary_version(project),
        "message": f"Committed snapshot v{label}. Working version is now v{working_version(project)}.",
    }


def publish_primary(
    db: Session,
    project: Project,
    *,
    note: str = "",
    created_by: str = "",
) -> dict[str, Any]:
    """Promote current paper to next primary major.0.0; set working to major.1.1."""
    snap = _snapshot_sections(db, project.id)
    if not any((s.get("content_md") or "").strip() for s in snap):
        raise ValueError("Paper is empty — write something before Publish primary.")

    next_major = int(getattr(project, "primary_major", 0) or 0) + 1
    if not getattr(project, "has_primary", False):
        next_major = max(1, next_major)
    label = format_version(next_major, 0, 0)

    row = PaperRelease(
        project_id=project.id,
        version_label=label,
        kind="primary",
        note=(note or "Primary published")[:2000],
        snapshot_json=json.dumps(snap),
        char_count=_char_count(snap),
        section_count=len(snap),
        created_by=(created_by or "")[:64],
    )
    db.add(row)

    project.primary_major = next_major
    project.primary_minor = 0
    project.primary_patch = 0
    project.has_primary = True
    # Next workline: major.1.1 (e.g. after 1.0.0 → work on 1.1.1)
    project.version_major = next_major
    project.version_minor = 1
    project.version_patch = 1
    project.publish_ready = True
    db.flush()
    _trim_releases(db, project.id)
    db.refresh(row)
    return {
        "release": release_to_dict(row),
        "working_version": working_version(project),
        "primary_version": primary_version(project),
        "message": (
            f"Published primary v{label}. "
            f"Continue work on v{working_version(project)} (Commit bumps patch; next Publish → v{next_major + 1}.0.0)."
        ),
    }


def list_releases(db: Session, project_id: int, *, limit: int = 40) -> list[PaperRelease]:
    limit = max(1, min(int(limit or 40), 80))
    return (
        db.query(PaperRelease)
        .filter(PaperRelease.project_id == project_id)
        .order_by(PaperRelease.id.desc())
        .limit(limit)
        .all()
    )


def get_release(db: Session, project_id: int, release_id: int) -> PaperRelease | None:
    return (
        db.query(PaperRelease)
        .filter(PaperRelease.id == release_id, PaperRelease.project_id == project_id)
        .first()
    )


def restore_release(
    db: Session,
    project: Project,
    release: PaperRelease,
    *,
    created_by: str = "",
) -> dict[str, Any]:
    """Restore section bodies from a release snapshot (does not change version numbers)."""
    try:
        snap = json.loads(release.snapshot_json or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("Corrupt release snapshot") from exc
    if not isinstance(snap, list):
        raise ValueError("Invalid release snapshot")

    # Optional safety commit of current state before restore
    try:
        current = _snapshot_sections(db, project.id)
        if any((s.get("content_md") or "").strip() for s in current):
            safety = PaperRelease(
                project_id=project.id,
                version_label=working_version(project),
                kind="pre-restore",
                note=f"Auto-snapshot before restore of v{release.version_label}",
                snapshot_json=json.dumps(current),
                char_count=_char_count(current),
                section_count=len(current),
                created_by=(created_by or "")[:64],
            )
            db.add(safety)
    except Exception:  # noqa: BLE001
        pass

    by_id = {int(s["section_id"]): s for s in snap if s.get("section_id") is not None}
    sections = (
        db.query(ResearchSection).filter(ResearchSection.project_id == project.id).all()
    )
    restored = 0
    for sec in sections:
        data = by_id.get(sec.id)
        if not data:
            continue
        sec.content_md = data.get("content_md") or ""
        if data.get("prompt") is not None:
            sec.prompt = data.get("prompt") or ""
        restored += 1
    db.flush()
    return {
        "restored_sections": restored,
        "from_version": release.version_label,
        "kind": release.kind,
        "working_version": working_version(project),
        "message": (
            f"Restored paper bodies from {release.kind} v{release.version_label}. "
            f"Working version stays v{working_version(project)} (use Commit to snapshot again)."
        ),
    }


def release_to_dict(row: PaperRelease, *, include_snapshot: bool = False) -> dict[str, Any]:
    out = {
        "id": row.id,
        "project_id": row.project_id,
        "version_label": row.version_label,
        "kind": row.kind,
        "note": row.note or "",
        "char_count": row.char_count,
        "section_count": row.section_count,
        "created_by": row.created_by or "",
        "created_at": to_iso_utc(row.created_at),
    }
    if include_snapshot:
        sections, combined = snapshot_as_paper(row)
        out["sections"] = sections
        out["combined_md"] = combined
    return out


def snapshot_as_paper(row: PaperRelease) -> tuple[list[dict[str, Any]], str]:
    """Parse release snapshot into section list + joined markdown for diffing."""
    try:
        snap = json.loads(row.snapshot_json or "[]")
    except json.JSONDecodeError:
        snap = []
    if not isinstance(snap, list):
        snap = []
    sections: list[dict[str, Any]] = []
    parts: list[str] = []
    for s in snap:
        if not isinstance(s, dict):
            continue
        title = str(s.get("title") or "Section")
        body = str(s.get("content_md") or "")
        sections.append(
            {
                "section_id": s.get("section_id"),
                "title": title,
                "sort_order": s.get("sort_order", 0),
                "prompt": s.get("prompt") or "",
                "content_md": body,
            }
        )
        parts.append(body if body.strip() else f"# {title}\n\n")
    combined = "\n\n---\n\n".join(parts)
    return sections, combined


def version_meta(project: Project) -> dict[str, Any]:
    return {
        "working_version": working_version(project),
        "primary_version": primary_version(project),
        "version_major": int(getattr(project, "version_major", 0) or 0),
        "version_minor": int(getattr(project, "version_minor", 1) or 1),
        "version_patch": int(getattr(project, "version_patch", 1) or 1),
        "has_primary": bool(getattr(project, "has_primary", False)),
    }
