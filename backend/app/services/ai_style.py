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
# En/em dash between digits (date/number ranges) — keep as ASCII hyphen, not comma.
RANGE_DASH_PATTERN = re.compile(r"(\d)\s*[\u2013\u2014]\s*(\d)")


def fix_ai_style_tells(text: str) -> dict[str, Any]:
    """Mechanical style fix for AI-check tells (preview/accept on desk).

    - Digit ranges with en/em dash → ASCII hyphen (1–30 → 1-30)
    - Remaining em/en dashes and -- → comma
    - Semicolons → periods
    Does not strip stock phrases or invent contractions. Preserves markdown HRs.
    """
    original = text or ""
    out = original
    ops: list[str] = []

    # Preserve markdown thematic breaks while fixing double hyphens in prose.
    hr_slots: dict[str, str] = {}

    def _park_hr(match: re.Match[str]) -> str:
        key = f"\0HR{len(hr_slots)}\0"
        hr_slots[key] = match.group(0)
        return key

    out = re.sub(r"(?m)^\s*-{3,}\s*$", _park_hr, out)

    out, n_range = RANGE_DASH_PATTERN.subn(r"\1-\2", out)
    if n_range:
        ops.append(f"Converted {n_range} number/date range dash(es) to hyphen (e.g. 1-30).")

    out, n_dd = re.subn(r"-{2,}", ", ", out)
    out, n_em = re.subn(r"[\u2014\u2013]", ", ", out)
    prose_dashes = n_dd + n_em
    if prose_dashes:
        ops.append(f"Replaced {prose_dashes} em/en/double-hyphen dash(es) with commas.")

    for key, val in hr_slots.items():
        out = out.replace(key, val)

    def _semi_to_period(match: re.Match[str]) -> str:
        rest = match.group(1)
        if rest and rest[0].islower():
            rest = rest[0].upper() + rest[1:]
        return f". {rest}"

    out, n_semi = re.subn(r";\s*(\S)", _semi_to_period, out)
    # Any leftover bare semicolons
    if ";" in out:
        leftovers = out.count(";")
        out = out.replace(";", ".")
        n_semi += leftovers
    if n_semi:
        ops.append(f"Replaced {n_semi} semicolon(s) with periods.")

    # Light cleanup without smashing markdown newlines.
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r" +\.", ".", out)
    out = re.sub(r" +,", ",", out)
    out = re.sub(r"\n{3,}", "\n\n", out)

    before = score_ai_likelihood(original)
    after = score_ai_likelihood(out)
    return {
        "original": original,
        "proposed": out,
        "changed": out != original,
        "ops": ops,
        "before": {
            "ai_pct": before.get("ai_pct"),
            "human_pct": before.get("human_pct"),
            "signals": before.get("signals") or {},
        },
        "after": {
            "ai_pct": after.get("ai_pct"),
            "human_pct": after.get("human_pct"),
            "signals": after.get("signals") or {},
        },
    }


def strip_banned_style(text: str) -> str:
    """Remove em dashes, double hyphens, semicolons, and stock AI phrases."""
    # Keep date/number ranges readable (1–30 → 1-30) before comma substitution.
    cleaned = RANGE_DASH_PATTERN.sub(r"\1-\2", text or "")
    cleaned = BANNED_DASH_PATTERN.sub(", ", cleaned)
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

    # Sentence rewriting must not smash markdown structure (headers/bullets/newlines).
    # Older logic joined on ". " and destroyed research-source-note formatting.
    looks_markdown = bool(re.search(r"(?m)^#{1,6}\s+|^\s*[-*]\s+", out))
    if strength in {"medium", "high"} and not looks_markdown:
        parts = re.split(r"(?<=\.)\s+", out)
        rebuilt: list[str] = []
        for sentence in parts:
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
    elif strength == "high" and looks_markdown:
        # Only split very long prose lines; keep line breaks and list/header lines intact.
        lines_out: list[str] = []
        for line in out.split("\n"):
            raw = line
            stripped = line.strip()
            if (
                not stripped
                or re.match(r"^#{1,6}\s+", stripped)
                or re.match(r"^[-*]\s+", stripped)
                or re.match(r"^\d+\.\s+", stripped)
                or len(stripped) <= 160
                or ", and " not in stripped
            ):
                lines_out.append(raw)
                continue
            left, right = stripped.split(", and ", 1)
            indent = re.match(r"^\s*", raw).group(0) if re.match(r"^\s*", raw) else ""
            lines_out.append(indent + left.rstrip(",") + ".")
            lines_out.append(indent + (right[0].upper() + right[1:] if right else right))
        out = "\n".join(lines_out)

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

    Tuned for formal analyst notes: long sentences / sparse contractions are mild.
    Stock AI phrases, em dashes, and double hyphens are the main red flags.
    """
    if not text.strip():
        return {
            "ai_pct": 0.0,
            "human_pct": 100.0,
            "signals": {"empty": True},
            "drivers": [],
            "why": [],
            "recommendations": ["Paste content to evaluate."],
        }

    # Ignore markdown thematic breaks so "---" section joiners / HRs are not scored as AI dashes.
    prose = re.sub(r"(?m)^\s*-{3,}\s*$", "", text)

    words = re.findall(r"[A-Za-z']+", prose)
    word_count = max(len(words), 1)
    sentences = [s.strip() for s in re.split(r"[.!?]+", prose) if s.strip()]
    sentence_count = max(len(sentences), 1)
    avg_sentence_len = word_count / sentence_count

    banned_hits = 0
    for pattern in BANNED_PHRASES:
        banned_hits += len(re.findall(pattern, prose, flags=re.IGNORECASE))

    dash_hits = len(BANNED_DASH_PATTERN.findall(prose))
    semicolon_hits = len(SEMICOLON_PATTERN.findall(prose))
    passive_hits = len(re.findall(r"\b(is|are|was|were|be|been|being)\s+\w+ed\b", prose, re.I))
    contraction_hits = len(re.findall(r"\b\w+n't\b|\bit's\b|\byou're\b|\bwe're\b|\bthey're\b", prose, re.I))
    unique_ratio = len(set(w.lower() for w in words)) / word_count
    bullets = re.findall(r"^\s*[-*]\s+.+$", prose, flags=re.MULTILINE)

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

    # Low baseline so typed formal notes are not already "failing"
    score = 4.0
    _drive(4.0, "baseline", "Small baseline only — formal human notes should stay low unless AI-ish tells appear.")

    # Primary tells: stock LLM phrases (strong)
    banned_pts = min(banned_hits * 10, 40)
    score += banned_pts
    if banned_hits:
        _drive(
            banned_pts,
            "stock_phrases",
            f"Found {banned_hits} stock AI-ish phrase hit(s) (furthermore, delve, robust, seamless…).",
        )

    # Product voice bans — still meaningful
    dash_pts = min(dash_hits * 5, 20)
    score += dash_pts
    if dash_hits:
        _drive(
            dash_pts,
            "dashes",
            f"Found {dash_hits} en/em dash or double-hyphen hit(s) "
            f"(markdown list '-' is fine; date ranges like 1–30 count).",
        )

    semi_pts = min(semicolon_hits * 2, 8)
    score += semi_pts
    if semicolon_hits:
        _drive(semi_pts, "semicolons", f"Found {semicolon_hits} semicolon(s).")

    # Formal writing: long sentences / light passive / few contractions are mild only
    if avg_sentence_len > 38:
        score += 6
        _drive(6, "long_sentences", f"Average sentence length is {avg_sentence_len:.1f} words (quite long).")
    elif avg_sentence_len > 30:
        score += 3
        _drive(
            3,
            "long_sentences",
            f"Average sentence length is {avg_sentence_len:.1f} words (normal for formal notes).",
        )

    # Passive only when passive is unusually dense
    passive_density = passive_hits / max(sentence_count, 1)
    if passive_density > 0.55 and word_count > 120:
        passive_pts = min(6.0, 3 + passive_hits * 0.2)
        score += passive_pts
        _drive(
            passive_pts,
            "passive_voice",
            f"Passive constructions look dense (~{passive_hits} hits) — fine in moderation for analyst prose.",
        )

    # Few contractions alone is NOT treated as AI (analyst voice is often formal)
    if contraction_hits / word_count < 0.005 and word_count > 200 and banned_hits >= 2:
        score += 4
        _drive(
            4,
            "few_contractions_with_stock",
            "Almost no contractions *plus* stock phrases — that combo reads smoother/AI-like.",
        )

    if unique_ratio < 0.38 and word_count > 150:
        score += 8
        _drive(8, "low_vocabulary_variety", f"Word variety is quite low (unique ratio {unique_ratio:.2f}).")
    elif unique_ratio < 0.45 and word_count > 150 and banned_hits >= 1:
        score += 4
        _drive(
            4,
            "low_vocabulary_with_stock",
            f"Lower word variety ({unique_ratio:.2f}) with stock phrases present.",
        )

    if unique_ratio > 0.58:
        score -= 4
        _drive(
            -4,
            "varied_vocabulary",
            f"Word variety looks natural (unique ratio {unique_ratio:.2f}).",
            direction="down",
        )
    if contraction_hits >= 2:
        score -= 3
        _drive(
            -3,
            "natural_contractions",
            f"Found {contraction_hits} contractions — slight human-voice credit.",
            direction="down",
        )

    # Template bullet rhythm: mild unless also stock-phrase heavy
    if len(bullets) >= 8:
        lengths = [len(b) for b in bullets]
        mean = sum(lengths) / len(lengths)
        variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
        if variance < 35:
            bullet_pts = 6.0 if banned_hits else 2.0
            score += bullet_pts
            _drive(
                bullet_pts,
                "uniform_bullets",
                f"{len(bullets)} bullets look evenly sized"
                + (" and stock phrases are present." if banned_hits else " (common in templates — mild only)."),
            )

    ai_pct = max(0.0, min(99.0, round(score, 1)))
    human_pct = round(100.0 - ai_pct, 1)

    recommendations: list[str] = []
    if banned_hits:
        recommendations.append("Strip stock AI phrases (furthermore, delve, robust, seamless, unlock…).")
    if dash_hits or semicolon_hits:
        recommendations.append("Replace em dashes, double hyphens, and semicolons with commas or periods.")
    if ai_pct >= 25 and banned_hits:
        recommendations.append("Run Local/Live humanize, then hand-edit a few lines in your own voice.")
    if ai_pct >= 15 and not banned_hits and not dash_hits:
        recommendations.append(
            "Score is mostly formal-structure signals, not paste tells. Optional: mix one short sentence per paragraph."
        )
    if contraction_hits < 1 and word_count > 80 and ai_pct >= 12:
        recommendations.append("Optional: a few contractions (don't, it's) if the audience allows a direct voice.")
    if not recommendations:
        recommendations.append(
            "Looks like typed / formal human prose. Light proofread is enough — no need to force slangy contractions."
        )

    # Clarify when formal structure (not AI paste) is driving the score
    formal_only = banned_hits == 0 and dash_hits == 0 and semicolon_hits == 0
    if formal_only and ai_pct >= 8:
        why.insert(
            0,
            "Note: no stock AI phrases or banned dashes found — remaining points are mostly formal writing shape, not proof you pasted from a model.",
        )
    if not why:
        why.append("No strong AI-style drivers — score stays low.")

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
            "calibration": "formal_analyst_v2",
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
