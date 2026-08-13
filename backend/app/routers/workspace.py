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
    return {
        "active": list_active_providers(db, purpose="any"),
        "research": list_active_providers(db, purpose="research"),
        "judge": list_active_providers(db, purpose="judge"),
    }


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
    from app.services.research_scaffold import evidence_checklist_md

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
    return {
        "evidence": analysis,
        "ai_check": ai,
        "publish_gate": gate,
        "checklist_md": evidence_checklist_md(),
        "insert_helpers": {
            "uncited_count": analysis.get("uncited_count", 0),
            "uncited_claims": analysis.get("uncited_claims", [])[:20],
        },
    }


@router.post("/evidence/checklist")
def evidence_checklist_endpoint(
    topic: str = "",
    _: User = Depends(get_current_user),
) -> dict:
    from app.services.research_scaffold import evidence_checklist_md

    return {"markdown": evidence_checklist_md(topic)}


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


@router.get("/live-models")
def list_live_models(
    purpose: str = "research",
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Model picker options for Live humanize / Live panel (one key, many models)."""
    from app.models import ApiToken
    from app.routers.secrets import SUGGESTED_MODELS
    from app.security import decrypt_secret
    from app.services.llm import PROVIDER_DEFAULTS, _discover_anthropic_models, list_active_providers

    purpose_n = (purpose or "research").strip().lower()
    if purpose_n not in {"research", "judge", "any"}:
        purpose_n = "research"
    active = list_active_providers(db, purpose=purpose_n)

    options: list[dict] = [
        {
            "id": "auto",
            "label": "Auto (token preferred / fallback)",
            "provider": None,
            "model": None,
        }
    ]
    seen: set[str] = set()

    def _add(provider: str, model: str, *, mark_preferred: bool = False) -> None:
        model_id = (model or "").strip()
        prov = (provider or "").strip().lower()
        if not prov or not model_id:
            return
        oid = f"{prov}:{model_id}"
        if oid in seen:
            return
        seen.add(oid)
        label = f"{prov} · {model_id}"
        if mark_preferred:
            label += " (preferred)"
        options.append(
            {
                "id": oid,
                "label": label,
                "provider": prov,
                "model": model_id,
            }
        )

    seen_prov: set[str] = set()
    for item in active:
        prov = item["provider"]
        preferred = (item.get("model") or "").strip()
        if preferred:
            _add(prov, preferred, mark_preferred=True)
        if prov in seen_prov:
            continue
        seen_prov.add(prov)
        for m in SUGGESTED_MODELS.get(prov, []):
            _add(prov, m, mark_preferred=(m == preferred))
        if prov == "anthropic":
            try:
                row = (
                    db.query(ApiToken)
                    .filter(ApiToken.provider == "anthropic", ApiToken.is_active.is_(True))
                    .order_by(ApiToken.label.asc())
                    .first()
                )
                if row:
                    key = decrypt_secret(row.encrypted_value)
                    base = PROVIDER_DEFAULTS.get("anthropic", {}).get(
                        "base_url", "https://api.anthropic.com/v1"
                    )
                    for mid in _discover_anthropic_models(key, base)[:12]:
                        _add(prov, mid, mark_preferred=(mid == preferred))
            except Exception:  # noqa: BLE001
                pass

    return {
        "purpose": purpose_n,
        "options": options,
        "providers": sorted(seen_prov),
        "note": (
            "Pick a model for Live humanize / Live panel. Same API key can use Haiku or Sonnet; "
            "you do not need multiple tokens per provider."
        ),
    }


@router.get("/scholar/search")
def scholar_search(
    q: str = "",
    limit: int = 12,
    year_from: int | None = None,
    year_to: int | None = None,
    _: User = Depends(get_current_user),
) -> dict:
    """Find scholarly articles for a research topic (Crossref + Semantic Scholar + OpenAlex).

    Optional year_from / year_to filter by publication year (inclusive).
    """
    from app.services.app_settings import load_app_settings
    from app.services.scholar_search import search_scholar

    rules = load_app_settings()
    return search_scholar(
        q,
        limit=limit,
        year_from=year_from,
        year_to=year_to,
        semantic_scholar_key=(rules.get("semantic_scholar_api_key") or "").strip() or None,
        openalex_key=(rules.get("openalex_api_key") or "").strip() or None,
    )


# In-memory radar cache: key -> (expires_epoch, payload)
_FEED_CACHE: dict[tuple, tuple[float, dict]] = {}
_FEED_CACHE_TTL_SEC = 180  # 3 minutes


@router.get("/feed")
def research_topic_feed(
    days: int = 7,
    refresh: bool = False,
    _: User = Depends(get_current_user),
) -> dict:
    """Dashboard feed: news + papers. Cached a few minutes; refresh=1 forces live pull."""
    import time

    from app.services.app_settings import load_app_settings
    from app.services.research_feed import build_topic_feed

    rules = load_app_settings()
    topics = rules.get("follow_topics") or []
    topic_list = topics if isinstance(topics, list) else []
    days_n = max(1, min(int(days or 7), 30))
    cache_key = (tuple(str(t).lower() for t in topic_list), days_n)

    now = time.time()
    if not refresh and cache_key in _FEED_CACHE:
        exp, payload = _FEED_CACHE[cache_key]
        if exp > now:
            out = dict(payload)
            out["cached"] = True
            out["cache_ttl_sec"] = int(exp - now)
            out["note"] = (
                (out.get("note") or "")
                + f" Showing cached feed (~{int(exp - now)}s left). Use Update now to force refresh."
            ).strip()
            return out

    payload = build_topic_feed(
        topic_list,
        days=days_n,
        semantic_scholar_key=(rules.get("semantic_scholar_api_key") or "").strip() or None,
        openalex_key=(rules.get("openalex_api_key") or "").strip() or None,
    )
    payload["cached"] = False
    payload["cache_ttl_sec"] = _FEED_CACHE_TTL_SEC
    _FEED_CACHE[cache_key] = (now + _FEED_CACHE_TTL_SEC, dict(payload))
    return payload


@router.post("/scholar/add-citation", response_model=CitationOut, status_code=201)
def scholar_add_citation(
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Citation:
    """Create a project citation from a scholar search hit."""
    from app.services.scholar_search import to_citation_fields

    project_id = int(body.get("project_id") or 0)
    if not project_id or not db.query(Project).filter(Project.id == project_id).first():
        raise HTTPException(status_code=404, detail="Project not found")
    item = body.get("item") or body
    style = str(body.get("style") or "apa")
    fields = to_citation_fields(item, style=style)
    formatted = format_citation(
        fields["style"],
        fields["title"],
        fields["url"],
        fields["author"],
        fields["year"],
    )
    row = Citation(
        project_id=project_id,
        style=fields["style"],
        title=fields["title"],
        url=fields["url"],
        author=fields["author"],
        year=fields["year"],
        formatted=formatted,
        notes=fields.get("notes") or "",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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
    try:
        return create_backup()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}") from exc


@router.post("/backups/restore")
def backups_restore(filename: str, user: User = Depends(require_admin)) -> dict:
    try:
        return restore_backup(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Restore failed: {exc}") from exc


@router.get("/backups/download/{filename}")
def backups_download(filename: str, user: User = Depends(require_admin)):
    from app.services.backup import backup_dir

    path = backup_dir() / Path(filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(path, filename=path.name, media_type="application/zip")
