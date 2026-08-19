"""Local English spellcheck for paper drafts (no cloud API).

Uses pyspellchecker. Skips URLs, markdown chrome, and common SecOps terms.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

# Tokens we never flag (domain / product vocabulary).
ALLOWLIST = {
    "mitre",
    "attck",
    "attack",
    "ciso",
    "cio",
    "cmo",
    "cto",
    "secops",
    "devops",
    "devsecops",
    "saas",
    "iaas",
    "paas",
    "cve",
    "cwe",
    "kev",
    "epss",
    "bas",
    "aev",
    "easm",
    "asm",
    "siem",
    "soar",
    "xdr",
    "edr",
    "mdr",
    "iam",
    "pam",
    "mfa",
    "sso",
    "saml",
    "oidc",
    "scim",
    "cmek",
    "byok",
    "dlp",
    "sbom",
    "ot",
    "ics",
    "itrbp",
    "gartner",
    "stride",
    "theresearcher",
    "markdown",
    "docx",
    "url",
    "api",
    "apis",
    "http",
    "https",
    "www",
}


@lru_cache(maxsize=1)
def _spell():
    from spellchecker import SpellChecker

    sp = SpellChecker(distance=2)
    # Seed domain words into the known dictionary
    sp.word_frequency.load_words(ALLOWLIST)
    return sp


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*[A-Za-z]|[A-Za-z]")


def _should_skip_token(raw: str) -> bool:
    t = raw.strip()
    if len(t) < 3:
        return True
    if t.isupper() and len(t) <= 6:  # acronyms CVE, SLA, etc.
        return True
    if any(ch.isdigit() for ch in t):
        return True
    low = t.lower().strip("'")
    if low in ALLOWLIST:
        return True
    if low.startswith("http") or "://" in low or low.startswith("www."):
        return True
    return False


def spellcheck_text(text: str, *, max_issues: int = 80) -> dict[str, Any]:
    """Return unique misspellings with suggestions and occurrence counts."""
    src = text or ""
    if not src.strip():
        return {
            "ok": True,
            "issue_count": 0,
            "issues": [],
            "message": "Nothing to check — section is empty.",
        }

    # Ignore fenced code lightly by blanking ``` blocks
    cleaned = re.sub(r"```[\s\S]*?```", " ", src)
    # Drop bare URLs
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    # Drop markdown link targets but keep labels: [label](url) → label
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)

    sp = _spell()
    counts: dict[str, int] = {}
    samples: dict[str, str] = {}  # preserve first casing seen

    for m in _WORD_RE.finditer(cleaned):
        raw = m.group(0)
        if _should_skip_token(raw):
            continue
        key = raw.lower().strip("'")
        if key in ALLOWLIST:
            continue
        # pyspellchecker expects lowercase
        if key in sp:
            continue
        counts[key] = counts.get(key, 0) + 1
        samples.setdefault(key, raw)

    issues: list[dict[str, Any]] = []
    for key, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        suggestions = sorted(sp.candidates(key) or [])[:5]
        # Prefer exact edit-distance suggestions first (library already ranks roughly)
        issues.append(
            {
                "word": samples.get(key, key),
                "normalized": key,
                "count": count,
                "suggestions": suggestions,
            }
        )
        if len(issues) >= max(1, min(int(max_issues or 80), 200)):
            break

    return {
        "ok": True,
        "issue_count": len(issues),
        "checked_chars": len(src),
        "issues": issues,
        "message": (
            f"Found {len(issues)} potential misspelling(s)."
            if issues
            else "No spelling issues found (local dictionary)."
        ),
    }
