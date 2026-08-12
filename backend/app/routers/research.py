from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import (
    AiCheckResult,
    Artifact,
    JudgeResult,
    Project,
    ResearchSection,
    User,
)
from app.schemas import (
    AiCheckOut,
    AiCheckRequest,
    ApplyAssistantRequest,
    ArtifactOut,
    AssistantRequest,
    AssistantResponse,
    ExportRequest,
    JudgeOut,
    JudgeRequest,
    RewriteRequest,
    SectionOut,
    TextExtractOut,
)
from app.services.ai_style import humanize_text, local_judge, local_research_assist, score_ai_likelihood
from app.services.document_text import (
    SUPPORTED_EXTENSIONS,
    DocumentExtractError,
    extract_text_from_upload,
)
from app.services.export_docx import markdown_to_docx_bytes

router = APIRouter(prefix="/api/research", tags=["research"])


@router.post("/assistant", response_model=AssistantResponse)
def research_assistant(
    body: AssistantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssistantResponse:
    from app.services.agents import run_research_panel, run_single_role

    context = ""
    section: ResearchSection | None = None
    project: Project | None = None
    evidence_mode = True if body.evidence_mode is None else body.evidence_mode
    if body.section_id:
        section = db.query(ResearchSection).filter(ResearchSection.id == body.section_id).first()
        if section:
            context = section.content_md
            project = db.query(Project).filter(Project.id == section.project_id).first()
            if project and body.evidence_mode is None:
                evidence_mode = bool(getattr(project, "evidence_mode", True))

    if body.multi_agent:
        result = run_research_panel(
            db,
            prompt=body.prompt,
            context_md=context,
            mode=body.mode,
            providers=body.providers,
            rewrite_human=body.rewrite_human,
            evidence_mode=evidence_mode,
        )
    else:
        provider = (body.providers or ["openai"])[0]
        result = run_single_role(
            db,
            provider=provider,
            role=body.mode or "researcher",
            prompt=body.prompt,
            context_md=context,
        )

    if section:
        section.agent_chars += result["agent_chars"]
        project = project or db.query(Project).filter(Project.id == section.project_id).first()
        if project:
            sections = (
                db.query(ResearchSection)
                .filter(ResearchSection.project_id == project.id)
                .all()
            )
            agent = sum(s.agent_chars for s in sections)
            human = sum(s.human_chars for s in sections)
            total = agent + human
            if total > 0:
                project.agent_contribution_pct = round(100.0 * agent / total, 1)
                project.human_contribution_pct = round(100.0 * human / total, 1)
                project.publish_ready = False
        db.commit()

    return AssistantResponse(
        content=result.get("content", ""),
        agent_chars=result.get("agent_chars", 0),
        notes=result.get("notes", ""),
        citations=result.get("citations", []),
        providers_used=result.get("providers_used", []),
        roles=result.get("roles", {}),
        used_live=bool(result.get("used_live")),
        critique=result.get("critique", ""),
        red_team=result.get("red_team", ""),
    )


@router.post("/assistant/apply", response_model=SectionOut)
def apply_assistant_output(
    body: ApplyAssistantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResearchSection:
    section = db.query(ResearchSection).filter(ResearchSection.id == body.section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    separator = "\n\n" if section.content_md.strip() else ""
    addition = body.content
    section.content_md = f"{section.content_md}{separator}{addition}"
    if body.mark_as_agent:
        section.agent_chars += len(addition)
    else:
        section.human_chars += len(addition)

    project = db.query(Project).filter(Project.id == section.project_id).first()
    if project:
        sections = (
            db.query(ResearchSection).filter(ResearchSection.project_id == project.id).all()
        )
        agent = sum(s.agent_chars for s in sections)
        human = sum(s.human_chars for s in sections)
        total = agent + human
        if total > 0:
            project.agent_contribution_pct = round(100.0 * agent / total, 1)
            project.human_contribution_pct = round(100.0 * human / total, 1)

    db.commit()
    db.refresh(section)
    return section


@router.post("/rewrite")
def rewrite_text(
    body: RewriteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    from app.services.llm import chat, list_active_providers

    rewritten = humanize_text(body.text, strength=body.strength)
    used_live = False
    provider = None
    active = list_active_providers(db, purpose="research")
    if active:
        provider = active[0]["provider"]
        live = chat(
            db,
            provider=provider,
            system=(
                "Rewrite for a Gartner-style security analyst voice. Direct, human, "
                "contractions ok. No em dashes, no double hyphens, no semicolons, no AI cliches. "
                "Keep facts. Improve clarity for executive readers."
            ),
            messages=[{"role": "user", "content": body.text[:12000]}],
            max_tokens=2500,
        )
        if live.content and not live.error:
            rewritten = humanize_text(live.content, strength=body.strength)
            used_live = True
    return {
        "content": rewritten,
        "original_len": len(body.text),
        "rewritten_len": len(rewritten),
        "requested_by": user.username,
        "used_live": used_live,
        "provider": provider,
    }


@router.get("/extract/formats")
def list_extract_formats(_: User = Depends(get_current_user)) -> dict:
    return {
        "extensions": sorted(SUPPORTED_EXTENSIONS),
        "notes": [
            "PDF text extraction works for text-based PDFs (no OCR for scans yet).",
            "Word support is .docx (not legacy .doc).",
            "Also: pptx, odt, txt, md, csv, html, rtf, json, log.",
        ],
    }


@router.post("/extract-text", response_model=TextExtractOut)
async def extract_text(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
) -> TextExtractOut:
    data = await file.read()
    try:
        extracted = extract_text_from_upload(
            file.filename or "upload.bin",
            data,
            file.content_type,
        )
    except DocumentExtractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TextExtractOut(
        **extracted,
        supported_extensions=sorted(SUPPORTED_EXTENSIONS),
    )


@router.post("/ai-check", response_model=AiCheckOut)
def ai_check(
    body: AiCheckRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AiCheckOut:
    return _run_ai_check(
        db=db,
        user=user,
        text=body.text,
        source_label=body.source_label,
    )


@router.post("/ai-check/upload", response_model=AiCheckOut)
async def ai_check_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AiCheckOut:
    data = await file.read()
    try:
        extracted = extract_text_from_upload(
            file.filename or "upload.bin",
            data,
            file.content_type,
        )
    except DocumentExtractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = _run_ai_check(
        db=db,
        user=user,
        text=extracted["text"],
        source_label=f"upload:{extracted['filename']}",
    )
    result.extracted_text = extracted["text"]
    result.filename = extracted["filename"]
    result.char_count = extracted["char_count"]
    result.truncated = extracted["truncated"]
    return result


def _run_ai_check(
    *,
    db: Session,
    user: User,
    text: str,
    source_label: str,
) -> AiCheckOut:
    result = score_ai_likelihood(text)
    sample = text[:500]
    row = AiCheckResult(
        source_label=source_label,
        text_sample=sample,
        ai_pct=result["ai_pct"],
        human_pct=result["human_pct"],
        signals_json=json.dumps(result["signals"]),
        created_by=user.username,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return AiCheckOut(
        id=row.id,
        source_label=row.source_label,
        ai_pct=row.ai_pct,
        human_pct=row.human_pct,
        signals=result["signals"],
        recommendations=result["recommendations"],
        created_at=row.created_at,
    )


@router.get("/ai-check/history", response_model=list[AiCheckOut])
def ai_check_history(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[AiCheckOut]:
    rows = db.query(AiCheckResult).order_by(AiCheckResult.id.desc()).limit(50).all()
    out: list[AiCheckOut] = []
    for row in rows:
        signals = {}
        try:
            signals = json.loads(row.signals_json or "{}")
        except json.JSONDecodeError:
            signals = {}
        out.append(
            AiCheckOut(
                id=row.id,
                source_label=row.source_label,
                ai_pct=row.ai_pct,
                human_pct=row.human_pct,
                signals=signals,
                recommendations=[],
                created_at=row.created_at,
            )
        )
    return out


@router.delete("/ai-check/history/{check_id}", status_code=204)
def delete_ai_check(
    check_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    row = db.query(AiCheckResult).filter(AiCheckResult.id == check_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Check not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.delete("/ai-check/history", status_code=200)
def clear_ai_check_history(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    count = db.query(AiCheckResult).delete()
    db.commit()
    return {"ok": True, "deleted": int(count or 0)}


@router.post("/judge", response_model=JudgeOut)
def judge_output(
    body: JudgeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JudgeOut:
    from app.services.llm import chat, list_active_providers

    # Local baseline always runs. Live models only if enabled for judge in Security.
    result = local_judge(body.text, body.criteria)
    judge_providers = list_active_providers(db, purpose="judge")
    models_used: list[str] = ["local"]
    live_bits: list[str] = []
    criteria = ", ".join(body.criteria or [])

    # Use up to 3 judge-enabled providers for multi-perspective review.
    for item in judge_providers[:3]:
        provider = item["provider"]
        live = chat(
            db,
            provider=provider,
            system=(
                "You are a strict research judge for Security Operations writing aimed at "
                "security leaders. Focus on decision quality, evidence, residual risk, and "
                "whether this reads like analyst insight rather than a pentest ticket. "
                "Be direct. No em dashes or AI filler."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Criteria: {criteria}\n\n"
                        f"Give short feedback: strengths, gaps, publish-ready yes/no, and one rewrite priority.\n\n"
                        f"TEXT:\n{body.text[:9000]}"
                    ),
                }
            ],
            max_tokens=700,
        )
        if live.content and not live.error:
            models_used.append(provider)
            live_bits.append(f"**{provider}:** {live.content[:900]}")
        elif live.error:
            live_bits.append(f"**{provider}:** unavailable ({live.error[:120]})")

    if live_bits:
        result["feedback"] = (
            f"{result['feedback']}\n\n### Live judge panel\n" + "\n\n".join(live_bits)
        )
    else:
        result["feedback"] = (
            f"{result['feedback']} No judge-enabled models active in Security. Local judge only."
        )

    row = JudgeResult(
        project_id=body.project_id,
        section_id=body.section_id,
        criteria_json=json.dumps(body.criteria),
        scores_json=json.dumps(result["scores"]),
        feedback=result["feedback"],
        overall_score=result["overall_score"],
        created_by=user.username,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return JudgeOut(
        id=row.id,
        overall_score=row.overall_score,
        scores=result["scores"],
        feedback=row.feedback,
        created_at=row.created_at,
        models_used=models_used,
        used_live=len(models_used) > 1,
    )


@router.post("/export/docx")
def export_docx(
    body: ExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    from app.services.evidence import analyze_evidence, publish_gate

    from app.services.app_settings import load_app_settings

    rules = load_app_settings()
    if body.project_id and not body.force:
        project = db.query(Project).filter(Project.id == body.project_id).first()
        if project:
            evidence = analyze_evidence(body.content_md)
            ai = score_ai_likelihood(body.content_md)
            # Project max can be looser than global, but not tighter unless set lower intentionally
            project_max = float(getattr(project, "max_agent_pct", None) or rules["max_agent_pct"])
            gate = publish_gate(
                agent_pct=float(project.agent_contribution_pct or 0),
                max_agent_pct=project_max,
                evidence=evidence,
                ai_pct=ai["ai_pct"],
            )
            if rules.get("enforce_publish_gate", True) and not gate["ready"]:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Publish gate blocked export. Adjust content or relax rules in Settings.",
                        "publish_gate": gate,
                    },
                )
            if body.force and not rules.get("allow_force_export", True):
                raise HTTPException(status_code=403, detail="Force export is disabled in Settings.")
            project.publish_ready = True
            db.commit()
    elif body.force and not rules.get("allow_force_export", True):
        raise HTTPException(status_code=403, detail="Force export is disabled in Settings.")

    from app.services.storage_paths import exports_dir

    data = markdown_to_docx_bytes(body.title, body.content_md)
    filename = f"{body.title.replace(' ', '_')[:40] or 'research'}.docx"
    if body.project_id:
        project = db.query(Project).filter(Project.id == body.project_id).first()
        if project and not getattr(project, "archived", False):
            out_dir = exports_dir(project.id, project.title)
            (out_dir / filename).write_bytes(data)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/projects/{project_id}/artifacts", response_model=ArtifactOut, status_code=201)
async def upload_artifact(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Artifact:
    from app.services.storage_paths import artifacts_dir, project_dir

    project = db.query(Project).filter(Project.id == project_id, Project.archived.is_(False)).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    folder = artifacts_dir(project.id, project.title)
    project.storage_path = str(project_dir(project.id, project.title, create=True))
    suffix = Path(file.filename or "upload.bin").suffix
    stored = f"{uuid.uuid4().hex}{suffix}"
    target = folder / stored
    content = await file.read()
    target.write_bytes(content)

    artifact = Artifact(
        project_id=project_id,
        filename=stored,
        original_name=file.filename or stored,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        notes=str(target),
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


@router.get("/projects/{project_id}/artifacts/{artifact_id}/download")
async def download_artifact(
    project_id: int,
    artifact_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from fastapi.responses import FileResponse
    from app.services.storage_paths import artifacts_dir, project_dir

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    artifact = (
        db.query(Artifact)
        .filter(Artifact.id == artifact_id, Artifact.project_id == project_id)
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    # Prefer path recorded in notes; fall back to active storage layout
    candidates = []
    if artifact.notes:
        candidates.append(Path(artifact.notes))
    candidates.append(artifacts_dir(project.id, project.title) / artifact.filename)
    # archived path may still be under storage/archive
    root = project_dir(project.id, project.title, create=False) if not project.archived else None
    if root:
        candidates.append(root / "artifacts" / artifact.filename)

    path = next((p for p in candidates if p and p.exists()), None)
    if not path:
        raise HTTPException(status_code=404, detail="File missing on disk under storage/")
    return FileResponse(
        path,
        filename=artifact.original_name,
        media_type=artifact.content_type or "application/octet-stream",
    )
