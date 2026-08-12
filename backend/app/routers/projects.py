from __future__ import annotations

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

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get_project(db: Session, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


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
) -> list[Project]:
    return db.query(Project).order_by(Project.updated_at.desc()).all()


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    project = Project(
        title=body.title,
        description=body.description,
        owner_id=user.id,
        status="active",
    )
    db.add(project)
    db.flush()
    for idx, title in enumerate(
        ["Overview", "Analysis", "Findings", "Recommendations", "References"]
    ):
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
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Project:
    return _get_project(db, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Project:
    project = _get_project(db, project_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    project = _get_project(db, project_id)
    if user.role != "admin" and project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this project")
    db.delete(project)
    db.commit()
    return Response(status_code=204)


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
    _: User = Depends(get_current_user),
) -> ResearchSection:
    project = _get_project(db, project_id)
    section = (
        db.query(ResearchSection)
        .filter(ResearchSection.id == section_id, ResearchSection.project_id == project_id)
        .first()
    )
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    data = body.model_dump(exclude_unset=True)
    old_content = section.content_md
    for field, value in data.items():
        setattr(section, field, value)

    if "content_md" in data and data["content_md"] is not None:
        new_content = data["content_md"]
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
