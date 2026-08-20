"""Summarize free text, uploaded docs, or public URLs for research intake."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.ai_style import humanize_text, strip_banned_style
from app.services.document_text import DocumentExtractError, extract_text_from_upload

MAX_FETCH_BYTES = 2 * 1024 * 1024
MAX_SUMMARY_INPUT = 60_000
MAX_URLS_IN_PROMPT = 3
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 TheResearcher/0.2"
)
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)


def _normalize_ws(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<!--.*?-->", " ", raw)
    # Prefer main/article if present
    main = re.search(r"(?is)<(article|main)[^>]*>(.*?)</\1>", raw)
    chunk = main.group(2) if main else raw
    chunk = re.sub(r"(?s)<[^>]+>", " ", chunk)
    chunk = html.unescape(chunk)
    return _normalize_ws(chunk)


def extract_urls(text: str, *, max_urls: int = MAX_URLS_IN_PROMPT) -> list[str]:
    """Pull unique http(s) URLs from free text (prompt paste)."""
    found: list[str] = []
    seen: set[str] = set()
    for match in URL_RE.findall(text or ""):
        cleaned = match.rstrip(".,;:!?)】》\"'")
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(cleaned)
        if len(found) >= max(1, min(int(max_urls or MAX_URLS_IN_PROMPT), 5)):
            break
    return found


def _looks_like_challenge_page(title: str, text: str) -> bool:
    blob = f"{title}\n{text[:800]}".lower()
    markers = (
        "just a moment",
        "attention required",
        "cf-browser-verification",
        "enable javascript and cookies",
        "checking your browser",
        "access denied",
        "cloudflare",
    )
    return any(m in blob for m in markers)


def fetch_url_text(url: str) -> dict[str, Any]:
    u = (url or "").strip()
    if not u:
        raise ValueError("URL is required.")
    parsed = urlparse(u)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed.")
    if not parsed.netloc:
        raise ValueError("URL host is missing.")

    try:
        with httpx.Client(
            timeout=25.0,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
            },
        ) as client:
            resp = client.get(u)
            if resp.status_code >= 400:
                raise ValueError(f"URL fetch failed ({resp.status_code}).")
            content = resp.content
            if len(content) > MAX_FETCH_BYTES:
                content = content[:MAX_FETCH_BYTES]
            ctype = (resp.headers.get("content-type") or "").lower()
            final_url = str(resp.url)
    except httpx.HTTPError as exc:
        raise ValueError(f"Could not fetch URL: {exc}") from exc

    # Binary docs served at URL
    path = urlparse(final_url).path.lower()
    if any(path.endswith(ext) for ext in (".pdf", ".docx", ".pptx", ".odt", ".txt", ".md")):
        name = path.rsplit("/", 1)[-1] or "download.bin"
        try:
            extracted = extract_text_from_upload(name, content, ctype)
            return {
                "source_type": "url_file",
                "url": final_url,
                "title": name,
                "text": extracted["text"],
                "char_count": extracted["char_count"],
                "ocr_used": bool(extracted.get("ocr_used")),
                "fetch_via": "direct",
            }
        except DocumentExtractError as exc:
            raise ValueError(str(exc)) from exc

    # Treat as HTML/text
    try:
        raw = content.decode("utf-8")
    except UnicodeDecodeError:
        raw = content.decode("latin-1", errors="replace")

    title = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    if m:
        title = _normalize_ws(html.unescape(m.group(1)))

    if "html" in ctype or "<html" in raw[:500].lower() or "<!doctype" in raw[:200].lower():
        text = html_to_text(raw)
    else:
        text = _normalize_ws(raw)

    if not text:
        raise ValueError("No readable text found at URL.")
    if _looks_like_challenge_page(title, text):
        raise ValueError(
            "Site returned a bot/Cloudflare challenge page. "
            "Set a Jina API key in Settings, or paste the article text into the prompt."
        )

    if len(text) > MAX_SUMMARY_INPUT:
        text = text[:MAX_SUMMARY_INPUT]

    return {
        "source_type": "url",
        "url": final_url,
        "title": title or final_url,
        "text": text,
        "char_count": len(text),
        "ocr_used": False,
        "fetch_via": "direct",
    }


def fetch_url_via_jina(url: str, *, api_key: str | None = None) -> dict[str, Any]:
    """Fetch readable markdown/text through Jina Reader (helps on Cloudflare sites)."""
    u = (url or "").strip()
    if not u:
        raise ValueError("URL is required.")
    reader = f"https://r.jina.ai/{u}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/plain,text/markdown,*/*",
        "X-Return-Format": "markdown",
    }
    key = (api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        with httpx.Client(timeout=45.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(reader)
            if resp.status_code >= 400:
                detail = _normalize_ws(html_to_text(resp.text or "") or resp.text or "")[:120]
                raise ValueError(f"Jina reader failed ({resp.status_code}): {detail}")
            text = _normalize_ws(resp.text or "")
    except httpx.HTTPError as exc:
        raise ValueError(f"Jina reader request failed: {exc}") from exc

    if not text or len(text) < 40:
        raise ValueError("Jina reader returned empty content.")
    if _looks_like_challenge_page("", text):
        raise ValueError(
            "Jina reader hit a bot challenge. Add a Jina API key in Settings, or paste the article text."
        )

    title = ""
    for line in text.splitlines()[:12]:
        s = line.strip()
        if s.startswith("# "):
            title = s[2:].strip()
            break
        if s.startswith("Title:"):
            title = s.split(":", 1)[1].strip()
            break

    if len(text) > MAX_SUMMARY_INPUT:
        text = text[:MAX_SUMMARY_INPUT]

    return {
        "source_type": "url",
        "url": u,
        "title": title or u,
        "text": text,
        "char_count": len(text),
        "ocr_used": False,
        "fetch_via": "jina",
    }


def fetch_url_text_with_fallback(url: str, *, jina_api_key: str | None = None) -> dict[str, Any]:
    """Direct fetch first; on block/failure try Jina Reader."""
    direct_err = ""
    try:
        return fetch_url_text(url)
    except ValueError as exc:
        direct_err = str(exc)

    jina_err = ""
    try:
        return fetch_url_via_jina(url, api_key=jina_api_key)
    except ValueError as exc:
        jina_err = str(exc)

    hint = (
        " Paste the article text into the Research prompt, or add a Jina API key in Settings "
        "(r.jina.ai) for Cloudflare-protected pages."
        if not (jina_api_key or "").strip()
        else " Paste the article text into the Research prompt if the site keeps blocking automated fetch."
    )
    raise ValueError(
        f"Could not read URL. Direct: {direct_err} Jina: {jina_err or 'not attempted'}.{hint}"
    )


def build_url_source_briefs(
    db,
    prompt: str,
    *,
    jina_api_key: str | None = None,
    user_name: str = "",
    max_urls: int = MAX_URLS_IN_PROMPT,
    mode: str = "auto",
) -> dict[str, Any]:
    """Detect URLs in a research prompt, fetch+summarize, return markdown briefs for context."""
    urls = extract_urls(prompt, max_urls=max_urls)
    if not urls:
        return {
            "urls": [],
            "briefs_md": "",
            "notes": "",
            "citations": [],
            "failed": [],
            "ok": [],
        }

    blocks: list[str] = []
    notes: list[str] = []
    citations: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    ok: list[dict[str, str]] = []

    for url in urls:
        try:
            fetched = fetch_url_text_with_fallback(url, jina_api_key=jina_api_key)
            summarized = summarize_payload(
                db,
                text=fetched.get("text") or "",
                title=fetched.get("title") or url,
                source_type=fetched.get("source_type") or "url",
                source_ref=fetched.get("url") or url,
                mode=mode,
                user_name=user_name,
            )
            title = summarized.get("title") or fetched.get("title") or url
            summary = (summarized.get("summary") or "").strip()
            via = fetched.get("fetch_via") or "direct"
            # Store flat bullets only — nested ## Summary / ### Key points in briefs
            # were getting pasted into drafts and breaking structure.
            flat_points = flatten_summary_to_bullets(
                summary,
                fallback_text=fetched.get("text") or "",
                limit=8,
            )
            points_md = "\n".join(f"- {p}" for p in flat_points) if flat_points else "- (no extractable points)"
            block = (
                f"### {title}\n"
                f"Source: {fetched.get('url') or url}\n"
                f"Fetched via: {via}\n\n"
                f"{points_md}\n"
            )
            blocks.append(block)
            citations.append({"title": str(title), "url": str(fetched.get("url") or url)})
            ok.append({"title": str(title), "url": str(fetched.get("url") or url), "via": str(via)})
            notes.append(f"Ingested {url} via {via}.")
        except ValueError as exc:
            failed.append({"url": url, "error": str(exc)})
            notes.append(f"Could not ingest {url}: {exc}")

    briefs_md = ""
    if blocks:
        briefs_md = "## Linked sources (fetched from Research prompt URLs)\n\n" + "\n---\n\n".join(
            blocks
        )
        briefs_md += (
            "\n\nUse these linked sources when drafting. Cite them with markdown links. "
            "Do not invent quotes or numbers not present in the briefs.\n"
        )

    return {
        "urls": urls,
        "briefs_md": briefs_md,
        "notes": " ".join(notes).strip(),
        "citations": citations,
        "failed": failed,
        "ok": ok,
    }


def flatten_summary_to_bullets(
    summary_md: str,
    *,
    fallback_text: str = "",
    limit: int = 8,
) -> list[str]:
    """Turn nested summary markdown into plain one-line bullets (no headers)."""
    raw = summary_md or ""
    bullets: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        # Drop markdown headings entirely.
        if re.match(r"^#{1,6}\s+", s):
            continue
        if re.match(r"(?i)^(summary|key points|analyst prompt|open questions)\s*:?\s*$", s):
            continue
        if s.startswith(("- ", "* ", "• ")):
            s = s[2:].strip()
        elif re.match(r"^\d+[.)]\s+", s):
            s = re.sub(r"^\d+[.)]\s+", "", s).strip()
        # Strip leftover bold/italic markers and nested heading crumbs.
        s = re.sub(r"[#*_`]+", "", s).strip()
        s = re.sub(r"\s+", " ", s)
        if len(s) < 25:
            continue
        if re.search(r"(?i)\b(key points|open questions|evidence gaps|analyst prompt)\b", s) and len(s) < 80:
            continue
        bullets.append(s)
        if len(bullets) >= limit:
            break
    if bullets:
        return bullets

    # Fallback: sentences from article text.
    body = _normalize_ws(fallback_text or raw)
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", body) if len(p.strip()) > 40]
    out: list[str] = []
    for p in parts[: max(3, limit)]:
        p = re.sub(r"[#*_`]+", "", p)
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            out.append(p[:280])
        if len(out) >= limit:
            break
    return out


def local_summarize(text: str, *, title: str = "", max_sentences: int = 8) -> str:
    """Cheap extractive summary without an LLM."""
    body = _normalize_ws(text or "")
    if not body:
        return "No content to summarize."

    # Split into sentences roughly
    parts = re.split(r"(?<=[.!?])\s+", body)
    sentences = [p.strip() for p in parts if len(p.strip()) > 40]
    if not sentences:
        sentences = [body[:500]]

    # Score by keyword density / length balance
    stop = {
        "the", "and", "for", "that", "with", "this", "from", "are", "was", "were",
        "have", "has", "will", "your", "their", "about", "into", "than", "then",
    }
    words = re.findall(r"[a-zA-Z']+", body.lower())
    freq: dict[str, int] = {}
    for w in words:
        if len(w) < 4 or w in stop:
            continue
        freq[w] = freq.get(w, 0) + 1

    ranked: list[tuple[float, int, str]] = []
    for i, s in enumerate(sentences[:80]):
        sw = re.findall(r"[a-zA-Z']+", s.lower())
        score = sum(freq.get(w, 0) for w in sw) / max(len(sw), 1)
        # Prefer earlier content slightly
        score += max(0, 3 - i * 0.05)
        ranked.append((score, i, s))
    ranked.sort(key=lambda t: (-t[0], t[1]))
    chosen = sorted(ranked[: max(3, min(max_sentences, 12))], key=lambda t: t[1])
    bullets = [c[2] for c in chosen]

    header = f"## Summary: {title}\n\n" if title else "## Summary\n\n"
    out = header + "### Key points\n" + "\n".join(f"- {b}" for b in bullets)
    out += (
        "\n\n### Analyst prompt\n"
        "What decision does this source inform? What is residual risk or open evidence still needed?\n"
    )
    return strip_banned_style(out)


def live_summarize(
    db,
    text: str,
    *,
    title: str = "",
    source_label: str = "",
    user_name: str = "",
) -> dict[str, Any]:
    from app.services.llm import chat, list_active_providers

    active = list_active_providers(db, purpose="research")
    if not active:
        return {
            "summary": local_summarize(text, title=title),
            "used_live": False,
            "provider": None,
            "model": None,
            "note": "No research token active; used local extractive summary.",
        }

    item = active[0]
    provider = item["provider"]
    preferred = (item.get("model") or "").strip() or None
    prompt_body = text[:MAX_SUMMARY_INPUT]
    live = chat(
        db,
        provider=provider,
        model=preferred,
        system=(
            "You summarize sources for a Security Operations research analyst. "
            "Be direct. No em dashes, double hyphens, or AI cliches. "
            "Focus on decisions, residual risk, methods, and evidence. "
            "Do not invent citations or numbers not in the source."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Source: {title or source_label or 'document'}\n\n"
                    "Write markdown with:\n"
                    "## Summary\n"
                    "### Key points (5-8 bullets)\n"
                    "### Relevance to OffSec / Exposure / VM (if any)\n"
                    "### Open questions / evidence gaps\n"
                    "### One-line takeaway for a security leader\n\n"
                    f"TEXT:\n{prompt_body}"
                ),
            }
        ],
        max_tokens=1400,
        temperature=0.3,
        purpose="summarize",
        created_by=user_name,
    )
    if live.content and not live.error:
        return {
            "summary": humanize_text(strip_banned_style(live.content), strength="medium"),
            "used_live": True,
            "provider": provider,
            "model": live.model,
            "note": f"Live summary via {provider}" + (f" ({live.model})" if live.model else ""),
        }
    return {
        "summary": local_summarize(text, title=title),
        "used_live": False,
        "provider": provider,
        "model": None,
        "note": f"Live summary failed ({live.error or 'empty'}); used local extractive summary.",
    }


def summarize_payload(
    db,
    *,
    text: str,
    title: str = "",
    source_type: str = "text",
    source_ref: str = "",
    mode: str = "auto",
    user_name: str = "",
    ocr_used: bool = False,
) -> dict[str, Any]:
    mode_n = (mode or "auto").strip().lower()
    if mode_n not in {"local", "live", "auto"}:
        mode_n = "auto"
    body = (text or "").strip()
    if not body:
        raise ValueError("No text to summarize.")
    if len(body) > MAX_SUMMARY_INPUT:
        body = body[:MAX_SUMMARY_INPUT]

    if mode_n == "local":
        summary = local_summarize(body, title=title)
        result = {
            "summary": summary,
            "used_live": False,
            "provider": None,
            "model": None,
            "note": "Local extractive summary.",
        }
    elif mode_n == "live":
        result = live_summarize(
            db, body, title=title, source_label=source_ref, user_name=user_name
        )
        if not result.get("used_live"):
            # Force message clarity for live-only requests
            from app.services.llm import list_active_providers

            if not list_active_providers(db, purpose="research"):
                raise ValueError(
                    "Live summarize needs an active research-enabled token in Security."
                )
    else:
        result = live_summarize(
            db, body, title=title, source_label=source_ref, user_name=user_name
        )

    return {
        **result,
        "mode": "live" if result.get("used_live") else "local",
        "requested_mode": mode_n,
        "source_type": source_type,
        "source_ref": source_ref,
        "title": title or source_ref or "Summary",
        "char_count": len(body),
        "ocr_used": ocr_used,
        "text_preview": body[:1200],
    }
