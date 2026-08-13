"""Multi-agent research orchestration (desk Research Assistant).

Call chain:
  POST /api/research/assistant (routers/research.py)
    -> run_research_panel() here when multi_agent=true
    -> chat() in llm.py for each live role
    -> local_research_assist() if no research tokens

Roles (up to 3 research-enabled providers from Security):
  1) researcher  — first draft
  2) critic      — gaps, citations, residual risk
  3) red_team    — attacker / ATT&CK challenge
  4) synthesizer — merge into one paper section (reuses researcher provider)

Does not write the section body. UI must call /assistant/apply (or Apply to paper).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.ai_style import humanize_text, local_research_assist, strip_banned_style
from app.services.llm import chat, list_active_providers
from app.services.refs_cache import trusted_refs_snippet

# Shared system prompt for every live role. Style rules match product publish voice.
SYSTEM_BASE = (
    "You are a senior Security Operations research analyst. Focus on Offensive Security, "
    "Exposure Management, and Vulnerability Management. The user is shifting from hands-on "
    "testing work into research insight writing. Write for security leaders who need decisions, "
    "not exploit steps. Direct tone, contractions, varied sentence length. Never use em dashes, "
    "double hyphens, or semicolons. Avoid AI cliches. Prefer evidence, citations, MITRE ATT&CK "
    "and STRIDE framing, residual risk, and sequenced recommendations (do now / build next / stop). "
    "Translate testing patterns into buyer outcomes. Do not invent CVE counts or market share. "
    "Mark uncertainty. Keep claims tight and responsible. No exploit recipes."
)


def run_research_panel(
    db: Session,
    *,
    prompt: str,
    context_md: str = "",
    mode: str = "research",
    providers: list[str] | None = None,
    rewrite_human: bool = True,
    evidence_mode: bool = True,
) -> dict[str, Any]:
    """Main multi-model panel. Returns draft content + critique/red_team side panels.

    Returns keys used by desk: content, critique, red_team, used_live, notes, roles.
    """
    # Only tokens with Research enabled (Security tab).
    active = list_active_providers(db, purpose="research")
    available = {p["provider"] for p in active}
    requested = providers or ["openai", "anthropic", "xai"]
    chosen = [p for p in requested if p in available]
    if not chosen and active:
        chosen = [active[0]["provider"]]

    refs = trusted_refs_snippet()
    evidence_bit = (
        "Evidence mode is ON. Every substantive claim must include a source URL or citation tag "
        "like [source: title](url) or (Author, Year). Flag confidence as high/medium/low."
        if evidence_mode
        else ""
    )

    # Offline path: no research tokens — template scaffold only (research_scaffold.py).
    if not chosen:
        local = local_research_assist(prompt, context_md, rewrite_human=rewrite_human)
        local["providers_used"] = []
        local["roles"] = {}
        local["used_live"] = False
        local["critique"] = (
            "Local mode only. Add research-enabled tokens in Security for critic and red-team passes."
        )
        local["red_team"] = ""
        return local

    # Map roles to providers (1 key = all roles on same provider; 3 keys = one each).
    role_map = {
        "researcher": chosen[0],
        "critic": chosen[1] if len(chosen) > 1 else chosen[0],
        "red_team": chosen[2] if len(chosen) > 2 else chosen[0],
    }

    user_blob = (
        f"Research prompt:\n{prompt}\n\n"
        f"Existing section context:\n{context_md[:4000]}\n\n"
        f"Trusted reference anchors:\n{refs}\n\n{evidence_bit}"
    )

    roles_out: dict[str, Any] = {}
    errors: list[str] = []

    # Pass 1: researcher draft
    r = chat(
        db,
        provider=role_map["researcher"],
        system=SYSTEM_BASE + " Role: primary researcher. Produce structured markdown findings.",
        messages=[{"role": "user", "content": user_blob + "\n\nProduce a working research draft."}],
        purpose="research",
    )
    if r.error:
        errors.append(f"researcher/{r.provider}: {r.error}")
        draft = local_research_assist(prompt, context_md, rewrite_human=False)["content"]
        roles_out["researcher"] = {"provider": "local", "ok": False, "error": r.error}
    else:
        draft = r.content
        roles_out["researcher"] = {"provider": r.provider, "model": r.model, "ok": True}

    # Pass 2: critic (accuracy, citations, residual risk)
    c = chat(
        db,
        provider=role_map["critic"],
        system=SYSTEM_BASE + " Role: critic/judge. Stress accuracy, citations, ethics, residual risk.",
        messages=[
            {
                "role": "user",
                "content": (
                    f"Critique this draft. List gaps, weak claims, missing MITRE/STRIDE coverage, "
                    f"and required fixes.\n\nDRAFT:\n{draft[:8000]}"
                ),
            }
        ],
        purpose="research_critic",
    )
    critique = c.content if not c.error else "Critic unavailable. Review citations and residual risk manually."
    if c.error:
        errors.append(f"critic/{c.provider}: {c.error}")
        roles_out["critic"] = {"provider": role_map["critic"], "ok": False, "error": c.error}
    else:
        roles_out["critic"] = {"provider": c.provider, "model": c.model, "ok": True}

    # Pass 3: red team (attack paths / ATT&CK pressure)
    rt = chat(
        db,
        provider=role_map["red_team"],
        system=SYSTEM_BASE + " Role: offensive red-team reviewer. Focus on attack paths and bypasses.",
        messages=[
            {
                "role": "user",
                "content": (
                    f"From an attacker perspective, challenge the controls and assumptions in this draft. "
                    f"Map likely ATT&CK techniques.\n\nDRAFT:\n{draft[:6000]}\n\nCRITIQUE:\n{critique[:3000]}"
                ),
            }
        ],
        purpose="research_red_team",
    )
    red = rt.content if not rt.error else "Red-team pass unavailable."
    if rt.error:
        errors.append(f"red_team/{rt.provider}: {rt.error}")
        roles_out["red_team"] = {"provider": role_map["red_team"], "ok": False, "error": rt.error}
    else:
        roles_out["red_team"] = {"provider": rt.provider, "model": rt.model, "ok": True}

    # Pass 4: synthesizer merges draft + critique + red team into one section
    synth = chat(
        db,
        provider=role_map["researcher"],
        system=SYSTEM_BASE + " Role: synthesizer. Merge draft, critique, and red-team into one paper section.",
        messages=[
            {
                "role": "user",
                "content": (
                    f"Mode: {mode}\nPrompt: {prompt}\n\n"
                    f"Merge into a single markdown research section with headings:\n"
                    f"Summary, Decision framing, Threat framing (MITRE/STRIDE), Findings, "
                    f"Options and tradeoffs, Residual risk, Recommendations (now/next/stop), "
                    f"Open questions, References.\n"
                    f"Every substantive claim needs a source or explicit [source needed].\n\n"
                    f"DRAFT:\n{draft[:7000]}\n\nCRITIQUE:\n{critique[:3500]}\n\nRED TEAM:\n{red[:3500]}"
                ),
            }
        ],
        purpose="research_synth",
    )
    if synth.error or not synth.content.strip():
        content = (
            f"## Research notes\n\n{draft}\n\n## Critic notes\n\n{critique}\n\n"
            f"## Red-team notes\n\n{red}\n"
        )
        if synth.error:
            errors.append(f"synth/{synth.provider}: {synth.error}")
    else:
        content = synth.content

    # Local style cleanup only (not a second live rewrite).
    content = strip_banned_style(content)
    if rewrite_human:
        content = humanize_text(content, strength="medium")

    notes = "Live multi-agent panel completed."
    if errors:
        notes = "Completed with fallbacks: " + " | ".join(errors[:4])

    return {
        "content": content,  # main Assistant draft text
        "agent_chars": len(content),  # length only; apply endpoint owns contribution ledger
        "notes": notes,
        "citations": _extract_link_citations(content),
        "providers_used": sorted({role_map[k] for k in role_map}),
        "roles": roles_out,
        "used_live": True,
        "critique": critique,  # shown on desk under Critic
        "red_team": red,  # shown on desk under Red team
    }


def run_single_role(
    db: Session,
    *,
    provider: str,
    role: str,
    prompt: str,
    context_md: str = "",
) -> dict[str, Any]:
    """One-shot live call (multi_agent=false). Falls back to local scaffold on failure."""
    system = SYSTEM_BASE + f" Role: {role}."
    result = chat(
        db,
        provider=provider,
        system=system,
        messages=[
            {
                "role": "user",
                "content": f"Context:\n{context_md[:5000]}\n\nTask:\n{prompt}",
            }
        ],
    )
    if result.error or not result.content:
        fallback = local_research_assist(prompt, context_md, rewrite_human=True)
        return {
            **fallback,
            "used_live": False,
            "provider": provider,
            "error": result.error,
        }
    content = humanize_text(strip_banned_style(result.content), strength="medium")
    return {
        "content": content,
        "agent_chars": len(content),
        "notes": f"Live {provider} ({result.model})",
        "citations": _extract_link_citations(content),
        "used_live": True,
        "provider": provider,
        "model": result.model,
    }


def _extract_link_citations(text: str) -> list[dict[str, str]]:
    """Pull markdown [title](url) links from generated text for the response payload."""
    import re

    cites = []
    for match in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", text):
        cites.append({"title": match.group(1), "url": match.group(2), "note": "inline"})
    seen = set()
    out = []
    for c in cites:
        key = c["url"]
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out[:30]
