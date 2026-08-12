"""Evidence, frameworks, citations, peer review, diagrams, backup, providers."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models import (
    Citation,
    ControlReviewItem,
    FrameworkMapping,
    PeerReview,
    Project,
    ResearchSection,
    User,
)
from app.schemas import (
    CitationCreate,
    CitationOut,
    ControlItemCreate,
    ControlItemOut,
    DiagramRequest,
    EvidenceRequest,
    FrameworkMapCreate,
    FrameworkMapOut,
    PeerReviewCreate,
    PeerReviewOut,
    PeerReviewUpdate,
)
from app.services.backup import create_backup, list_backups, restore_backup
from app.services.diagrams import (
    attack_path_mermaid,
    control_gap_mermaid,
    from_section_text,
    stride_mermaid,
)
from app.services.evidence import analyze_evidence, format_citation, publish_gate
from app.services.app_settings import load_app_settings
from app.services.frameworks_data import (
    MITRE_TECHNIQUES,
    SAAS_CONTROL_PACKS,
    STRIDE,
)
from app.services.llm import list_active_providers
from app.services.refs_cache import load_refs
from app.services.ai_style import score_ai_likelihood
from app.services.template_store import list_templates

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get("/templates")
def templates(_: User = Depends(get_current_user)) -> dict:
    rules = load_app_settings()
    rows = list_templates()
    return {
        "templates": [
            {
                "key": t["key"],
                "title": t["title"],
                "description": t.get("description", ""),
                "sections": t.get("sections", []),
                "builtin": bool(t.get("builtin", False)),
            }
            for t in rows
        ],
        "default": rules.get("default_template_key") or "blank",
    }


@router.get("/providers")
def providers(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    return {"active": list_active_providers(db)}


@router.get("/frameworks")
def frameworks(_: User = Depends(get_current_user)) -> dict:
    return {
        "mitre": MITRE_TECHNIQUES,
        "stride": STRIDE,
        "saas_packs": SAAS_CONTROL_PACKS,
        "refs": load_refs(),
    }


@router.get("/projects/{project_id}/framework-maps", response_model=list[FrameworkMapOut])
def list_maps(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[FrameworkMapping]:
    return (
        db.query(FrameworkMapping)
        .filter(FrameworkMapping.project_id == project_id)
        .order_by(FrameworkMapping.id.desc())
        .all()
    )


@router.post("/framework-maps", response_model=FrameworkMapOut, status_code=201)
def add_map(
    body: FrameworkMapCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FrameworkMapping:
    if not db.query(Project).filter(Project.id == body.project_id).first():
        raise HTTPException(status_code=404, detail="Project not found")
    row = FrameworkMapping(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/framework-maps/{map_id}", status_code=204)
def delete_map(
    map_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    row = db.query(FrameworkMapping).filter(FrameworkMapping.id == map_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Mapping not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.post("/evidence/analyze")
def evidence_analyze(
    body: EvidenceRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    analysis = analyze_evidence(body.text)
    ai = score_ai_likelihood(body.text)
    project = None
    if body.project_id:
        project = db.query(Project).filter(Project.id == body.project_id).first()
    gate = publish_gate(
        agent_pct=float(getattr(project, "agent_contribution_pct", 0) or 0) if project else 0,
        max_agent_pct=float(getattr(project, "max_agent_pct", 10) or 10) if project else 10,
        evidence=analysis,
        ai_pct=ai["ai_pct"],
    )
    return {"evidence": analysis, "ai_check": ai, "publish_gate": gate}


@router.get("/projects/{project_id}/publish-gate")
def project_publish_gate(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    sections = (
        db.query(ResearchSection).filter(ResearchSection.project_id == project_id).all()
    )
    combined = "\n\n".join(s.content_md for s in sections)
    evidence = analyze_evidence(combined)
    ai = score_ai_likelihood(combined)
    gate = publish_gate(
        agent_pct=float(project.agent_contribution_pct or 0),
        max_agent_pct=float(getattr(project, "max_agent_pct", 10) or 10),
        evidence=evidence,
        ai_pct=ai["ai_pct"],
    )
    project.publish_ready = gate["ready"]
    db.commit()
    return {
        "project_id": project_id,
        "publish_gate": gate,
        "evidence": evidence,
        "ai_check": {"ai_pct": ai["ai_pct"], "human_pct": ai["human_pct"]},
        "publish_ready": project.publish_ready,
    }


@router.get("/projects/{project_id}/citations", response_model=list[CitationOut])
def list_citations(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Citation]:
    return (
        db.query(Citation)
        .filter(Citation.project_id == project_id)
        .order_by(Citation.id.desc())
        .all()
    )


@router.post("/citations", response_model=CitationOut, status_code=201)
def add_citation(
    body: CitationCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Citation:
    if not db.query(Project).filter(Project.id == body.project_id).first():
        raise HTTPException(status_code=404, detail="Project not found")
    formatted = format_citation(body.style, body.title, body.url, body.author, body.year)
    row = Citation(
        project_id=body.project_id,
        style=body.style,
        title=body.title,
        url=body.url,
        author=body.author,
        year=body.year,
        formatted=formatted,
        notes=body.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/citations/{citation_id}", status_code=204)
def delete_citation(
    citation_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    row = db.query(Citation).filter(Citation.id == citation_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Citation not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/projects/{project_id}/peer-reviews", response_model=list[PeerReviewOut])
def list_peer_reviews(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[PeerReview]:
    return (
        db.query(PeerReview)
        .filter(PeerReview.project_id == project_id)
        .order_by(PeerReview.id.desc())
        .all()
    )


@router.post("/peer-reviews", response_model=PeerReviewOut, status_code=201)
def create_peer_review(
    body: PeerReviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PeerReview:
    if user.role not in {"admin", "reviewer", "researcher"}:
        raise HTTPException(status_code=403, detail="Not allowed")
    if not db.query(Project).filter(Project.id == body.project_id).first():
        raise HTTPException(status_code=404, detail="Project not found")
    row = PeerReview(
        project_id=body.project_id,
        section_id=body.section_id,
        reviewer=user.username,
        comments=body.comments,
        overall_score=body.overall_score,
        status=body.status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/peer-reviews/{review_id}", response_model=PeerReviewOut)
def update_peer_review(
    review_id: int,
    body: PeerReviewUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PeerReview:
    row = db.query(PeerReview).filter(PeerReview.id == review_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Review not found")
    if user.role not in {"admin", "reviewer"} and row.reviewer != user.username:
        raise HTTPException(status_code=403, detail="Not allowed")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.get("/projects/{project_id}/controls", response_model=list[ControlItemOut])
def list_controls(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ControlReviewItem]:
    return (
        db.query(ControlReviewItem)
        .filter(ControlReviewItem.project_id == project_id)
        .order_by(ControlReviewItem.id.desc())
        .all()
    )


@router.post("/controls", response_model=ControlItemOut, status_code=201)
def add_control(
    body: ControlItemCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ControlReviewItem:
    if not db.query(Project).filter(Project.id == body.project_id).first():
        raise HTTPException(status_code=404, detail="Project not found")
    row = ControlReviewItem(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/diagrams")
def make_diagram(
    body: DiagramRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    text = body.text
    maps = []
    controls = []
    if body.section_id:
        section = db.query(ResearchSection).filter(ResearchSection.id == body.section_id).first()
        if section:
            text = text or section.content_md
    if body.project_id:
        maps = (
            db.query(FrameworkMapping)
            .filter(FrameworkMapping.project_id == body.project_id)
            .all()
        )
        controls = (
            db.query(ControlReviewItem)
            .filter(ControlReviewItem.project_id == body.project_id)
            .all()
        )

    kind = (body.kind or "attack").lower()
    if kind == "stride":
        stride_rows = [
            {"category": m.ref_id or m.name, "note": m.notes}
            for m in maps
            if m.framework == "stride"
        ]
        mermaid = (
            stride_mermaid(stride_rows)
            if stride_rows
            else from_section_text(text, kind="stride")
        )
    elif kind == "controls":
        mermaid = control_gap_mermaid(
            [{"name": c.control_name, "status": c.status} for c in controls]
        )
    else:
        techs = [{"id": m.ref_id, "name": m.name} for m in maps if m.framework == "mitre"]
        mermaid = (
            attack_path_mermaid(body.title, techs)
            if techs
            else from_section_text(text, kind="attack")
        )
    return {"kind": kind, "mermaid": mermaid}


@router.get("/backups")
def backups_list(user: User = Depends(require_admin)) -> dict:
    return {"backups": list_backups()}


@router.post("/backups")
def backups_create(user: User = Depends(require_admin)) -> dict:
    return create_backup()


@router.post("/backups/restore")
def backups_restore(filename: str, user: User = Depends(require_admin)) -> dict:
    try:
        return restore_backup(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/backups/download/{filename}")
def backups_download(filename: str, user: User = Depends(require_admin)):
    from app.services.backup import backup_dir

    path = backup_dir() / Path(filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(path, filename=path.name, media_type="application/zip")
