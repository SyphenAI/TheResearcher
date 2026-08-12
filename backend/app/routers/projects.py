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
        created_at=project.created_at,
        updated_at=project.updated_at,
        section_count=section_count,
        sections_with_content=sections_with_content,
        task_count=task_count,
        tasks_done=tasks_done,
        artifact_count=artifacts,
        progress_pct=round(min(100.0, max(0.0, progress)), 1),
    )


def _recalc_contributions(db: Session, project: Project) -> None:
    sections = (
        db.query(ResearchSection).filter(ResearchSection.project_id == project.id).all()
    )
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
    _get_project(db, project_id)
    section = ResearchSection(project_id=project_id, **body.model_dump())
    db.add(section)
    db.commit()
    db.refresh(section)
    return section


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
        delta = len(new_content) - len(old_content)
        if "agent_chars" not in data and "human_chars" not in data:
            if delta > 0:
                section.human_chars += delta
            elif delta < 0:
                section.human_chars = max(0, section.human_chars + delta)

    _recalc_contributions(db, project)
    db.commit()
    db.refresh(section)
    return section


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
