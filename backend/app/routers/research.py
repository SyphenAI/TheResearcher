from __future__ import annotations

import json
import re
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
    SummarizeRequest,
    TextExtractOut,
)
from app.services.ai_style import humanize_text, local_judge, local_research_assist, score_ai_likelihood
from app.services.document_text import (
    SUPPORTED_EXTENSIONS,
    DocumentExtractError,
    extract_text_from_upload,
)
from app.services.export_docx import markdown_to_docx_bytes

# Research desk HTTP API. Prefix: /api/research
# Key routes:
#   POST /assistant       — multi-agent or single-role draft (does not save paper)
#   POST /assistant/apply — append draft to section + agent_chars ledger
#   POST /rewrite         — local or live humanize
#   POST /ai-check        — local heuristic (+ optional live panel)
#   POST /judge           — local + judge-enabled models
# Reasoning implementations: services/agents.py, ai_style.py, research_scaffold.py, llm.py
router = APIRouter(prefix="/api/research", tags=["research"])


@router.post("/assistant", response_model=AssistantResponse)
def research_assistant(
    body: AssistantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssistantResponse:
    """Desk Research Assistant. multi_agent=true -> agents.run_research_panel (slow)."""
    from app.services.agents import run_research_panel, run_single_role

    context = ""
    section: ResearchSection | None = None
    project: Project | None = None
    evidence_mode = True if body.evidence_mode is None else body.evidence_mode
    if body.section_id:
        section = db.query(ResearchSection).filter(ResearchSection.id == body.section_id).first()
        if section:
            # Existing paper body is context for the panel, not overwritten here.
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

    # Do not bump agent_chars until Apply to paper — draft-only runs must not
    # leave the desk stuck at high agent contribution.
    if section and project:
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
    """Write Assistant draft into the section paper. This is when agent % increases."""
    section = db.query(ResearchSection).filter(ResearchSection.id == body.section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    separator = "\n\n" if section.content_md.strip() else ""
    addition = body.content
    section.content_md = f"{section.content_md}{separator}{addition}"
    # Contribution ledger (desk Agent contribution %). Only bumps on apply, not on draft.
    if body.mark_as_agent:
        section.agent_chars = max(0, int(section.agent_chars or 0)) + len(addition)
    else:
        section.human_chars = max(0, int(section.human_chars or 0)) + len(addition)

    project = db.query(Project).filter(Project.id == section.project_id).first()
    if project:
        from app.routers.projects import _recalc_contributions

        _recalc_contributions(db, project)
        project.publish_ready = False

    db.commit()
    db.refresh(section)
    return section


@router.post("/rewrite")
def rewrite_text(
    body: RewriteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Humanize endpoint. mode=local|live|auto. Desk requires Accept before save."""
    from app.services.llm import chat, list_active_providers

    mode = (body.mode or "auto").strip().lower()
    if mode not in {"local", "live", "auto"}:
        mode = "auto"

    text = body.text or ""
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text is required to rewrite.")

    # Always compute local rules rewrite; live path may replace it.
    local_rewritten = humanize_text(text, strength=body.strength)
    rewritten = local_rewritten
    used_live = False
    provider = None
    model = None
    error = None
    active = list_active_providers(db, purpose="research")
    override_provider = (body.provider or "").strip().lower() or None
    override_model = (body.model or "").strip() or None

    want_live = mode in {"live", "auto"}
    if want_live and active:
        # Optional picker: same API key, choose Haiku vs Sonnet (etc.).
        item = active[0]
        if override_provider:
            match = next((a for a in active if a["provider"] == override_provider), None)
            if not match:
                if mode == "live":
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"No research-enabled token for provider '{override_provider}'. "
                            "Add/enable one in Security."
                        ),
                    )
            else:
                item = match
        provider = item["provider"]
        preferred = override_model or (item.get("model") or "").strip() or None
        live = chat(
            db,
            provider=provider,
            model=preferred,
            system=(
                "Rewrite for a Gartner-style security analyst voice. Direct, human, "
                "contractions ok. No em dashes, no double hyphens, no semicolons, no AI cliches. "
                "Keep facts and meaning. Improve clarity for executive readers. "
                "Prefer decision framing, residual risk, and sequenced recommendations when relevant. "
                "Do not invent sources, CVE counts, or market data."
            ),
            messages=[{"role": "user", "content": text[:12000]}],
            max_tokens=2500,
            purpose="rewrite_live" if mode == "live" else "rewrite",
            created_by=user.username,
        )
        if live.content and not live.error:
            rewritten = humanize_text(live.content, strength=body.strength)
            used_live = True
            model = live.model
        else:
            error = live.error or "Live rewrite returned empty content."
            if mode == "live":
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"Live humanize failed via {provider}: {error}. "
                        "Fix the token/model in Security, or use Local humanize."
                    ),
                )
    elif mode == "live" and not active:
        raise HTTPException(
            status_code=400,
            detail=(
                "Live humanize needs an active research-enabled token in Security. "
                "Add one, or use Local humanize."
            ),
        )

    return {
        "content": rewritten,
        "original_len": len(text),
        "rewritten_len": len(rewritten),
        "requested_by": user.username,
        "used_live": used_live,
        "provider": provider,
        "model": model,
        "mode": "live" if used_live else "local",
        "requested_mode": mode,
        "error": error,
        "note": (
            f"Live rewrite via {provider}" + (f" ({model})" if model else "")
            if used_live
            else (
                "Local rules rewrite only."
                if mode == "local"
                else "Local rules rewrite (no research token or live call failed in auto mode)."
            )
        ),
    }


@router.post("/summarize")
def summarize_source(
    body: SummarizeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Summarize pasted text or fetch+summarize a public URL."""
    from app.services.summarize import fetch_url_text, summarize_payload

    try:
        if (body.url or "").strip():
            fetched = fetch_url_text(body.url.strip())
            return summarize_payload(
                db,
                text=fetched["text"],
                title=body.title.strip() or fetched.get("title") or "",
                source_type=fetched.get("source_type") or "url",
                source_ref=fetched.get("url") or body.url,
                mode=body.mode,
                user_name=user.username,
                ocr_used=bool(fetched.get("ocr_used")),
            )
        if (body.text or "").strip():
            return summarize_payload(
                db,
                text=body.text,
                title=body.title.strip() or "Pasted text",
                source_type="text",
                source_ref="paste",
                mode=body.mode,
                user_name=user.username,
            )
        raise HTTPException(status_code=400, detail="Provide a URL or text to summarize.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/summarize/upload")
async def summarize_upload(
    file: UploadFile = File(...),
    mode: str = "auto",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Extract text from an uploaded document and summarize it."""
    from app.services.summarize import summarize_payload

    data = await file.read()
    try:
        extracted = extract_text_from_upload(
            file.filename or "upload.bin",
            data,
            file.content_type,
        )
    except DocumentExtractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = summarize_payload(
            db,
            text=extracted["text"],
            title=extracted.get("filename") or file.filename or "Upload",
            source_type="upload",
            source_ref=extracted.get("filename") or file.filename or "upload",
            mode=mode,
            user_name=user.username,
            ocr_used=bool(extracted.get("ocr_used")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["filename"] = extracted.get("filename")
    result["extension"] = extracted.get("extension")
    result["truncated"] = extracted.get("truncated")
    return result


@router.get("/extract/formats")
def list_extract_formats(_: User = Depends(get_current_user)) -> dict:
    from app.services.document_text import ocr_available

    return {
        "extensions": sorted(SUPPORTED_EXTENSIONS),
        "ocr_available": ocr_available(),
        "notes": [
            "PDF text extraction uses the embedded text layer first.",
            (
                "Scanned PDFs: OCR is available (tesseract, up to 15 pages)."
                if ocr_available()
                else "Scanned PDFs: OCR binary not detected in this runtime."
            ),
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
        mode=body.mode,
        max_live=body.max_live,
        provider=body.provider,
        model=body.model,
    )


@router.post("/ai-check/upload", response_model=AiCheckOut)
async def ai_check_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    mode: str = "quick",
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
        mode=mode,
    )
    result.extracted_text = extracted["text"]
    result.filename = extracted["filename"]
    result.char_count = extracted["char_count"]
    result.truncated = extracted["truncated"]
    result.ocr_used = bool(extracted.get("ocr_used"))
    result.ocr_note = extracted.get("ocr_note") or ""
    return result


def _run_live_ai_panel(
    db: Session,
    *,
    text: str,
    local_ai_pct: float,
    user: User,
    max_live: int = 3,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> tuple[list[dict], list[str], list[str]]:
    """Ask up to max_live research-enabled models for a second opinion. Local score stays authoritative."""
    from app.services.llm import chat, list_active_providers

    active = list_active_providers(db, purpose="research")
    # One entry per provider (first label wins) so we do not triple-hit the same API.
    seen: set[str] = set()
    unique: list[dict] = []
    for item in active:
        prov = item["provider"]
        if prov in seen:
            continue
        seen.add(prov)
        unique.append(item)
        if len(unique) >= max(1, min(int(max_live or 3), 5)):
            break

    # Picker: if user chose provider+model, only run that provider with that model.
    prov_over = (provider_override or "").strip().lower() or None
    model_over = (model_override or "").strip() or None
    if prov_over:
        match = next((u for u in unique if u["provider"] == prov_over), None)
        if match:
            unique = [match]
        elif active:
            # Provider has a token but wasn't in unique set
            match = next((a for a in active if a["provider"] == prov_over), None)
            if match:
                unique = [match]

    panel: list[dict] = []
    models_used: list[str] = ["local"]
    extra_recs: list[str] = []

    if not unique:
        panel.append(
            {
                "provider": "none",
                "model": "",
                "ok": False,
                "feedback": (
                    "No research-enabled tokens active. Local quick score only. "
                    "Add tokens in Security and leave Research on for a live panel."
                ),
            }
        )
        return panel, models_used, extra_recs

    for item in unique:
        provider = item["provider"]
        preferred = model_over if (model_over and (not prov_over or prov_over == provider)) else (
            (item.get("model") or "").strip() or None
        )
        live = chat(
            db,
            provider=provider,
            model=preferred,
            system=(
                "You are a writing-quality reviewer for security research notes. "
                "Detect AI-sounding prose and weak analyst voice. Be brief and direct. "
                "No em dashes, no AI filler. "
                "Do not invent facts about the topic content."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Local heuristic AI-likelihood score: {local_ai_pct}% "
                        f"(0=human, higher=more AI-like).\n\n"
                        "In under 120 words, answer:\n"
                        "1) AI-tell signals you notice (or none)\n"
                        "2) Does this read like a security analyst note? yes/no + why\n"
                        "3) One rewrite priority\n"
                        "4) End with: LIVE_AI_RISK: low|medium|high\n\n"
                        f"TEXT:\n{text[:8000]}"
                    ),
                }
            ],
            max_tokens=350,
            temperature=0.2,
            purpose="ai_check_live",
            created_by=user.username,
        )
        if live.content and not live.error:
            label = f"{provider}:{live.model}" if live.model else provider
            models_used.append(label)
            feedback = live.content.strip()
            risk = "medium"
            low = feedback.lower()
            if "live_ai_risk: low" in low:
                risk = "low"
            elif "live_ai_risk: high" in low:
                risk = "high"
            panel.append(
                {
                    "provider": provider,
                    "model": live.model or preferred or "default",
                    "ok": True,
                    "feedback": feedback[:900],
                    "live_ai_risk": risk,
                }
            )
            if risk == "high":
                extra_recs.append(
                    f"{provider} flags high AI-sounding risk. Humanize and hand-edit before publish."
                )
        else:
            panel.append(
                {
                    "provider": provider,
                    "model": preferred or "default",
                    "ok": False,
                    "feedback": (live.error or "unavailable")[:240],
                    "live_ai_risk": None,
                }
            )

    return panel, models_used, extra_recs


def _run_ai_check(
    *,
    db: Session,
    user: User,
    text: str,
    source_label: str,
    mode: str = "quick",
    max_live: int = 3,
    provider: str | None = None,
    model: str | None = None,
) -> AiCheckOut:
    mode_norm = (mode or "quick").strip().lower()
    if mode_norm not in {"quick", "live"}:
        mode_norm = "quick"

    result = score_ai_likelihood(text)
    live_panel: list[dict] = []
    models_used: list[str] = ["local"]
    used_live = False

    if mode_norm == "live":
        live_panel, models_used, extra_recs = _run_live_ai_panel(
            db,
            text=text,
            local_ai_pct=float(result["ai_pct"]),
            user=user,
            max_live=max_live,
            provider_override=provider,
            model_override=model,
        )
        used_live = any(p.get("ok") for p in live_panel if p.get("provider") != "none")
        if extra_recs:
            result["recommendations"] = list(result.get("recommendations") or []) + extra_recs

    sample = text[:500]
    signals = dict(result["signals"] or {})
    signals["check_mode"] = mode_norm
    if live_panel:
        signals["live_panel_count"] = len(live_panel)

    row = AiCheckResult(
        source_label=source_label if mode_norm == "quick" else f"{source_label}|live",
        text_sample=sample,
        ai_pct=result["ai_pct"],
        human_pct=result["human_pct"],
        signals_json=json.dumps(signals),
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
        signals=signals,
        recommendations=result["recommendations"],
        created_at=row.created_at,
        mode=mode_norm,
        used_live=used_live,
        models_used=models_used,
        live_panel=live_panel,
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
    panel: list[dict] = [
        {
            "role": "local_baseline",
            "provider": "local",
            "model": "heuristic",
            "ok": True,
            "feedback": result["feedback"][:500],
            "overall_score": result["overall_score"],
        }
    ]
    criteria = ", ".join(body.criteria or [])

    # Use up to 3 judge-enabled providers for multi-perspective review.
    for item in judge_providers[:3]:
        provider = item["provider"]
        preferred = (item.get("model") or "").strip() or None
        live = chat(
            db,
            provider=provider,
            model=preferred,
            system=(
                "You are a strict research judge for Security Operations writing aimed at "
                "security leaders. Focus on decision quality, evidence, residual risk, and "
                "whether this reads like analyst insight rather than a pentest ticket. "
                "Be direct. No em dashes or AI filler. "
                "End with a line: PUBLISH_READY: yes|no and SCORE: n/10."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Criteria: {criteria}\n\n"
                        f"Give short feedback: strengths, gaps, publish-ready yes/no, score /10, "
                        f"and one rewrite priority.\n\n"
                        f"TEXT:\n{body.text[:9000]}"
                    ),
                }
            ],
            max_tokens=700,
            purpose="judge",
            project_id=body.project_id,
            created_by=user.username,
        )
        if live.content and not live.error:
            models_used.append(f"{provider}:{live.model}" if live.model else provider)
            excerpt = live.content[:900]
            live_bits.append(f"**{provider}** (`{live.model or 'default'}`): {excerpt}")
            ready_hint = None
            low = live.content.lower()
            if "publish_ready: yes" in low or "publish-ready: yes" in low:
                ready_hint = True
            elif "publish_ready: no" in low or "publish-ready: no" in low:
                ready_hint = False
            panel.append(
                {
                    "role": "live_judge",
                    "provider": provider,
                    "model": live.model or preferred or "default",
                    "ok": True,
                    "feedback": excerpt,
                    "publish_ready_hint": ready_hint,
                }
            )
        else:
            err = (live.error or "unavailable")[:160]
            live_bits.append(f"**{provider}:** unavailable ({err})")
            panel.append(
                {
                    "role": "live_judge",
                    "provider": provider,
                    "model": preferred or "default",
                    "ok": False,
                    "feedback": err,
                    "publish_ready_hint": None,
                }
            )

    if live_bits:
        result["feedback"] = (
            f"{result['feedback']}\n\n### Live judge panel\n" + "\n\n".join(live_bits)
        )
    else:
        result["feedback"] = (
            f"{result['feedback']} No judge-enabled models active in Security. Local judge only."
        )

    live_ready = [p.get("publish_ready_hint") for p in panel if p.get("role") == "live_judge" and p.get("ok")]
    publish_ready_hint = None
    if live_ready:
        # unanimous yes -> True; any no -> False; else None
        if all(v is True for v in live_ready):
            publish_ready_hint = True
        elif any(v is False for v in live_ready):
            publish_ready_hint = False

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
        used_live=any(p.get("role") == "live_judge" and p.get("ok") for p in panel),
        panel=panel,
        publish_ready_hint=publish_ready_hint,
    )


@router.post("/export/docx")
def export_docx(
    body: ExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Convert markdown paper to Word and download.

    as_draft=true: paper-area download while writing (skip publish gate).
    force=true: admin override when gate blocks official export.
    """
    from app.services.evidence import analyze_evidence, publish_gate
    from app.services.app_settings import load_app_settings

    rules = load_app_settings()
    as_draft = bool(getattr(body, "as_draft", False))
    # Draft downloads from the paper editor always convert MD→DOCX without gate.
    if body.project_id and not body.force and not as_draft:
        project = db.query(Project).filter(Project.id == body.project_id).first()
        if project:
            evidence = analyze_evidence(body.content_md)
            ai = score_ai_likelihood(body.content_md)
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
                        "message": "Publish gate blocked export. Adjust content or use Download Word (draft) in the paper area.",
                        "publish_gate": gate,
                    },
                )
            project.publish_ready = True
            db.commit()
    if body.force and not as_draft and not rules.get("allow_force_export", True):
        raise HTTPException(status_code=403, detail="Force export is disabled in Settings.")

    from app.services.storage_paths import exports_dir

    data = markdown_to_docx_bytes(body.title, body.content_md)
    safe = re.sub(r"[^\w\-]+", "_", (body.title or "research").strip())[:48] or "research"
    suffix = "_draft" if as_draft else ""
    filename = f"{safe}{suffix}.docx"
    if body.project_id and not as_draft:
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
