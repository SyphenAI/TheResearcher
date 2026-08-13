"""Evidence scanning + publish gate rules.

analyze_evidence() — find claim-like sentences missing citations (desk Evidence check).
publish_gate() — ready/blocked from agent %, AI %, evidence coverage (Settings thresholds).
Used by workspace evidence endpoints and export/docx gate in research.py.
"""

from __future__ import annotations

import re
from typing import Any

CLAIM_HINTS = re.compile(
    r"\b(is|are|was|were|shows|proves|reduces|increases|always|never|must|critical|severe)\b",
    re.I,
)
CITATION_PATTERNS = [
    re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)"),
    re.compile(r"\(https?://[^)]+\)"),
    re.compile(r"https?://\S+"),
    re.compile(r"\([A-Z][A-Za-z]+(?:\s+et\s+al\.)?,?\s+\d{4}\)"),
    re.compile(r"\[\d+\]"),
]


def evidence_stub_for_claim(
    claim_text: str,
    *,
    title: str = "Source title",
    url: str = "https://",
    confidence: str = "medium",
) -> str:
    """Markdown insert for an uncited claim."""
    from app.services.research_scaffold import claim_evidence_stub

    return claim_evidence_stub(claim_text, title=title, url=url, confidence=confidence)


def blocker_actions(blockers: list[str]) -> list[dict[str, str]]:
    """Map publish blockers to concrete desk actions."""
    actions: list[dict[str, str]] = []
    for b in blockers or []:
        text = str(b)
        low = text.lower()
        if "agent contribution" in low:
            actions.append(
                {
                    "blocker": text,
                    "action": "Edit the paper by hand or Accept only humanized text so human contribution rises.",
                    "desk_hint": "human_edit",
                }
            )
        elif "evidence coverage" in low or "uncited" in low:
            actions.append(
                {
                    "blocker": text,
                    "action": "Run Evidence check, insert evidence notes on red claims, or soften absolute language.",
                    "desk_hint": "evidence",
                }
            )
        elif "ai checker" in low or "ai-likeness" in low or "ai likelihood" in low:
            actions.append(
                {
                    "blocker": text,
                    "action": "Run Humanize, review the red/green diff, Accept, then hand-edit in your voice.",
                    "desk_hint": "humanize",
                }
            )
        else:
            actions.append(
                {
                    "blocker": text,
                    "action": "Open Settings publish rules or revise the section content.",
                    "desk_hint": "settings",
                }
            )
    return actions


def analyze_evidence(text: str) -> dict[str, Any]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    claims = []
    cited = 0
    uncited = 0
    for i, line in enumerate(lines):
        if line.startswith("#") or line.startswith("```") or line.startswith(">"):
            continue
        if len(line) < 40:
            continue
        if not CLAIM_HINTS.search(line):
            continue
        has_cite = any(p.search(line) for p in CITATION_PATTERNS)
        item = {
            "line": i + 1,
            "text": line[:280],
            "has_citation": has_cite,
            "confidence": "medium" if has_cite else "low",
            "insert_snippet": ""
            if has_cite
            else evidence_stub_for_claim(line[:200], confidence="low"),
        }
        claims.append(item)
        if has_cite:
            cited += 1
        else:
            uncited += 1

    try:
        from app.services.app_settings import load_app_settings

        min_cov = float(load_app_settings().get("evidence_coverage_min_pct", 70.0))
    except Exception:  # noqa: BLE001
        min_cov = 70.0

    total = max(len(claims), 1)
    coverage = round(100.0 * cited / total, 1) if claims else 100.0
    recommendations = []
    if uncited:
        recommendations.append(
            f"{uncited} claim-like lines lack citations. Use Insert evidence note on each, or soften language."
        )
    if coverage < min_cov:
        recommendations.append(
            f"Evidence coverage is under {min_cov}%. Tighten claims or attach primary sources."
        )
    if not recommendations:
        recommendations.append("Evidence coverage looks solid. Spot-check URLs still resolve.")

    uncited_claims = [c for c in claims if not c["has_citation"]]
    return {
        "claim_count": len(claims),
        "cited_count": cited,
        "uncited_count": uncited,
        "coverage_pct": coverage if claims else 100.0,
        "claims": claims[:80],
        "uncited_claims": uncited_claims[:40],
        "recommendations": recommendations,
        "pass_threshold": (not claims)
        or (coverage >= min_cov and uncited <= max(2, len(claims) // 5)),
        "min_coverage_pct": min_cov,
    }


def format_citation(style: str, title: str, url: str = "", author: str = "", year: str = "") -> str:
    style = (style or "apa").lower()
    author = author or "Author"
    year = year or "n.d."
    title = title or "Untitled"
    if style == "mla":
        core = f'{author}. "{title}."'
        return f"{core} {url}" if url else core
    if style == "chicago":
        core = f'{author}. "{title}." Accessed {year}.'
        return f"{core} {url}" if url else core
    # apa default
    core = f"{author} ({year}). {title}."
    return f"{core} {url}" if url else core


def publish_gate(
    *,
    agent_pct: float,
    max_agent_pct: float | None = None,
    evidence: dict[str, Any] | None = None,
    ai_pct: float | None = None,
    max_ai_checker_pct: float | None = None,
    evidence_coverage_min_pct: float | None = None,
    enforce_publish_gate: bool | None = None,
    require_citations_for_publish: bool | None = None,
) -> dict[str, Any]:
    """Evaluate publish readiness using global app rules when not overridden."""
    try:
        from app.services.app_settings import load_app_settings

        rules = load_app_settings()
    except Exception:  # noqa: BLE001
        rules = {
            "max_agent_pct": 10.0,
            "max_ai_checker_pct": 10.0,
            "evidence_coverage_min_pct": 70.0,
            "enforce_publish_gate": True,
            "require_citations_for_publish": True,
        }

    max_agent = float(max_agent_pct if max_agent_pct is not None else rules["max_agent_pct"])
    max_ai = float(
        max_ai_checker_pct if max_ai_checker_pct is not None else rules["max_ai_checker_pct"]
    )
    min_evidence = float(
        evidence_coverage_min_pct
        if evidence_coverage_min_pct is not None
        else rules["evidence_coverage_min_pct"]
    )
    enforce = (
        rules["enforce_publish_gate"]
        if enforce_publish_gate is None
        else bool(enforce_publish_gate)
    )
    require_cites = (
        rules["require_citations_for_publish"]
        if require_citations_for_publish is None
        else bool(require_citations_for_publish)
    )

    if not enforce:
        return {
            "ready": True,
            "blockers": [],
            "actions": [],
            "max_agent_pct": max_agent,
            "max_ai_checker_pct": max_ai,
            "agent_pct": agent_pct,
            "ai_pct": ai_pct,
            "enforced": False,
            "message": "Publish gate is disabled in Settings.",
        }

    blockers = []
    if agent_pct > max_agent:
        blockers.append(f"Agent contribution {agent_pct}% exceeds target {max_agent}%.")
    if evidence is not None and require_cites:
        coverage = float(evidence.get("coverage_pct") or 0)
        uncited = int(evidence.get("uncited_count") or 0)
        claims = int(evidence.get("claim_count") or 0)
        if claims and coverage < min_evidence:
            blockers.append(
                f"Evidence coverage {coverage}% is under the {min_evidence}% minimum."
            )
        if uncited > max(2, claims // 5 if claims else 0):
            blockers.append(f"Too many uncited claims ({uncited}). Add sources or soften claims.")
    if ai_pct is not None and ai_pct >= max_ai:
        blockers.append(f"AI checker likelihood {ai_pct}% is at or above {max_ai}%.")
    actions = blocker_actions(blockers)
    return {
        "ready": len(blockers) == 0,
        "blockers": blockers,
        "actions": actions,
        "max_agent_pct": max_agent,
        "max_ai_checker_pct": max_ai,
        "evidence_coverage_min_pct": min_evidence,
        "agent_pct": agent_pct,
        "ai_pct": ai_pct,
        "enforced": True,
        "message": "Ready to export." if not blockers else f"{len(blockers)} publish blocker(s).",
    }
