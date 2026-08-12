from __future__ import annotations

import re
from typing import Any


BANNED_PHRASES = [
    r"\bin conclusion\b",
    r"\bfurthermore\b",
    r"\bit is important to note\b",
    r"\bdelve\b",
    r"\btestament\b",
    r"\bnot only\b.+\bbut also\b",
    r"\bleverage\b",
    r"\brobust\b",
    r"\bcutting[- ]edge\b",
    r"\bseamless(ly)?\b",
    r"\bunlock\b",
    r"\bempower\b",
]

BANNED_DASH_PATTERN = re.compile(r"(--|\u2014|\u2013)")
SEMICOLON_PATTERN = re.compile(r";")


def strip_banned_style(text: str) -> str:
    cleaned = BANNED_DASH_PATTERN.sub(", ", text)
    cleaned = SEMICOLON_PATTERN.sub(". ", cleaned)
    for pattern in BANNED_PHRASES:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def humanize_text(text: str, strength: str = "medium") -> str:
    """Rewrite helper that reduces AI-ish cadence without external model calls."""
    text = strip_banned_style(text)
    # Soften formulaic openers
    replacements = [
        (r"^In today's digital landscape,?\s*", ""),
        (r"^In the realm of\s+", "For "),
        (r"^It should be noted that\s+", ""),
        (r"^Moreover,?\s+", ""),
        (r"^Additionally,?\s+", ""),
        (r"^Overall,?\s+", ""),
        (r"\butilize\b", "use"),
        (r"\butilize[sd]\b", "used"),
        (r"\bfacilitate\b", "help"),
        (r"\bcomprehensive\b", "full"),
        (r"\boptimize\b", "improve"),
        (r"\bensure that\b", "make sure"),
    ]
    out = text
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE | re.MULTILINE)

    if strength in {"medium", "high"}:
        # Break long sentences occasionally by splitting on ", and "
        parts = re.split(r"(?<=\.)\s+", out)
        rebuilt: list[str] = []
        for i, sentence in enumerate(parts):
            sentence = sentence.strip()
            if not sentence:
                continue
            if strength == "high" and len(sentence) > 160 and ", and " in sentence:
                left, right = sentence.split(", and ", 1)
                rebuilt.append(left.rstrip(",") + ".")
                rebuilt.append(right[0].upper() + right[1:] if right else right)
            else:
                rebuilt.append(sentence)
        out = " ".join(rebuilt)

    # Prefer contractions for common patterns
    contraction_map = [
        (r"\bdo not\b", "don't"),
        (r"\bdoes not\b", "doesn't"),
        (r"\bcannot\b", "can't"),
        (r"\bwill not\b", "won't"),
        (r"\bit is\b", "it's"),
        (r"\byou are\b", "you're"),
        (r"\bwe are\b", "we're"),
        (r"\bthey are\b", "they're"),
        (r"\bis not\b", "isn't"),
        (r"\bare not\b", "aren't"),
    ]
    for pattern, repl in contraction_map:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)

    return strip_banned_style(out)


def score_ai_likelihood(text: str) -> dict[str, Any]:
    """Heuristic AI checker for local offline use. Not a legal detector."""
    if not text.strip():
        return {
            "ai_pct": 0.0,
            "human_pct": 100.0,
            "signals": {"empty": True},
            "recommendations": ["Paste content to evaluate."],
        }

    words = re.findall(r"[A-Za-z']+", text)
    word_count = max(len(words), 1)
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    sentence_count = max(len(sentences), 1)
    avg_sentence_len = word_count / sentence_count

    banned_hits = 0
    for pattern in BANNED_PHRASES:
        banned_hits += len(re.findall(pattern, text, flags=re.IGNORECASE))

    dash_hits = len(BANNED_DASH_PATTERN.findall(text))
    semicolon_hits = len(SEMICOLON_PATTERN.findall(text))
    passive_hits = len(re.findall(r"\b(is|are|was|were|be|been|being)\s+\w+ed\b", text, re.I))
    contraction_hits = len(re.findall(r"\b\w+n't\b|\bit's\b|\byou're\b|\bwe're\b|\bthey're\b", text, re.I))
    unique_ratio = len(set(w.lower() for w in words)) / word_count

    score = 20.0
    if avg_sentence_len > 24:
        score += 12
    if avg_sentence_len > 32:
        score += 10
    score += min(banned_hits * 8, 24)
    score += min(dash_hits * 4, 12)
    score += min(semicolon_hits * 2, 8)
    score += min(passive_hits * 1.5, 12)
    if contraction_hits / word_count < 0.01 and word_count > 80:
        score += 10
    if unique_ratio < 0.45 and word_count > 100:
        score += 10
    if unique_ratio > 0.65:
        score -= 8
    if contraction_hits > 3:
        score -= 6

    # Paragraph symmetry (many equal-ish bullets) often reads synthetic
    bullets = re.findall(r"^\s*[-*]\s+.+$", text, flags=re.MULTILINE)
    if len(bullets) >= 6:
        lengths = [len(b) for b in bullets]
        mean = sum(lengths) / len(lengths)
        variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
        if variance < 40:
            score += 8

    ai_pct = max(0.0, min(99.0, round(score, 1)))
    human_pct = round(100.0 - ai_pct, 1)

    recommendations: list[str] = []
    if ai_pct >= 10:
        recommendations.append("Run Humanize rewrite, then edit in your own voice.")
    if banned_hits:
        recommendations.append("Remove stock AI phrases and transition filler.")
    if dash_hits or semicolon_hits:
        recommendations.append("Replace em dashes, double hyphens, and semicolons with commas or periods.")
    if contraction_hits < 2 and word_count > 60:
        recommendations.append("Use natural contractions (don't, it's, you're).")
    if avg_sentence_len > 28:
        recommendations.append("Mix short punchy lines with longer ones.")
    if not recommendations:
        recommendations.append("Looks mostly human. Keep a light human edit pass before publish.")

    return {
        "ai_pct": ai_pct,
        "human_pct": human_pct,
        "signals": {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_sentence_len": round(avg_sentence_len, 2),
            "banned_phrase_hits": banned_hits,
            "dash_hits": dash_hits,
            "semicolon_hits": semicolon_hits,
            "passive_hits": passive_hits,
            "contraction_hits": contraction_hits,
            "unique_word_ratio": round(unique_ratio, 3),
            "bullet_count": len(bullets),
        },
        "recommendations": recommendations,
    }


def local_research_assist(prompt: str, context_md: str = "", rewrite_human: bool = False) -> dict[str, Any]:
    """Offline research assistant scaffold used until external AI tokens are configured."""
    prompt = prompt.strip()
    base = (
        f"## Research notes\n\n"
        f"Prompt: {prompt}\n\n"
        f"### Working outline\n"
        f"1. Frame the security question in business and risk terms.\n"
        f"2. Map relevant MITRE ATT&CK techniques and STRIDE categories.\n"
        f"3. Review exposure paths, asset classes, and likely blast radius.\n"
        f"4. Compare SaaS or control options against the requirement.\n"
        f"5. Capture evidence, confidence, and open questions.\n\n"
        f"### Draft response\n"
        f"Here's a practical starting point for your topic. Treat this as scaffolding, "
        f"not final research. Pull primary sources, vendor docs, and internal telemetry "
        f"before you publish.\n\n"
        f"For '{prompt}', start by naming the asset or process under review, the threat "
        f"actors or failure modes that matter, and the control objective you need. "
        f"Then score residual risk after each control option. Keep claims tight and cite "
        f"where numbers came from.\n"
    )
    if context_md.strip():
        base += f"\n### Existing section context\n\n{context_md[:2000]}\n"

    citations = [
        {
            "title": "MITRE ATT&CK",
            "url": "https://attack.mitre.org/",
            "note": "Technique mapping reference",
        },
        {
            "title": "STRIDE threat model",
            "url": "https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats",
            "note": "Threat category framing",
        },
    ]
    content = humanize_text(base) if rewrite_human else strip_banned_style(base)
    return {
        "content": content,
        "agent_chars": len(content),
        "notes": (
            "Generated by the local assistant scaffold. Add provider tokens in Security "
            "to enable full multi-agent research."
        ),
        "citations": citations,
    }


def local_judge(text: str, criteria: list[str]) -> dict[str, Any]:
    text = text.strip()
    if not text:
        scores = {c: 0.0 for c in criteria}
        return {
            "scores": scores,
            "overall_score": 0.0,
            "feedback": "No content provided for review.",
        }

    words = re.findall(r"\w+", text)
    word_count = len(words)
    has_citations = bool(re.search(r"https?://|\[\d+\]|\(.*\d{4}.*\)", text))
    has_structure = bool(re.search(r"^#+\s|\n-\s|\n\d+\.", text, re.M))
    ai = score_ai_likelihood(text)

    scores: dict[str, float] = {}
    for c in criteria:
        key = c.lower()
        if key == "accuracy":
            scores[c] = 6.5 + (1.5 if has_citations else 0) + min(word_count / 400, 1.5)
        elif key == "relevance":
            scores[c] = 7.0 if word_count > 80 else 4.0
        elif key == "originality":
            scores[c] = max(3.0, 9.0 - (ai["ai_pct"] / 20))
        elif key == "ethics":
            risky = re.search(r"\b(exploit|weaponize|zero[- ]day payload)\b", text, re.I)
            scores[c] = 5.0 if risky else 8.5
        elif key == "clarity":
            scores[c] = 8.0 if has_structure else 6.0
        else:
            scores[c] = 6.5

    for k, v in list(scores.items()):
        scores[k] = round(min(10.0, max(0.0, v)), 1)

    overall = round(sum(scores.values()) / max(len(scores), 1), 1)
    feedback_bits = [
        f"Overall score {overall}/10 across {', '.join(criteria)}.",
        f"Estimated AI-likeness about {ai['ai_pct']}% on the local checker.",
    ]
    if not has_citations:
        feedback_bits.append("Add inline citations and primary references.")
    if not has_structure:
        feedback_bits.append("Use headings and short sections so reviewers can scan findings.")
    if ai["ai_pct"] >= 10:
        feedback_bits.append(
            "Humanize and hand-edit until agent contribution stays under 10% for final publish."
        )
    feedback_bits.append("Peer review next: share with a teammate and log decisions in tasks.")

    return {
        "scores": scores,
        "overall_score": overall,
        "feedback": strip_banned_style(" ".join(feedback_bits)),
    }
