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
    context = ""
    section: ResearchSection | None = None
    if body.section_id:
        section = db.query(ResearchSection).filter(ResearchSection.id == body.section_id).first()
        if section:
            context = section.content_md

    result = local_research_assist(body.prompt, context, rewrite_human=body.rewrite_human)
    if section:
        section.agent_chars += result["agent_chars"]
        project = db.query(Project).filter(Project.id == section.project_id).first()
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
        db.commit()

    return AssistantResponse(**result)


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
    user: User = Depends(get_current_user),
) -> dict:
    rewritten = humanize_text(body.text, strength=body.strength)
    return {
        "content": rewritten,
        "original_len": len(body.text),
        "rewritten_len": len(rewritten),
        "requested_by": user.username,
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


@router.post("/judge", response_model=JudgeOut)
def judge_output(
    body: JudgeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JudgeOut:
    result = local_judge(body.text, body.criteria)
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
    )


@router.post("/export/docx")
def export_docx(
    body: ExportRequest,
    user: User = Depends(get_current_user),
) -> Response:
    data = markdown_to_docx_bytes(body.title, body.content_md)
    filename = f"{body.title.replace(' ', '_')[:40] or 'research'}.docx"
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
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    settings = get_settings()
    folder = settings.data_dir / "artifacts" / str(project_id)
    folder.mkdir(parents=True, exist_ok=True)
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
        notes="",
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact
