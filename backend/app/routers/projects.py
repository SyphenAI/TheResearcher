from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Artifact, Project, ResearchSection, ResearchTask, User
from app.schemas import (
    ArtifactOut,
    PaperReleaseNote,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    SectionCreate,
    SectionOut,
    SectionUpdate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.services.storage_paths import (
    archive_project_folder,
    list_archived_folders,
    project_dir,
    restore_project_folder,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get_project(db: Session, project_id: int, *, include_archived: bool = False) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not include_archived and getattr(project, "archived", False):
        raise HTTPException(status_code=404, detail="Project is archived")
    return project


def _section_has_content(content_md: str, title: str) -> bool:
    text = content_md or ""
    text = re.sub(rf"^#+\s*{re.escape(title)}\s*", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"_Start drafting here\._", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[#>*_\-\s]", "", text)
    return len(text) >= 40


def _serialize_project(db: Session, project: Project) -> ProjectOut:
    sections = (
        db.query(ResearchSection).filter(ResearchSection.project_id == project.id).all()
    )
    tasks = db.query(ResearchTask).filter(ResearchTask.project_id == project.id).all()
    artifacts = db.query(Artifact).filter(Artifact.project_id == project.id).count()

    section_count = len(sections)
    sections_with_content = sum(
        1 for s in sections if _section_has_content(s.content_md, s.title)
    )
    task_count = len(tasks)
    tasks_done = sum(1 for t in tasks if t.status.lower() in {"done", "completed"})

    if project.status.lower() in {"completed", "done", "archived"}:
        progress = 100.0
    elif section_count == 0 and task_count == 0:
        progress = 0.0
    elif task_count == 0:
        progress = 100.0 * sections_with_content / max(section_count, 1)
    else:
        section_part = 100.0 * sections_with_content / max(section_count, 1)
        task_part = 100.0 * tasks_done / max(task_count, 1)
        progress = (0.65 * section_part) + (0.35 * task_part)

    from app.services.paper_versions import primary_version, working_version

    return ProjectOut(
        id=project.id,
        title=project.title,
        description=project.description,
        status=project.status,
        owner_id=project.owner_id,
        agent_contribution_pct=project.agent_contribution_pct,
        human_contribution_pct=project.human_contribution_pct,
        template_key=getattr(project, "template_key", None) or "blank",
        evidence_mode=bool(getattr(project, "evidence_mode", True)),
        max_agent_pct=float(getattr(project, "max_agent_pct", 10.0) or 10.0),
        publish_ready=bool(getattr(project, "publish_ready", False)),
        archived=bool(getattr(project, "archived", False)),
        storage_path=getattr(project, "storage_path", "") or "",
        archived_at=getattr(project, "archived_at", None),
        working_version=working_version(project),
        primary_version=primary_version(project),
        version_major=int(getattr(project, "version_major", 0) or 0),
        version_minor=int(getattr(project, "version_minor", 1) or 1),
        version_patch=int(getattr(project, "version_patch", 1) or 1),
        has_primary=bool(getattr(project, "has_primary", False)),
        created_at=project.created_at,
        updated_at=project.updated_at,
        section_count=section_count,
        sections_with_content=sections_with_content,
        task_count=task_count,
        tasks_done=tasks_done,
        artifact_count=artifacts,
        progress_pct=round(min(100.0, max(0.0, progress)), 1),
    )


def _align_section_chars_to_body(section: ResearchSection) -> None:
    """Keep agent/human char ledgers consistent with the current section body.

    - Empty body zeros both counters.
    - If the agent ledger exceeds the body (typical after deleting an agent draft),
      treat the residual body as human/seed rather than still 100% agent.
    - Otherwise clamp total to body length (cut agent first), then fill gaps as human.
    """
    text = section.content_md or ""
    n = len(text)
    agent = max(0, int(section.agent_chars or 0))
    human = max(0, int(section.human_chars or 0))
    if n <= 0:
        section.agent_chars = 0
        section.human_chars = 0
        return
    # Deleted agent draft left ledger larger than body
    if agent > n:
        section.agent_chars = 0
        section.human_chars = n
        return
    total = agent + human
    if total > n:
        overflow = total - n
        cut = min(agent, overflow)
        agent -= cut
        overflow -= cut
        if overflow:
            human = max(0, human - overflow)
    elif total < n:
        human += n - total
    section.agent_chars = agent
    section.human_chars = human


def _apply_content_char_delta(section: ResearchSection, old_content: str, new_content: str) -> None:
    """Attribute growth to human; attribute shrink to agent first, then human."""
    old_len = len(old_content or "")
    new_len = len(new_content or "")
    delta = new_len - old_len
    agent = max(0, int(section.agent_chars or 0))
    human = max(0, int(section.human_chars or 0))
    if delta > 0:
        human += delta
    elif delta < 0:
        removed = -delta
        cut = min(agent, removed)
        agent -= cut
        removed -= cut
        if removed:
            human = max(0, human - removed)
    section.agent_chars = agent
    section.human_chars = human
    _align_section_chars_to_body(section)


def _recalc_contributions(db: Session, project: Project) -> None:
    sections = (
        db.query(ResearchSection).filter(ResearchSection.project_id == project.id).all()
    )
    for s in sections:
        _align_section_chars_to_body(s)
    agent = sum(s.agent_chars for s in sections)
    human = sum(s.human_chars for s in sections)
    total = agent + human
    if total <= 0:
        project.agent_contribution_pct = 0.0
        project.human_contribution_pct = 100.0
    else:
        project.agent_contribution_pct = round(100.0 * agent / total, 1)
        project.human_contribution_pct = round(100.0 * human / total, 1)


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ProjectOut]:
    rows = (
        db.query(Project)
        .filter(Project.archived.is_(False))
        .order_by(Project.updated_at.desc())
        .all()
    )
    return [_serialize_project(db, p) for p in rows]


@router.get("/archived")
def list_archived_projects(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    rows = (
        db.query(Project)
        .filter(Project.archived.is_(True))
        .order_by(Project.archived_at.desc().nullslast(), Project.updated_at.desc())
        .all()
    )
    folders = {f.get("project_id"): f for f in list_archived_folders()}
    return {
        "projects": [_serialize_project(db, p) for p in rows],
        "storage_folders": list(folders.values()),
    }


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    from app.services.app_settings import load_app_settings
    from app.services.template_store import get_template

    rules = load_app_settings()
    key = body.template_key or rules.get("default_template_key") or "blank"
    template = get_template(key) or get_template("blank") or {
        "title": "Blank research",
        "description": "",
        "sections": ["Overview", "Analysis", "Findings", "Recommendations", "References"],
        "section_defs": [],
    }
    section_defs = template.get("section_defs")
    evidence_mode = (
        body.evidence_mode
        if body.evidence_mode is not None
        else bool(rules.get("default_evidence_mode", True))
    )
    max_agent = (
        body.max_agent_pct
        if body.max_agent_pct is not None
        else float(rules.get("max_agent_pct", 10.0))
    )
    project = Project(
        title=body.title or template["title"],
        description=body.description or template.get("description", ""),
        owner_id=user.id,
        status="active",
        template_key=key,
        evidence_mode=evidence_mode,
        max_agent_pct=max_agent,
        publish_ready=False,
        archived=False,
    )
    db.add(project)
    db.flush()
    if section_defs:
        for idx, sec in enumerate(section_defs):
            db.add(
                ResearchSection(
                    project_id=project.id,
                    title=sec["title"],
                    prompt=sec.get("prompt", ""),
                    content_md=sec.get("seed") or f"# {sec['title']}\n\n",
                    sort_order=idx,
                )
            )
    else:
        for idx, title in enumerate(template["sections"]):
            db.add(
                ResearchSection(
                    project_id=project.id,
                    title=title,
                    content_md=f"# {title}\n\n",
                    sort_order=idx,
                )
            )
    db.commit()
    db.refresh(project)
    # Local storage folder for this research topic (uploads/exports stay under tool root)
    path = project_dir(project.id, project.title, create=True)
    project.storage_path = str(path)
    db.commit()
    db.refresh(project)
    return _serialize_project(db, project)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProjectOut:
    return _serialize_project(db, _get_project(db, project_id))


@router.get("/{project_id}/paper-releases")
def list_paper_releases(
    project_id: int,
    limit: int = 40,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Official Commit / primary Publish snapshots (full paper)."""
    from app.services.paper_versions import list_releases, release_to_dict, version_meta

    project = _get_project(db, project_id)
    rows = list_releases(db, project_id, limit=limit)
    return {
        "project_id": project_id,
        **version_meta(project),
        "releases": [release_to_dict(r) for r in rows],
    }


@router.get("/{project_id}/paper-releases/{release_id}")
def get_paper_release(
    project_id: int,
    release_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """One release with full section snapshot (for restore/diff)."""
    from app.services.paper_versions import get_release, release_to_dict

    _get_project(db, project_id)
    row = get_release(db, project_id, release_id)
    if not row:
        raise HTTPException(status_code=404, detail="Release not found")
    return release_to_dict(row, include_snapshot=True)


@router.get("/{project_id}/paper-diff")
def paper_diff(
    project_id: int,
    left: int,
    right: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Compare two paper releases (left = older/base, right = newer)."""
    from app.services.paper_versions import get_release, release_to_dict

    project = _get_project(db, project_id)
    left_row = get_release(db, project_id, left)
    right_row = get_release(db, project_id, right)
    if not left_row or not right_row:
        raise HTTPException(status_code=404, detail="One or both releases not found")
    return {
        "project_id": project_id,
        "project_title": project.title,
        "left": release_to_dict(left_row, include_snapshot=True),
        "right": release_to_dict(right_row, include_snapshot=True),
    }


@router.post("/{project_id}/paper/commit")
def commit_paper_version(
    project_id: int,
    body: PaperReleaseNote | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Snapshot full paper at current working version, then bump patch (0.1.1 → 0.1.2)."""
    from app.services.paper_versions import commit_paper, version_meta

    project = _get_project(db, project_id)
    note = (body.note if body else "") or ""
    try:
        result = commit_paper(db, project, note=note, created_by=user.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(project)
    return {**result, "project": _serialize_project(db, project), **version_meta(project)}


@router.post("/{project_id}/paper/publish-primary")
def publish_primary_paper_version(
    project_id: int,
    body: PaperReleaseNote | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Publish primary major.0.0 from current paper; set working line to major.1.1."""
    from app.services.paper_versions import publish_primary, version_meta

    project = _get_project(db, project_id)
    note = (body.note if body else "") or ""
    try:
        result = publish_primary(db, project, note=note, created_by=user.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(project)
    return {**result, "project": _serialize_project(db, project), **version_meta(project)}


@router.post("/{project_id}/paper-releases/{release_id}/restore")
def restore_paper_release(
    project_id: int,
    release_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Restore section bodies from a commit/primary snapshot (version numbers unchanged)."""
    from app.services.paper_versions import get_release, restore_release, version_meta

    project = _get_project(db, project_id)
    release = get_release(db, project_id, release_id)
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    try:
        result = restore_release(db, project, release, created_by=user.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(project)
    return {**result, "project": _serialize_project(db, project), **version_meta(project)}


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProjectOut:
    project = _get_project(db, project_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return _serialize_project(db, project)


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Soft-delete: hide from dashboard and move storage into storage/archive/."""
    project = _get_project(db, project_id)
    if user.role != "admin" and project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this project")

    archive_path = archive_project_folder(project.id, project.title)
    project.archived = True
    project.status = "archived"
    project.archived_at = datetime.now(timezone.utc)
    project.storage_path = str(archive_path)
    project.publish_ready = False
    db.commit()
    return {
        "ok": True,
        "project_id": project.id,
        "archived": True,
        "storage_path": str(archive_path),
        "message": "Project removed from dashboard and archived under storage/archive/.",
    }


@router.post("/{project_id}/restore", response_model=ProjectOut)
def restore_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    project = _get_project(db, project_id, include_archived=True)
    if not getattr(project, "archived", False):
        raise HTTPException(status_code=400, detail="Project is not archived")
    if user.role != "admin" and project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not allowed to restore this project")

    restored = restore_project_folder(project.id)
    path = restored or project_dir(project.id, project.title, create=True)
    project.archived = False
    project.status = "active"
    project.archived_at = None
    project.storage_path = str(path)
    db.commit()
    db.refresh(project)
    return _serialize_project(db, project)


@router.get("/{project_id}/sections", response_model=list[SectionOut])
def list_sections(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ResearchSection]:
    _get_project(db, project_id)
    return (
        db.query(ResearchSection)
        .filter(ResearchSection.project_id == project_id)
        .order_by(ResearchSection.sort_order.asc(), ResearchSection.id.asc())
        .all()
    )


@router.post("/{project_id}/sections", response_model=SectionOut, status_code=201)
def create_section(
    project_id: int,
    body: SectionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ResearchSection:
    """Add a section after the template list (desk left panel)."""
    _get_project(db, project_id)
    data = body.model_dump()
    title = (data.get("title") or "").strip() or "New section"
    data["title"] = title[:255]
    # Append after existing sections when sort_order not explicitly set (>0) / default 0.
    if not data.get("sort_order"):
        max_order = (
            db.query(ResearchSection.sort_order)
            .filter(ResearchSection.project_id == project_id)
            .order_by(ResearchSection.sort_order.desc())
            .first()
        )
        data["sort_order"] = (max_order[0] if max_order else -1) + 1
    if not (data.get("content_md") or "").strip():
        data["content_md"] = f"# {title}\n\n"
    section = ResearchSection(project_id=project_id, **data)
    db.add(section)
    db.commit()
    db.refresh(section)
    return section


@router.delete("/{project_id}/sections/{section_id}", status_code=204)
def delete_section(
    project_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    """Remove a section from the project (paper body for that section is deleted)."""
    _get_project(db, project_id)
    section = (
        db.query(ResearchSection)
        .filter(ResearchSection.id == section_id, ResearchSection.project_id == project_id)
        .first()
    )
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    remaining = (
        db.query(ResearchSection)
        .filter(ResearchSection.project_id == project_id, ResearchSection.id != section_id)
        .count()
    )
    if remaining < 1:
        raise HTTPException(status_code=400, detail="Keep at least one section in the paper.")
    db.delete(section)
    db.commit()
    return Response(status_code=204)


@router.post("/{project_id}/sections/{section_id}/move", response_model=list[SectionOut])
def move_section(
    project_id: int,
    section_id: int,
    direction: str = "up",
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ResearchSection]:
    """Reorder section tiles: direction=up|down (swap with neighbor)."""
    _get_project(db, project_id)
    rows = (
        db.query(ResearchSection)
        .filter(ResearchSection.project_id == project_id)
        .order_by(ResearchSection.sort_order.asc(), ResearchSection.id.asc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No sections")
    # Normalize contiguous sort_order so swaps stay stable
    for idx, row in enumerate(rows):
        row.sort_order = idx
    db.flush()

    ids = [r.id for r in rows]
    try:
        i = ids.index(section_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Section not found") from exc

    d = (direction or "up").strip().lower()
    if d not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="direction must be up or down")
    j = i - 1 if d == "up" else i + 1
    if j < 0 or j >= len(rows):
        # Already at edge — return current order unchanged
        return rows

    rows[i].sort_order, rows[j].sort_order = rows[j].sort_order, rows[i].sort_order
    db.commit()
    return (
        db.query(ResearchSection)
        .filter(ResearchSection.project_id == project_id)
        .order_by(ResearchSection.sort_order.asc(), ResearchSection.id.asc())
        .all()
    )


@router.patch("/{project_id}/sections/{section_id}", response_model=SectionOut)
def update_section(
    project_id: int,
    section_id: int,
    body: SectionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResearchSection:
    from app.services.section_versions import record_section_version

    project = _get_project(db, project_id)
    section = (
        db.query(ResearchSection)
        .filter(ResearchSection.id == section_id, ResearchSection.project_id == project_id)
        .first()
    )
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    data = body.model_dump(exclude_unset=True)
    old_content = section.content_md or ""
    for field, value in data.items():
        setattr(section, field, value)

    if "content_md" in data and data["content_md"] is not None:
        new_content = data["content_md"]
        if new_content != old_content and old_content.strip():
            record_section_version(
                db,
                section_id=section.id,
                project_id=project_id,
                content_md=old_content,
                label="before-save",
                created_by=user.username,
            )
        if "agent_chars" not in data and "human_chars" not in data:
            _apply_content_char_delta(section, old_content, new_content)
        else:
            _align_section_chars_to_body(section)

    _recalc_contributions(db, project)
    db.commit()
    db.refresh(section)
    return section


@router.post("/{project_id}/resync-contributions", response_model=ProjectOut)
def resync_project_contributions(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProjectOut:
    """Re-align agent/human char ledgers to current section bodies and refresh %.

    Use after deleting agent drafts so the desk metrics are not stuck at 100% agent.
    """
    project = _get_project(db, project_id)
    _recalc_contributions(db, project)
    project.publish_ready = False
    db.commit()
    db.refresh(project)
    return _serialize_project(db, project)


@router.get("/{project_id}/sections/{section_id}/versions")
def list_section_versions(
    project_id: int,
    section_id: int,
    limit: int = 12,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    from app.services.section_versions import list_section_versions as list_vers
    from app.services.section_versions import version_to_dict

    _get_project(db, project_id)
    section = (
        db.query(ResearchSection)
        .filter(ResearchSection.id == section_id, ResearchSection.project_id == project_id)
        .first()
    )
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    rows = list_vers(db, section_id, limit=limit)
    return {"section_id": section_id, "versions": [version_to_dict(r) for r in rows]}


@router.post("/{project_id}/sections/{section_id}/versions/{version_id}/restore", response_model=SectionOut)
def restore_section_version(
    project_id: int,
    section_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResearchSection:
    from app.services.section_versions import get_version, record_section_version

    project = _get_project(db, project_id)
    section = (
        db.query(ResearchSection)
        .filter(ResearchSection.id == section_id, ResearchSection.project_id == project_id)
        .first()
    )
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    ver = get_version(db, version_id, section_id=section_id)
    if not ver:
        raise HTTPException(status_code=404, detail="Version not found")

    # Snapshot current before restore
    if (section.content_md or "").strip():
        record_section_version(
            db,
            section_id=section.id,
            project_id=project_id,
            content_md=section.content_md or "",
            label="before-restore",
            created_by=user.username,
        )
    section.content_md = ver.content_md or ""
    section.human_chars = max(section.human_chars, len(section.content_md))
    _recalc_contributions(db, project)
    db.commit()
    db.refresh(section)
    return section


@router.get("/{project_id}/tasks", response_model=list[TaskOut])
def list_tasks(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ResearchTask]:
    _get_project(db, project_id)
    return (
        db.query(ResearchTask)
        .filter(ResearchTask.project_id == project_id)
        .order_by(ResearchTask.id.desc())
        .all()
    )


@router.post("/{project_id}/tasks", response_model=TaskOut, status_code=201)
def create_task(
    project_id: int,
    body: TaskCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ResearchTask:
    _get_project(db, project_id)
    task = ResearchTask(project_id=project_id, **body.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{project_id}/tasks/{task_id}", response_model=TaskOut)
def update_task(
    project_id: int,
    task_id: int,
    body: TaskUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ResearchTask:
    _get_project(db, project_id)
    task = (
        db.query(ResearchTask)
        .filter(ResearchTask.id == task_id, ResearchTask.project_id == project_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{project_id}/tasks/{task_id}", status_code=204)
def delete_task(
    project_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    _get_project(db, project_id)
    task = (
        db.query(ResearchTask)
        .filter(ResearchTask.id == task_id, ResearchTask.project_id == project_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return Response(status_code=204)


@router.get("/{project_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Artifact]:
    _get_project(db, project_id)
    return (
        db.query(Artifact)
        .filter(Artifact.project_id == project_id)
        .order_by(Artifact.id.desc())
        .all()
    )
