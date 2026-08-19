"""Local (offline) style helpers — no live model required.

Used by:
  - Research panel post-pass (strip + humanize)
  - AI Checker quick mode (score_ai_likelihood)
  - Local humanize on desk / AI Checker
  - Offline Research Assistant fallback (local_research_assist -> research_scaffold)
  - Local Judge baseline scores (local_judge)

Live rewrites / multi-model judge still go through routers/research.py + llm.py.
"""

from __future__ import annotations

import re
from typing import Any


# Stock phrases the product voice bans; also feed AI-likelihood scoring.
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
    """Remove em dashes, double hyphens, semicolons, and stock AI phrases."""
    cleaned = BANNED_DASH_PATTERN.sub(", ", text)
    cleaned = SEMICOLON_PATTERN.sub(". ", cleaned)
    for pattern in BANNED_PHRASES:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def humanize_text(text: str, strength: str = "medium") -> str:
    """Rule-based local humanize (free). strength: low | medium | high."""
    text = strip_banned_style(text)
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
    """Local AI % heuristic (quick check + publish gate). Not a forensic detector.

    Signals: sentence length, banned phrases, dashes, passive voice, contractions,
    vocabulary uniqueness, uniform bullet lists. Caps at 99%.
    """
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

    drivers: list[dict[str, Any]] = []
    why: list[str] = []

    def _drive(points: float, label: str, detail: str, *, direction: str = "up") -> None:
        if abs(points) < 0.05:
            return
        drivers.append(
            {
                "points": round(points, 1),
                "direction": direction,
                "label": label,
                "detail": detail,
            }
        )
        sign = "+" if points > 0 else ""
        why.append(f"{sign}{points:.0f}: {detail}")

    score = 20.0
    _drive(20.0, "baseline", "Every draft starts at a 20 baseline before style signals.", direction="up")

    if avg_sentence_len > 32:
        score += 22
        _drive(
            22,
            "long_sentences",
            f"Average sentence length is {avg_sentence_len:.1f} words (very long / even cadence).",
        )
    elif avg_sentence_len > 24:
        score += 12
        _drive(
            12,
            "long_sentences",
            f"Average sentence length is {avg_sentence_len:.1f} words (on the long side).",
        )

    banned_pts = min(banned_hits * 8, 24)
    score += banned_pts
    if banned_hits:
        _drive(
            banned_pts,
            "stock_phrases",
            f"Found {banned_hits} stock AI-ish phrase hit(s) (e.g. furthermore, delve, robust).",
        )

    dash_pts = min(dash_hits * 4, 12)
    score += dash_pts
    if dash_hits:
        _drive(dash_pts, "dashes", f"Found {dash_hits} em dash / double-hyphen hit(s).")

    semi_pts = min(semicolon_hits * 2, 8)
    score += semi_pts
    if semicolon_hits:
        _drive(semi_pts, "semicolons", f"Found {semicolon_hits} semicolon(s).")

    passive_pts = min(passive_hits * 1.5, 12)
    score += passive_pts
    if passive_hits:
        _drive(passive_pts, "passive_voice", f"Detected about {passive_hits} passive-ish construction(s).")

    if contraction_hits / word_count < 0.01 and word_count > 80:
        score += 10
        _drive(
            10,
            "few_contractions",
            "Very few contractions for this length — reads more formal/AI-smooth.",
        )
    if unique_ratio < 0.45 and word_count > 100:
        score += 10
        _drive(
            10,
            "low_vocabulary_variety",
            f"Word variety is low (unique ratio {unique_ratio:.2f}).",
        )
    if unique_ratio > 0.65:
        score -= 8
        _drive(
            -8,
            "varied_vocabulary",
            f"Word variety looks natural (unique ratio {unique_ratio:.2f}).",
            direction="down",
        )
    if contraction_hits > 3:
        score -= 6
        _drive(
            -6,
            "natural_contractions",
            f"Found {contraction_hits} contractions (don't / it's / you're) — more human voice.",
            direction="down",
        )

    # Paragraph symmetry (many equal-ish bullets) often reads synthetic
    bullets = re.findall(r"^\s*[-*]\s+.+$", text, flags=re.MULTILINE)
    bullet_sym_pts = 0.0
    if len(bullets) >= 6:
        lengths = [len(b) for b in bullets]
        mean = sum(lengths) / len(lengths)
        variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
        if variance < 40:
            bullet_sym_pts = 8.0
            score += bullet_sym_pts
            _drive(
                bullet_sym_pts,
                "uniform_bullets",
                f"{len(bullets)} bullets look very evenly sized (template-like rhythm).",
            )

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

    if not why:
        why.append("No strong AI-style drivers beyond the baseline — score stays low.")

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
        "drivers": drivers,
        "why": why,
        "recommendations": recommendations,
    }


def local_research_assist(prompt: str, context_md: str = "", rewrite_human: bool = False) -> dict[str, Any]:
    """Offline Research Assistant: domain scaffold, not a live model."""
    from app.services.research_scaffold import build_local_scaffold

    return build_local_scaffold(prompt, context_md, rewrite_human=rewrite_human)


def local_judge(text: str, criteria: list[str]) -> dict[str, Any]:
    """Cheap local rubric scores (citations, structure, AI %, ethics keywords)."""
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
    try:
        from app.services.app_settings import load_app_settings

        max_ai = float(load_app_settings().get("max_ai_checker_pct", 10.0))
    except Exception:  # noqa: BLE001
        max_ai = 10.0
    if ai["ai_pct"] >= max_ai:
        feedback_bits.append(
            f"Humanize and hand-edit until AI-likeness is under your Settings target ({max_ai}%)."
        )
    feedback_bits.append(
        "Translate testing detail into leadership decisions: residual risk, sequencing, and what to stop."
    )

    return {
        "scores": scores,
        "overall_score": overall,
        "feedback": strip_banned_style(" ".join(feedback_bits)),
    }
