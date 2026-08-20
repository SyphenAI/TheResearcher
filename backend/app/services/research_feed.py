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


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    # ISO-ish
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        pass
    # RFC 2822 from RSS
    try:
        dt = parsedate_to_datetime(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        pass
    # Year-only (papers)
    if re.fullmatch(r"\d{4}", str(value).strip()):
        try:
            y = int(value)
            return datetime(y, 12, 31, tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _iso(dt: datetime | None) -> str:
    if not dt:
        return ""
    from app.services.timefmt import to_iso_utc

    return to_iso_utc(dt) or ""


def fetch_google_news(
    topic: str,
    *,
    limit: int = 8,
    days: int = 7,
) -> list[dict[str, Any]]:
    """Live pull from Google News RSS. Uses when:7d to bias toward recent items."""
    q = (topic or "").strip()
    if len(q) < 2:
        return []
    days = max(1, min(int(days or 7), 30))
    # Google News query operator keeps the feed focused on the last N days.
    q_rss = f"{q} when:{days}d"
    url = (
        "https://news.google.com/rss/search"
        f"?q={quote(q_rss)}&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        with httpx.Client(
            timeout=20.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return []
            root = ET.fromstring(resp.text)
    except Exception:  # noqa: BLE001
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = _clean(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        pub_raw = item.findtext("pubDate") or ""
        pub_dt = _parse_dt(pub_raw)
        source = _clean(item.findtext("source") or "")
        desc = _clean(item.findtext("description") or "")
        if not title:
            continue
        # Hard filter: only keep items with a parseable date inside the window.
        # If Google omits a date, still allow a small number (rare) as "undated recent".
        if pub_dt and pub_dt < cutoff:
            continue
        items.append(
            {
                "kind": "news",
                "topic": q,
                "title": title,
                "url": link,
                "source": source or "Google News",
                "published_at": _iso(pub_dt) if pub_dt else pub_raw,
                "published_ts": pub_dt.timestamp() if pub_dt else 0,
                "snippet": desc[:280],
                "provider": "google_news",
            }
        )
        if len(items) >= max(1, min(limit, 15)):
            break
    return items


def fetch_recent_papers(
    topic: str,
    *,
    limit: int = 5,
    days: int = 7,
    semantic_scholar_key: str | None = None,
) -> list[dict[str, Any]]:
    """Scholar hits biased to recent years; days window is soft (year granularity)."""
    q = (topic or "").strip()
    if len(q) < 2:
        return []
    rows = search_crossref(q, limit=max(limit, 10))
    if len(rows) < 3:
        rows.extend(
            search_semantic_scholar(q, limit=max(limit, 8), api_key=semantic_scholar_key)
        )

    now = datetime.now(timezone.utc)
    # Papers rarely have daily timestamps; keep current + previous year when days <= 30.
    min_year = now.year if days <= 14 else now.year - 1

    filtered: list[dict[str, Any]] = []
    for r in rows:
        try:
            y = int(r.get("year") or 0)
        except ValueError:
            y = 0
        if y and y < min_year:
            continue
        filtered.append(r)

    if not filtered:
        filtered = rows  # fall back if everything was older

    def sort_key(r: dict[str, Any]) -> tuple:
        try:
            y = int(r.get("year") or 0)
        except ValueError:
            y = 0
        return (-y, -int(r.get("cited_by_count") or 0))

    filtered = sorted(filtered, key=sort_key)
    out: list[dict[str, Any]] = []
    for r in filtered[: max(1, min(limit, 10))]:
        year = str(r.get("year") or "")
        pub_dt = _parse_dt(year)
        out.append(
            {
                "kind": "paper",
                "topic": q,
                "title": r.get("title") or "Untitled",
                "url": r.get("url") or "",
                "source": r.get("venue")
                or ",".join(r.get("sources") or [r.get("source") or "scholar"]),
                "published_at": year,
                "published_ts": pub_dt.timestamp() if pub_dt else 0,
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
    days: int = 7,
    per_topic_news: int = 5,
    per_topic_papers: int = 3,
    semantic_scholar_key: str | None = None,
    openalex_key: str | None = None,
) -> dict[str, Any]:
    """Live feed pull (no disk cache). Call on dashboard load or Update now."""
    _ = openalex_key
    days = max(1, min(int(days or 7), 30))
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

    generated_at = datetime.now(timezone.utc)
    if not cleaned:
        return {
            "topics": [],
            "items": [],
            "days": days,
            "generated_at": generated_at.isoformat(),
            "window_start": (generated_at - timedelta(days=days)).isoformat(),
            "live": True,
            "message": "Add follow topics in Settings to build a research news feed.",
        }

    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for topic in cleaned:
        try:
            items.extend(fetch_google_news(topic, limit=per_topic_news, days=days))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"news/{topic}: {exc}")
        try:
            items.extend(
                fetch_recent_papers(
                    topic,
                    limit=per_topic_papers,
                    days=days,
                    semantic_scholar_key=semantic_scholar_key,
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"papers/{topic}: {exc}")

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
    news = [i for i in ranked if i.get("kind") == "news"]
    papers = [i for i in ranked if i.get("kind") == "paper"]
    news.sort(key=lambda i: float(i.get("published_ts") or 0), reverse=True)
    papers.sort(
        key=lambda i: (
            float(i.get("published_ts") or 0),
            int(i.get("cited_by_count") or 0),
        ),
        reverse=True,
    )

    # Chronological news first, then recent papers.
    combined = news[:24] + papers[:12]
    combined = combined[:36]

    return {
        "topics": cleaned,
        "items": combined,
        "news_count": len(news),
        "paper_count": len(papers),
        "days": days,
        "generated_at": generated_at.isoformat(),
        "window_start": (generated_at - timedelta(days=days)).isoformat(),
        "live": True,
        "errors": errors,
        "message": (
            f"Live feed (last {days} days) · {len(cleaned)} topic(s) · "
            f"{len(news)} news · {len(papers)} papers."
            if combined
            else f"No items in the last {days} days. Try Refresh, broaden topics, or widen the window."
        ),
        "note": (
            "News is a live Google News RSS pull filtered to the selected window "
            f"(default {days} days). Papers are recent scholarly hits (year-level). "
            "Use Update now / Refresh feed to re-pull. Edit follow topics in Settings."
        ),
        "stale_after_minutes": 0,
    }
