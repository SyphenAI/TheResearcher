"""Topic follow feed: world news (Google News RSS) + recent scholarly hits."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.services.scholar_search import search_crossref, search_semantic_scholar

USER_AGENT = "TheResearcher/0.2 (local research desk; topic feed)"


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_rss_date(value: str) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:  # noqa: BLE001
        return value


def fetch_google_news(topic: str, *, limit: int = 6) -> list[dict[str, Any]]:
    q = (topic or "").strip()
    if len(q) < 2:
        return []
    url = (
        "https://news.google.com/rss/search"
        f"?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        with httpx.Client(timeout=20.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return []
            root = ET.fromstring(resp.text)
    except Exception:  # noqa: BLE001
        return []

    items: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = _clean(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        pub = _parse_rss_date(item.findtext("pubDate") or "")
        source = _clean(item.findtext("source") or "")
        desc = _clean(item.findtext("description") or "")
        if not title:
            continue
        items.append(
            {
                "kind": "news",
                "topic": q,
                "title": title,
                "url": link,
                "source": source or "Google News",
                "published_at": pub,
                "snippet": desc[:280],
                "provider": "google_news",
            }
        )
        if len(items) >= max(1, min(limit, 12)):
            break
    return items


def fetch_recent_papers(
    topic: str,
    *,
    limit: int = 5,
    semantic_scholar_key: str | None = None,
) -> list[dict[str, Any]]:
    q = (topic or "").strip()
    if len(q) < 2:
        return []
    # Prefer Crossref; S2 as backup for CS/security depth.
    rows = search_crossref(q, limit=max(limit, 8))
    if len(rows) < 3:
        rows.extend(
            search_semantic_scholar(q, limit=max(limit, 6), api_key=semantic_scholar_key)
        )

    # Prefer newer / more cited among topical hits.
    def sort_key(r: dict[str, Any]) -> tuple:
        try:
            y = int(r.get("year") or 0)
        except ValueError:
            y = 0
        return (-y, -int(r.get("cited_by_count") or 0))

    rows = sorted(rows, key=sort_key)
    out: list[dict[str, Any]] = []
    for r in rows[: max(1, min(limit, 10))]:
        out.append(
            {
                "kind": "paper",
                "topic": q,
                "title": r.get("title") or "Untitled",
                "url": r.get("url") or "",
                "source": r.get("venue") or ",".join(r.get("sources") or [r.get("source") or "scholar"]),
                "published_at": str(r.get("year") or ""),
                "snippet": (r.get("abstract") or "")[:280],
                "author": r.get("author") or "",
                "cited_by_count": r.get("cited_by_count") or 0,
                "doi": r.get("doi") or "",
                "provider": r.get("source") or "scholar",
                "item": r,
            }
        )
    return out


def build_topic_feed(
    topics: list[str],
    *,
    per_topic_news: int = 4,
    per_topic_papers: int = 3,
    semantic_scholar_key: str | None = None,
    openalex_key: str | None = None,
) -> dict[str, Any]:
    _ = openalex_key  # reserved; Crossref/S2 are enough for feed latency
    cleaned: list[str] = []
    seen_t: set[str] = set()
    for t in topics or []:
        s = str(t or "").strip()
        if len(s) < 2:
            continue
        key = s.lower()
        if key in seen_t:
            continue
        seen_t.add(key)
        cleaned.append(s)
        if len(cleaned) >= 8:
            break

    if not cleaned:
        return {
            "topics": [],
            "items": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "message": "Add follow topics in Settings to build a research news feed.",
        }

    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for topic in cleaned:
        try:
            items.extend(fetch_google_news(topic, limit=per_topic_news))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"news/{topic}: {exc}")
        try:
            items.extend(
                fetch_recent_papers(
                    topic,
                    limit=per_topic_papers,
                    semantic_scholar_key=semantic_scholar_key,
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"papers/{topic}: {exc}")

    # Dedupe by URL/title
    merged: dict[str, dict[str, Any]] = {}
    for it in items:
        key = (it.get("url") or "").lower().strip() or re.sub(
            r"[^a-z0-9]+", "", (it.get("title") or "").lower()
        )[:100]
        if not key:
            continue
        if key not in merged:
            merged[key] = it

    ranked = list(merged.values())

    def _rank(it: dict[str, Any]) -> tuple:
        # Prefer fresher news first, then papers with citations.
        kind_rank = 0 if it.get("kind") == "news" else 1
        pub = it.get("published_at") or ""
        return (kind_rank, pub if isinstance(pub, str) else "", -int(it.get("cited_by_count") or 0))

    # Sort news by published_at desc roughly: put ISO-like dates first
    news = [i for i in ranked if i.get("kind") == "news"]
    papers = [i for i in ranked if i.get("kind") == "paper"]
    news.sort(key=lambda i: i.get("published_at") or "", reverse=True)
    papers.sort(key=lambda i: (-int(i.get("cited_by_count") or 0), str(i.get("published_at") or "")), reverse=False)
    papers.sort(key=lambda i: str(i.get("published_at") or "0"), reverse=True)

    # Interleave a bit: keep chronological-ish feed with papers mixed in
    combined = news[:24] + papers[:16]
    combined = combined[:40]

    return {
        "topics": cleaned,
        "items": combined,
        "news_count": len(news),
        "paper_count": len(papers),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "errors": errors,
        "message": (
            f"Feed for {len(cleaned)} topic(s): {len(news)} news · {len(papers)} papers."
            if combined
            else "No feed items returned. Check network or refine follow topics."
        ),
        "note": (
            "News via Google News RSS. Papers via Crossref/Semantic Scholar. "
            "Edit follow topics in Settings."
        ),
        "stale_after_minutes": 30,
    }
