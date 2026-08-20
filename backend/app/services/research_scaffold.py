"""Offline research scaffolds (no API cost).

Entry: build_local_scaffold() via ai_style.local_research_assist when the
Research Assistant has no live research tokens (or a live role fails).

detect_domain() picks a skeleton: offensive | exposure | vuln | saas |
tester_analyst | general. Output is markdown headings for the desk draft.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.ai_style import humanize_text, strip_banned_style
from app.services.refs_cache import trusted_refs_snippet


def detect_domain(prompt: str, context_md: str = "") -> str:
    """Keyword score -> best domain label for scaffold sections."""
    text = f"{prompt}\n{context_md}".lower()
    scores = {
        "offensive": len(
            re.findall(
                r"\b(offens|pentest|pen test|red team|purple|bas|aev|adversarial exposure|"
                r"breach and attack|control validation)\b",
                text,
            )
        ),
        "exposure": len(
            re.findall(
                r"\b(exposure|attack surface|asm|easm|internet[- ]facing|external asset|"
                r"shadow it|cloud posture|caasm)\b",
                text,
            )
        ),
        "vuln": len(
            re.findall(
                r"\b(vulnerab|cve|patch|sla|remediat|vm program|scanner|epss|kev|"
                r"exception debt)\b",
                text,
            )
        ),
        "saas": len(
            re.findall(
                r"\b(saas|vendor|cmek|byok|sso|scim|control review|casb)\b",
                text,
            )
        ),
        "tester_analyst": len(
            re.findall(
                r"\b(tester to analyst|from testing|hands[- ]on|career|gartner|"
                r"research note|analyst voice)\b",
                text,
            )
        ),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def evidence_checklist_md(topic: str = "") -> str:
    """Markdown checklist inserted from desk Evidence tools."""
    topic_bit = f" for **{topic}**" if topic.strip() else ""
    return (
        f"## Evidence checklist{topic_bit}\n\n"
        "- [ ] Claim is specific enough to falsify\n"
        "- [ ] Primary source linked (vendor docs, ATT&CK, standard, telemetry, interview)\n"
        "- [ ] Confidence marked (high / medium / low)\n"
        "- [ ] Residual risk stated after control options\n"
        "- [ ] Recommendation is sequenced (now / next / stop)\n"
        "- [ ] No invented CVE counts, win rates, or market share numbers\n"
        "- [ ] Written for a security leader decision, not a ticket queue\n"
        "- [ ] Buyer question answered in plain language\n"
    )


def analyst_voice_notes() -> str:
    return (
        "### Voice shift: tester to analyst\n"
        "Write for decisions, not for exploit steps. Translate hands-on testing experience into:\n"
        "- what buyers struggle to prioritize\n"
        "- which validation methods change outcomes\n"
        "- where programs waste spend\n"
        "- residual risk after tooling and process\n"
        "Keep tradecraft high-level and responsible. No exploit recipes. No client-identifying detail.\n"
    )


def buyer_questions_md(domain: str) -> str:
    common = [
        "What decision is blocked if we publish nothing?",
        "What would a CISO or SecOps lead do differently in 90 days?",
        "What should we stop buying or stop measuring?",
    ]
    by_domain = {
        "offensive": [
            "When is pen testing enough, and when do you need continuous validation?",
            "How do BAS / AEV change residual risk versus annual tests?",
            "What detection gaps would a purple team expose that scanners miss?",
        ],
        "exposure": [
            "Who owns internet-facing assets when discovery finds shadow services?",
            "How do we rank exposures by exploitability and business blast radius?",
            "What loop closes the gap between discovery and remediation?",
        ],
        "vuln": [
            "Which CVEs matter for this environment, not just for the industry?",
            "Are SLAs realistic given exception debt and change windows?",
            "What executive metric replaces raw open-vuln counts?",
        ],
        "saas": [
            "Which control gaps create material residual risk for this data class?",
            "Is compensating control evidence strong enough for audit and operations?",
            "What is the exit or contingency path if the vendor fails a control?",
        ],
        "tester_analyst": [
            "What pattern did hands-on testing reveal that pure market research misses?",
            "How do I turn a finding class into a program recommendation?",
            "What evidence would a peer analyst demand before publishing?",
        ],
        "general": [
            "What is the leadership decision this note must unlock?",
            "What uncertainty remains after the best available evidence?",
        ],
    }
    qs = common + by_domain.get(domain, by_domain["general"])
    lines = "\n".join(f"- {q}" for q in qs)
    return f"### Buyer and leadership questions\n{lines}\n"


def has_linked_sources(context_md: str = "") -> bool:
    return "Linked sources (fetched from Research prompt URLs)" in (context_md or "")


def wants_deep_framing(prompt: str, context_md: str = "") -> bool:
    """Expand ATT&CK / program framing when the ask is technical, not a thin news brief.

    Explicit triggers: 'full framing', 'with ATT&CK', 'attack path', etc.
    Also expands for offensive/vuln-heavy prompts. Pure vendor-acquisition news stays short
    unless the user asks for depth.
    """
    text = f"{prompt}\n{context_md}".lower()
    if re.search(
        r"\b(full framing|with att&ck|with mitre|attack path|threat framing|"
        r"deep dive|full analysis|include stride)\b",
        text,
    ):
        return True
    # Vendor/news-heavy → prefer short unless user forced depth above.
    news_hits = len(
        re.findall(
            r"\b(acquire|acquired|acquires|acquiring|acquisition|merger|merge|bookings|"
            r"magic quadrant|press release|customers?(?:\s+across)?|yo[uy] growth|"
            r"asp|arr|funding|vendor)\b",
            text,
        )
    )
    tech_hits = len(
        re.findall(
            r"\b(attack path|att&ck|t1\d{3}|lateral|exploit|control validation|"
            r"bas\b|aev\b|remediat|retest|ctem loop|exposure priorit)\b",
            text,
        )
    )
    # Merger/news articles stay on the short research-paper note unless the user
    # explicitly asks for depth (even if the press copy mentions CTEM/exposure).
    if news_hits >= 1 and not re.search(
        r"\b(full framing|with att&ck|with mitre|attack path|threat framing|"
        r"deep dive|full analysis|include stride)\b",
        text,
    ):
        return False
    if news_hits >= 2 and tech_hits == 0:
        return False
    domain = detect_domain(prompt, context_md)
    if domain in {"offensive", "vuln"}:
        return True
    if domain == "exposure" and tech_hits > 0:
        return True
    return tech_hits >= 2


def looks_unfilled_template(text: str) -> bool:
    """True when a draft is still instructional placeholders, not analysis."""
    body = text or ""
    if len(body.strip()) < 80:
        return True
    markers = (
        "_One sentence:",
        "_3–5 factual",
        "_Separate marketing",
        "_What remains true",
        "_Deal terms, integration",
        "_Cite the linked source",
        "Linked source material (do not paste raw)",
        "Suggested section skeleton",
        "Working outline",
        "Draft response starter",
    )
    hits = sum(1 for m in markers if m in body)
    italic_hints = len(re.findall(r"_[^_\n]{18,}_", body))
    return hits >= 2 or italic_hints >= 3


def looks_broken_brief_structure(text: str) -> bool:
    """True when nested summary markdown leaked into the draft."""
    body = text or ""
    if body.count("## Summary") >= 2:
        return True
    # Headers embedded inside list items (e.g. "- ### Key points ...")
    if re.search(r"(?m)^\s*[-*]\s+#{1,6}\s+", body):
        return True
    if re.search(r"(?m)^\s*[-*].{0,40}###\s+(Key points|Open questions|Analyst prompt)", body, re.I):
        return True
    # Nested heading crumbs mid-bullet
    if re.search(r"(?m)^\s*[-*].*(##\s+Summary|###\s+Key points)", body):
        return True
    return False


def _flatten_brief_body(text: str) -> str:
    """Remove nested markdown headings from linked-brief bodies before extraction."""
    from app.services.summarize import flatten_summary_to_bullets

    bullets = flatten_summary_to_bullets(text or "", limit=12)
    if bullets:
        return " ".join(bullets)
    cleaned = re.sub(r"(?m)^#{1,6}\s+.*$", " ", text or "")
    cleaned = re.sub(r"[#*_`]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_linked_blocks(context_md: str) -> list[dict[str, str]]:
    """Parse linked-source brief blocks from assistant context."""
    raw = context_md or ""
    # Prefer the linked-sources section only (ignore section paper / operator notes).
    if "## Linked sources (fetched from Research prompt URLs)" in raw:
        raw = raw.split("## Linked sources (fetched from Research prompt URLs)", 1)[1]
    if "## Operator instructions" in raw:
        # Operator may appear before linked sources; already split above when possible.
        pass
    chunks = re.split(r"\n(?=### )", raw)
    out: list[dict[str, str]] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("### "):
            continue
        lines = chunk.splitlines()
        title = lines[0][4:].strip()
        url = ""
        body_lines: list[str] = []
        for line in lines[1:]:
            if line.lower().startswith("source:"):
                url = line.split(":", 1)[1].strip()
                continue
            if line.lower().startswith("fetched via:"):
                continue
            body_lines.append(line)
        body = "\n".join(body_lines).strip()
        if title or body:
            out.append({"title": title, "url": url, "body": body})
    return out


def _fact_bullets_from_text(text: str, *, limit: int = 5) -> list[str]:
    """Extractive bullets; prefer sentences with numbers, names, or acquisition verbs."""
    flat = _flatten_brief_body(text)
    body = re.sub(r"\s+", " ", flat or "").strip()
    if not body:
        return []
    parts = re.split(r"(?<=[.!?])\s+", body)
    scored: list[tuple[float, int, str]] = []
    for i, s in enumerate(parts[:60]):
        s = s.strip(" -•\t")
        s = re.sub(r"^#{1,6}\s+", "", s).strip()
        if len(s) < 35 or len(s) > 280:
            continue
        if re.search(r"(?i)^(summary|key points|open questions|analyst prompt)\b", s):
            continue
        low = s.lower()
        score = 0.0
        if re.search(r"\d", s):
            score += 2.0
        if re.search(r"\b(acquir|merger|customer|gartner|ctem|exposure|plextrac|brinqa)\b", low):
            score += 2.5
        if re.search(r"\b(largest|growth|percent|%|million|billion)\b", low):
            score += 1.5
        if "http" in low or "source:" in low:
            score -= 2.0
        if "#" in s:
            score -= 3.0
        score += max(0.0, 1.5 - i * 0.03)
        scored.append((score, i, s))
    scored.sort(key=lambda t: (-t[0], t[1]))
    picks = sorted(scored[:limit], key=lambda t: t[1])
    return [p[2] for p in picks]


def _press_figures(text: str) -> list[str]:
    """Useful figures/claims from press copy, labeled as reported (not risk-scored)."""
    flat = _flatten_brief_body(text)
    lines: list[str] = []
    for sent in re.split(r"(?<=[.!?])\s+", flat or ""):
        s = sent.strip(" -•\t")
        s = re.sub(r"^#{1,6}\s+", "", s).strip()
        if len(s) < 25 or len(s) > 260 or "#" in s:
            continue
        low = s.lower()
        if re.search(
            r"\b(largest|leading|%\b|percent|customers|fortune|countries|bookings|"
            r"asp|arr|magic quadrant|closes the ctem|acquir|merger)\b",
            low,
        ):
            lines.append(f"- Reported in source: {s}")
        if len(lines) >= 5:
            break
    if not lines:
        lines.append("- No standout figures auto-extracted; pull quotes/numbers manually from the article.")
    return lines


def _em_implications(text: str, title: str = "") -> str:
    """How a merger/news item could change exposure-management practice (for paper writing)."""
    low = f"{title}\n{text}".lower()
    bits: list[str] = []
    if re.search(r"\b(acquir|merger|plextrac|brinqa|validation|pentest|ctem)\b", low):
        bits.append(
            "If prioritization/aggregation platforms absorb validation or pentest-reporting tools, "
            "buyers may expect one workflow from exposure ranking through fix proof and retest, "
            "instead of separate scanner, ASM, and assessment stacks."
        )
        bits.append(
            "Program design pressure shifts toward proving a finding can travel discover → prioritize → "
            "validate/remediate → retest inside one operating model, not only sharing a dashboard."
        )
        bits.append(
            "Consolidation can reduce tool sprawl, but it also raises questions about migration of "
            "assessment data, role changes between VM/EM and offensive testing teams, and whether "
            "'closed loop' messaging outruns real process change."
        )
    else:
        bits.append(
            "Use this article to show how market moves are reshaping the exposure-management operating "
            "model buyers are sold, then contrast that narrative with how programs actually run today."
        )
    return "\n".join(f"- {b}" for b in bits)


def build_linked_source_draft(
    prompt: str,
    context_md: str = "",
    rewrite_human: bool = True,
) -> dict[str, Any]:
    """Research-paper source note from a linked article (optional deep framing).

    Default is summary + implications for writing, not a risk-rating scorecard.
    """
    prompt = prompt.strip()
    deep = wants_deep_framing(prompt, context_md)
    domain = detect_domain(prompt, context_md)
    blocks = _extract_linked_blocks(context_md)
    primary = blocks[0] if blocks else {"title": "Linked source", "url": "", "body": ""}
    combined = "\n\n".join((b.get("body") or "").strip() for b in blocks if (b.get("body") or "").strip())
    if not combined.strip():
        combined = context_md or ""

    facts = _fact_bullets_from_text(combined, limit=6)
    if not facts:
        facts = [
            "Linked source text was thin or unreadable. Paste the article body into the prompt and re-run."
        ]
    fact_md = "\n".join(f"- {f}" for f in facts)
    figures_md = "\n".join(_press_figures(combined))
    title = primary.get("title") or "Linked source"
    url = primary.get("url") or ""
    cite = f"[{title}]({url})" if url else title

    # If the prompt is only the URL, don't echo it as the writing ask.
    from app.services.summarize import URL_RE, extract_urls

    writing_ask = prompt
    urls_only = extract_urls(prompt)
    remainder = " ".join(URL_RE.sub(" ", prompt).split())
    if urls_only and len(remainder) < 8:
        writing_ask = (
            "Summarize this article for use in an exposure-management / CTEM research paper, "
            "including how the move could change how buyers run programs."
        )

    why = (
        f"This {cite} note is useful as a market-move citation in an exposure-management / CTEM paper: "
        f"it shows vendors packaging prioritization with validation/reporting as one 'closed loop' story. "
        f"Use it to discuss how buyers may be pushed to rethink tool boundaries, not as proof the loop is closed."
    )
    implications = _em_implications(combined, title)
    use_in_paper = (
        "- Cite the article for the **announced combination of capabilities** and the market narrative "
        "around unified exposure management.\n"
        "- Keep press metrics and 'largest / closes the loop' lines attributed to the article or vendor, "
        "not as independent market fact.\n"
        "- Pair this source with a second reference (analyst note, filing, or customer case) before leaning "
        "on size or outcome claims in the final paper."
    )
    paper_questions = (
        "- What publication/announcement date should be cited?\n"
        "- Which capabilities does each party bring to discover, prioritize, validate, remediate, and retest?\n"
        "- How might EM/VM teams and offensive/validation teams reorganize after this kind of merger?\n"
        "- What would a buyer need to see in a live workflow before accepting 'CTEM loop closed' language?"
    )

    parts = [
        "## Research source note\n\n",
        f"**Writing ask:** {writing_ask}\n\n" if writing_ask else "",
        "### Why this source matters for the paper\n",
        f"{why}\n\n",
        "### Article synopsis\n",
        f"{fact_md}\n\n",
        "### Figures and claims to handle carefully\n",
        f"{figures_md}\n\n",
        "### Implications for how people run exposure management\n",
        f"{implications}\n\n",
        "### How to use this in the draft\n",
        f"{use_in_paper}\n\n",
        "### Open questions for further research\n",
        f"{paper_questions}\n\n",
        "### Reference\n",
        f"- {cite}\n",
    ]
    if deep:
        parts.extend(
            [
                "\n### Extra framing (because you asked for depth)\n",
                "- Tie the story to the CTEM stages you care about in the paper "
                "(discover → prioritize → validate → remediate → retest).\n",
                "- If attack-path content appears, name only the ATT&CK techniques the article "
                "actually supports — no generic laundry lists.\n",
                "- Note any buyer demo that would falsify 'loop closed' marketing "
                "(one finding from priority through retest).\n\n",
            ]
        )

    base = "".join(parts)
    content = humanize_text(base) if rewrite_human else strip_banned_style(base)
    citations = [{"title": title, "url": url}] if url else []
    return {
        "content": content,
        "agent_chars": len(content),
        "notes": (
            "Local research-paper source note"
            + (" with deep framing." if deep else " (summary + EM implications for writing).")
        ),
        "citations": citations,
        "domain": domain,
        "deep_framing": deep,
    }


def build_local_scaffold(prompt: str, context_md: str = "", rewrite_human: bool = True) -> dict[str, Any]:
    """Build offline draft dict: content, agent_chars, notes, citations."""
    prompt = prompt.strip()
    # URL / linked-source runs get a short source brief, not the full empty scaffold.
    if has_linked_sources(context_md):
        return build_linked_source_draft(prompt, context_md, rewrite_human=rewrite_human)

    domain = detect_domain(prompt, context_md)
    refs = trusted_refs_snippet(1200)
    domain_block = _domain_block(domain, prompt)
    base = (
        f"## Research draft scaffold\n\n"
        f"**Prompt:** {prompt}\n\n"
        f"**Detected focus:** {domain}\n\n"
        f"{analyst_voice_notes()}\n"
        f"{domain_block}\n\n"
        f"{buyer_questions_md(domain)}\n"
        f"### Decision framing\n"
        f"Who needs to act (CISO, SecOps lead, VM owner, product security, board risk)? "
        f"What decision is blocked today? What happens if they wait a quarter?\n\n"
        f"### Working outline\n"
        f"1. Problem and buyer outcome\n"
        f"2. Scope boundaries (in / out)\n"
        f"3. Threat framing (MITRE ATT&CK + STRIDE where useful)\n"
        f"4. Current-state program or market pattern\n"
        f"5. Options and tradeoffs (including what to stop)\n"
        f"6. Residual risk and metrics that matter\n"
        f"7. Recommendations (do now / build next / stop)\n"
        f"8. Open questions and evidence still needed\n\n"
        f"### Draft response starter\n"
        f"Start from the decision, not the tool category. For '{prompt}', name the "
        f"failure mode, the validation gap, and what changes if leadership acts in 90 days. "
        f"Pull proof from primary sources before you treat any number as fact. "
        f"If a claim needs a source, write the claim and leave `[source needed]` rather than inventing one.\n\n"
        f"### Suggested section skeleton\n"
        f"{_section_skeleton(domain)}\n"
        f"{evidence_checklist_md(prompt)}\n"
        f"### Reference anchors\n{refs}\n"
    )
    if context_md.strip():
        base += f"\n### Existing section context\n\n{context_md[:2500]}\n"

    content = humanize_text(base) if rewrite_human else strip_banned_style(base)
    citations = [
        {"title": "MITRE ATT&CK", "url": "https://attack.mitre.org/", "note": "Technique mapping"},
        {
            "title": "STRIDE threat model",
            "url": "https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats",
            "note": "Threat categories",
        },
        {
            "title": "NIST Cybersecurity Framework",
            "url": "https://www.nist.gov/cyberframework",
            "note": "Program function framing",
        },
        {
            "title": "CISA Known Exploited Vulnerabilities",
            "url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
            "note": "Exploitability prioritization anchor",
        },
    ]
    return {
        "content": content,
        "agent_chars": len(content),
        "notes": (
            f"Local domain scaffold ({domain}). Add OpenAI / Anthropic / xAI tokens in Security "
            "for live multi-agent research."
        ),
        "citations": citations,
        "domain": domain,
        "evidence_checklist": evidence_checklist_md(prompt),
        "buyer_questions": buyer_questions_md(domain),
    }


def claim_evidence_stub(claim_text: str, title: str = "", url: str = "", confidence: str = "medium") -> str:
    """Markdown block to paste under a weak claim while evidence is gathered."""
    claim = (claim_text or "Claim needs support").strip()
    title = (title or "Source title").strip()
    url = (url or "https://").strip()
    conf = (confidence or "medium").strip().lower()
    return (
        f"\n\n> **Evidence note**\n"
        f"> Claim: {claim}\n"
        f"> Source: [{title}]({url})\n"
        f"> Confidence: {conf}\n"
        f"> Residual risk if wrong: _state impact_\n"
    )


def _section_skeleton(domain: str) -> str:
    if domain == "offensive":
        return (
            "- Summary for leadership\n"
            "- Method comparison (pen test / BAS / AEV / red-purple)\n"
            "- ATT&CK techniques likely in scope\n"
            "- Detection and response gaps\n"
            "- Residual risk after recommended validation cadence\n"
            "- Recommendations (now / next / stop)\n"
        )
    if domain == "exposure":
        return (
            "- Scope and asset classes\n"
            "- Discovery coverage and ownership model\n"
            "- Prioritization logic (exploitability x business impact)\n"
            "- Remediation loop and SLA realism\n"
            "- Residual internet-facing risk\n"
            "- Recommendations (now / next / stop)\n"
        )
    if domain == "vuln":
        return (
            "- Program scope and coverage holes\n"
            "- Triage model (scanner severity vs exploitability)\n"
            "- SLA and exception debt\n"
            "- Executive metrics that drive action\n"
            "- Residual risk after exceptions\n"
            "- Recommendations (now / next / stop)\n"
        )
    if domain == "saas":
        return (
            "- Business context and data class\n"
            "- Identity, data, logging, ops controls\n"
            "- Gap matrix and compensating controls\n"
            "- Residual risk and assurance gaps\n"
            "- Recommendation and exit considerations\n"
        )
    if domain == "tester_analyst":
        return (
            "- Decision this note must unlock\n"
            "- What hands-on testing taught me (pattern, not war story)\n"
            "- Program or market pattern\n"
            "- Threat framing\n"
            "- What buyers get wrong\n"
            "- Options and tradeoffs\n"
            "- Recommendations and evidence still needed\n"
        )
    return (
        "- Summary\n"
        "- Threat framing\n"
        "- Findings\n"
        "- Residual risk\n"
        "- Recommendations\n"
        "- References\n"
    )


def _domain_block(domain: str, prompt: str) -> str:
    if domain == "offensive":
        return (
            "### Offensive Security lens\n"
            "Compare methods by outcome, not hype:\n"
            "- **Penetration testing:** depth on scoped assets, point-in-time, good for unknown unknowns in a boundary\n"
            "- **BAS:** continuous control validation against known techniques and regressions\n"
            "- **AEV:** validate whether exposures are truly exploitable in context before spending remediation budget\n"
            "- **Red / purple team:** objective-driven paths, detection quality, and response friction\n\n"
            "Program questions to answer:\n"
            "- Which method reduces residual risk for this buyer's maturity and change capacity?\n"
            "- What is the right cadence (annual deep test vs continuous validation)?\n"
            "- How do findings feed detection engineering, not only ticket queues?\n"
            "- Where do vendors over-claim continuous assurance?\n\n"
            "Analyst caution: keep attack narrative at technique level. No exploit steps, payloads, or client identifiers.\n"
        )
    if domain == "exposure":
        return (
            "### Exposure Management lens\n"
            "Focus on the loop: discover → own → prioritize → validate → remediate → re-check.\n"
            "Call out:\n"
            "- internet-facing asset sprawl and shadow SaaS\n"
            "- ownership gaps (security finds it, nobody fixes it)\n"
            "- scoring that ignores exploitability and business blast radius\n"
            "- missing link to offensive validation (is this exposure real?)\n\n"
            "Useful framing: exposure without ownership is inventory theater. "
            "Exposure without validation is prioritization theater.\n"
        )
    if domain == "vuln":
        return (
            "### Vulnerability Management lens\n"
            "Separate scanner noise from risk-based triage.\n"
            "Cover:\n"
            "- coverage holes (agents, network segments, cloud accounts)\n"
            "- exception debt and forever-accepted risk\n"
            "- SLA realism versus change freezes\n"
            "- executive metrics that drive action (KEV/EPSS-informed, not raw open counts)\n\n"
            "Push away from CVE count theater. Toward exploitability, asset criticality, and time-to-mitigate.\n"
        )
    if domain == "saas":
        return (
            "### SaaS control review lens\n"
            "Score identity, data protection, logging, and operational controls.\n"
            "For each material control mark: met / partial / gap, evidence, compensating control, residual risk.\n"
            "Ask whether assurance artifacts (SOC 2, pen tests) match the data class and trust boundary.\n"
        )
    if domain == "tester_analyst":
        return (
            "### Tester → Analyst lens\n"
            "You are converting hands-on testing credibility into research insight.\n"
            "Do:\n"
            "- extract repeatable patterns from testing experience\n"
            "- name the buyer decision and the cost of inaction\n"
            "- map techniques to ATT&CK and program controls\n"
            "- recommend sequencing, not just severity\n"
            "Don't:\n"
            "- write a pentest report clone\n"
            "- dump tool output\n"
            "- invent market size or vendor rankings without sources\n"
        )
    return (
        "### General SecOps research lens\n"
        f"Keep the note actionable for leadership. Topic seed: {prompt}\n"
        "Prefer decisions, residual risk, and evidence over tooling laundry lists.\n"
    )
