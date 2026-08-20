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
from app.services.research_scaffold import (
    has_linked_sources,
    looks_broken_brief_structure,
    looks_unfilled_template,
    wants_deep_framing,
)

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

    linked = has_linked_sources(context_md)
    deep = wants_deep_framing(prompt, context_md)
    # Linked-source briefs can be long; keep more context than a normal section snippet.
    context_limit = 12000 if linked else 4000
    user_blob = (
        f"Research prompt:\n{prompt}\n\n"
        f"Existing section context:\n{context_md[:context_limit]}\n\n"
        f"Trusted reference anchors:\n{refs}\n\n{evidence_bit}"
    )

    if linked and deep:
        draft_shape = (
            "Write a source-driven research note with: takeaway, what the source says, "
            "analyst read (not press copy), vendor claims vs evidence, residual risk, "
            "recommendations (now/next/stop), open questions, references. "
            "Also include applied threat/program framing (only ATT&CK/STRIDE items this story "
            "actually implies — no generic technique laundry lists). "
            "Do not copy Operator instructions or paste the raw linked brief."
        )
    elif linked:
        draft_shape = (
            "Write a RESEARCH-PAPER SOURCE NOTE filled from "
            "'## Linked sources (fetched from Research prompt URLs)' only. "
            "Goal: help the user cite and discuss this article in an exposure-management / CTEM paper "
            "(especially mergers and how they could change how people run EM), NOT a risk-rating memo. "
            "Required filled headings: Why this source matters for the paper; Article synopsis "
            "(5-8 plain factual bullets); Figures and claims to handle carefully (attribute to press/"
            "vendor, no confidence-score theater); Implications for how people run exposure management; "
            "How to use this in the draft; Open questions for further research; Reference URL. "
            "Never leave italic placeholders. Never emit duplicate '## Summary' or headers inside bullets. "
            "Ignore '## Section paper in progress' unless the ask says to revise it."
        )
    else:
        draft_shape = (
            "Produce a working research draft in markdown with decision framing, findings, "
            "residual risk, and sequenced recommendations. "
            "Never reply that the draft is empty — write the draft yourself from the prompt and context."
        )

    roles_out: dict[str, Any] = {}
    errors: list[str] = []

    # Pass 1: researcher draft
    r = chat(
        db,
        provider=role_map["researcher"],
        system=SYSTEM_BASE + " Role: primary researcher. Produce structured markdown findings.",
        messages=[
            {
                "role": "user",
                "content": user_blob + "\n\n" + draft_shape,
            }
        ],
        purpose="research",
    )
    draft = (r.content or "").strip() if not r.error else ""
    bad_draft = (
        r.error
        or len(draft) < 80
        or looks_unfilled_template(draft)
        or looks_broken_brief_structure(draft)
    )
    if bad_draft:
        if r.error:
            errors.append(f"researcher/{r.provider}: {r.error}")
        elif not draft:
            errors.append("researcher: empty draft")
        elif looks_broken_brief_structure(draft):
            errors.append("researcher: nested/duplicate summary headers; used filled local brief")
        elif looks_unfilled_template(draft):
            errors.append("researcher: unfilled template shell; used filled local source brief")
        else:
            errors.append("researcher: draft too short; used local scaffold")
        local_draft = local_research_assist(prompt, context_md, rewrite_human=False)["content"]
        # Prefer filled local brief over an instructional/broken shell from the model.
        if local_draft and not looks_unfilled_template(local_draft) and not looks_broken_brief_structure(
            local_draft
        ):
            draft = local_draft.strip()
        else:
            draft = (local_draft or "").strip() or draft
        roles_out["researcher"] = {
            "provider": "local",
            "ok": False,
            "error": r.error or "empty_short_unfilled_or_broken_structure",
        }
    else:
        roles_out["researcher"] = {"provider": r.provider, "model": r.model, "ok": True}

    critique = ""
    red = ""

    # Skip critic/red-team/synth when there is still no usable draft — avoids rubric-only spam.
    if len(draft) < 80:
        content = (
            "## Could not produce a research draft\n\n"
            "The live researcher returned little or no text, and the local fallback was also thin. "
            "Check research-enabled API keys in Security, or paste source text into the prompt "
            "(especially if a linked URL failed to fetch).\n\n"
            f"### Prompt\n{prompt[:1500]}\n"
        )
        notes = "Research panel stopped early: empty draft."
        if errors:
            notes += " " + " | ".join(errors[:4])
        return {
            "content": content,
            "agent_chars": len(content),
            "notes": notes,
            "citations": [],
            "providers_used": sorted({role_map[k] for k in role_map}),
            "roles": roles_out,
            "used_live": True,
            "critique": "",
            "red_team": "",
        }

    # Pass 2: critic (accuracy, citations, residual risk)
    if linked and not deep:
        critic_ask = (
            "Critique this research-paper source note. Focus on whether it helps write about "
            "the article's implications for exposure management practice: missing synopsis facts, "
            "missing dates, unattributed press metrics, weak 'so what for EM programs', or "
            "turning into a risk-scorecard instead of a usable paper note. "
            "Do NOT demand residual-risk scorecards, evidence tables as homework, or full MITRE "
            "templates. Keep critique under ~220 words.\n\n"
            f"DRAFT:\n{draft[:8000]}"
        )
    else:
        critic_ask = (
            "Critique this draft. List gaps, weak claims, missing MITRE/STRIDE coverage where "
            "it would change the recommendation, and required fixes. Do not dump a blank rubric. "
            "If somehow empty, say EMPTY_DRAFT in one line.\n\n"
            f"DRAFT:\n{draft[:8000]}"
        )
    c = chat(
        db,
        provider=role_map["critic"],
        system=SYSTEM_BASE + " Role: critic/judge. Stress accuracy, citations, ethics, residual risk.",
        messages=[{"role": "user", "content": critic_ask}],
        purpose="research_critic",
    )
    critique = c.content if not c.error else "Critic unavailable. Review citations and residual risk manually."
    if c.error:
        errors.append(f"critic/{c.provider}: {c.error}")
        roles_out["critic"] = {"provider": role_map["critic"], "ok": False, "error": c.error}
    else:
        roles_out["critic"] = {"provider": c.provider, "model": c.model, "ok": True}
    if "EMPTY_DRAFT" in (critique or "") and len(critique) < 80:
        critique = "Critic skipped: draft was empty."

    # Pass 3: red team (skip on short news briefs — usually noise without attack-path depth)
    if linked and not deep:
        red = ""
        roles_out["red_team"] = {"provider": "skipped", "ok": True, "note": "skipped_short_source_brief"}
    else:
        rt = chat(
            db,
            provider=role_map["red_team"],
            system=SYSTEM_BASE + " Role: offensive red-team reviewer. Focus on attack paths and bypasses.",
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"From an attacker perspective, challenge the controls and assumptions in this draft. "
                        f"Map likely ATT&CK techniques that actually matter here.\n\n"
                        f"DRAFT:\n{draft[:6000]}\n\nCRITIQUE:\n{critique[:3000]}"
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
    if linked and not deep:
        synth_shape = (
            "Merge into one RESEARCH-PAPER SOURCE NOTE with headings:\n"
            "Why this source matters for the paper; Article synopsis; Figures and claims to handle "
            "carefully; Implications for how people run exposure management; How to use this in the "
            "draft; Open questions for further research; Reference.\n"
            "Write for citing a merger/news article in an EM/CTEM paper. Do not turn it into a "
            "risk-rating memo or confidence scorecard. "
            "Formatting rules: one top-level title only; never emit '## Summary' twice; "
            "never put headers inside a bullet; each bullet is one plain sentence. "
            "Do not paste Operator instructions.\n"
        )
    elif linked and deep:
        synth_shape = (
            "Merge into one research-paper source note with headings:\n"
            "Why this source matters; Article synopsis; Figures/claims to handle carefully; "
            "Implications for exposure management practice; Applied threat/program framing; "
            "How to use in the draft; Open questions; Reference.\n"
            "Formatting rules: no duplicate '## Summary'; no headers nested inside bullets. "
            "Only include ATT&CK/STRIDE items that apply to this story.\n"
        )
    else:
        synth_shape = (
            "Merge into a single markdown research section with headings:\n"
            "Summary, Decision framing, Threat framing (MITRE/STRIDE), Findings, "
            "Options and tradeoffs, Residual risk, Recommendations (now/next/stop), "
            "Open questions, References.\n"
        )
    synth = chat(
        db,
        provider=role_map["researcher"],
        system=SYSTEM_BASE + " Role: synthesizer. Merge draft, critique, and red-team into one paper section.",
        messages=[
            {
                "role": "user",
                "content": (
                    f"Mode: {mode}\nPrompt: {prompt}\n\n"
                    f"{synth_shape}"
                    f"Every substantive claim needs a source or explicit [source needed].\n"
                    f"Write the section itself. Do not say the draft is empty.\n\n"
                    f"DRAFT:\n{draft[:7000]}\n\nCRITIQUE:\n{critique[:3500]}\n\nRED TEAM:\n{red[:3500]}"
                ),
            }
        ],
        purpose="research_synth",
    )
    synth_text = (synth.content or "").strip()
    if synth.error or not synth_text:
        content = draft
        if synth.error:
            errors.append(f"synth/{synth.provider}: {synth.error}")
    elif looks_broken_brief_structure(synth_text) or looks_unfilled_template(synth_text):
        content = draft
        errors.append("synth: broken/nested headers; kept researcher draft")
    else:
        content = synth_text

    # Local style cleanup only (not a second live rewrite).
    content = strip_banned_style(content)
    if rewrite_human:
        # Markdown-aware humanize preserves headers/bullets/newlines.
        content = humanize_text(content, strength="medium")
    # Drop invented "Extra framing" unless the user asked for depth.
    if linked and not deep and "### Extra framing" in content:
        content = content.split("### Extra framing", 1)[0].rstrip() + "\n"
    # Final guard: if cleanup somehow reintroduced broken structure, fall back again.
    if looks_broken_brief_structure(content) and draft and not looks_broken_brief_structure(draft):
        content = draft
        errors.append("postprocess: reverted broken structure to researcher draft")

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
