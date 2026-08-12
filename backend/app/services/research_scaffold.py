"""Domain research scaffolds for offline and live-assisted drafting.

Voice target: security research analyst, not raw pentest ticket writer.
Helps transition from active testing work into insight-style research notes.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.ai_style import humanize_text, strip_banned_style
from app.services.refs_cache import trusted_refs_snippet


def detect_domain(prompt: str, context_md: str = "") -> str:
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


def build_local_scaffold(prompt: str, context_md: str = "", rewrite_human: bool = True) -> dict[str, Any]:
    prompt = prompt.strip()
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
