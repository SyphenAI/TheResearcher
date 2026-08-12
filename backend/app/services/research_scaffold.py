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
        "offensive": len(re.findall(r"\b(offens|pentest|red team|purple|bas|aev|adversarial exposure)\b", text)),
        "exposure": len(re.findall(r"\b(exposure|attack surface|asm|easm|internet[- ]facing|external asset)\b", text)),
        "vuln": len(re.findall(r"\b(vulnerab|cve|patch|sla|remediat|vm program|scanner)\b", text)),
        "saas": len(re.findall(r"\b(saas|vendor|cmek|sso|scim|control review)\b", text)),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def evidence_checklist_md(topic: str = "") -> str:
    topic_bit = f" for **{topic}**" if topic.strip() else ""
    return (
        f"## Evidence checklist{topic_bit}\n\n"
        "- [ ] Claim is specific enough to falsify\n"
        "- [ ] Primary source linked (vendor docs, ATT&CK, standard, telemetry)\n"
        "- [ ] Confidence marked (high / medium / low)\n"
        "- [ ] Residual risk stated after control options\n"
        "- [ ] Recommendation is sequenced (now / next / stop)\n"
        "- [ ] No invented CVE counts or market share numbers\n"
        "- [ ] Written for a security leader decision, not a ticket queue\n"
    )


def analyst_voice_notes() -> str:
    return (
        "### Voice shift: tester to analyst\n"
        "Write for decisions, not for exploit steps. Translate hands-on testing experience into:\n"
        "- what buyers struggle to prioritize\n"
        "- which validation methods change outcomes\n"
        "- where programs waste spend\n"
        "- residual risk after tooling\n"
        "Keep tradecraft high-level and responsible. No exploit recipes.\n"
    )


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
        f"### Decision framing\n"
        f"Who needs to act (CISO, SecOps lead, VM owner, product security)? "
        f"What decision is blocked today?\n\n"
        f"### Working outline\n"
        f"1. Problem and buyer outcome\n"
        f"2. Scope boundaries (in / out)\n"
        f"3. Threat framing (MITRE ATT&CK + STRIDE where useful)\n"
        f"4. Current-state program or market pattern\n"
        f"5. Options and tradeoffs\n"
        f"6. Residual risk and metrics that matter\n"
        f"7. Recommendations (do now / build next / stop)\n"
        f"8. Open questions and evidence still needed\n\n"
        f"### Draft response\n"
        f"Start from the decision, not the tool category. For '{prompt}', name the "
        f"failure mode, the validation gap, and what changes if leadership acts in 90 days. "
        f"Pull proof from primary sources before you treat any number as fact.\n\n"
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
    }


def _domain_block(domain: str, prompt: str) -> str:
    if domain == "offensive":
        return (
            "### Offensive Security lens\n"
            "Compare methods by outcome, not hype:\n"
            "- Penetration testing: depth on scoped assets, point-in-time\n"
            "- BAS: continuous control validation against known techniques\n"
            "- AEV: validate whether exposures are truly exploitable in context\n"
            "- Red / purple team: objective-driven paths and detection quality\n"
            "Ask: which method reduces residual risk for this buyer's maturity?\n"
        )
    if domain == "exposure":
        return (
            "### Exposure Management lens\n"
            "Focus on discovery, ownership, prioritization, and validation loops.\n"
            "Call out internet-facing asset sprawl, shadow SaaS, and ownership gaps.\n"
            "Connect exposure scoring to remediation SLAs and offensive validation.\n"
        )
    if domain == "vuln":
        return (
            "### Vulnerability Management lens\n"
            "Separate scanner noise from risk-based triage. Cover coverage holes, "
            "exception debt, SLA realism, and executive metrics that drive action.\n"
            "Avoid CVE count theater. Push toward exploitability and business impact.\n"
        )
    if domain == "saas":
        return (
            "### SaaS control review lens\n"
            "Score identity, data protection, logging, and operational controls.\n"
            "Mark met / partial / gap and residual risk after compensating controls.\n"
        )
    return (
        "### General SecOps research lens\n"
        f"Keep the note actionable for leadership. Topic seed: {prompt}\n"
    )
