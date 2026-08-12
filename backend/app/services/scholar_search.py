"""Scholarly article search for research notes (Crossref + optional Semantic Scholar / OpenAlex)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

USER_AGENT = "TheResearcher/0.2 (local research desk; mailto:researcher@localhost)"


def _terms(query: str) -> list[str]:
    return [t for t in re.split(r"\s+", (query or "").lower()) if len(t) > 1]


def _relevance(title: str, abstract: str, query: str) -> float:
    blob = f"{title} {abstract}".lower()
    terms = _terms(query)
    if not terms:
        return 0.0
    hits = sum(1 for t in terms if t in blob)
    return hits / max(len(terms), 1)


def _score_item(item: dict[str, Any], query: str) -> float:
    rel = _relevance(item.get("title") or "", item.get("abstract") or "", query)
    cites = float(item.get("cited_by_count") or 0)
    # Log-ish boost so mega-cited papers do not drown topical matches.
    cite_boost = min(2.5, (cites + 1) ** 0.35 / 3.0)
    year = item.get("year")
    year_boost = 0.0
    try:
        y = int(year)
        if y >= 2022:
            year_boost = 0.25
        elif y >= 2018:
            year_boost = 0.1
    except (TypeError, ValueError):
        pass
    return round(rel * 3.0 + cite_boost + year_boost, 4)


def _norm_key(item: dict[str, Any]) -> str:
    doi = (item.get("doi") or "").lower().strip()
    if doi:
        return f"doi:{doi}"
    title = re.sub(r"[^a-z0-9]+", "", (item.get("title") or "").lower())
    return f"t:{title[:80]}"


def search_crossref(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if len(q) < 2:
        return []
    url = (
        "https://api.crossref.org/works"
        f"?query={quote(q)}&rows={max(1, min(limit, 20))}"
        "&select=DOI,title,author,published-print,published-online,container-title,"
        "abstract,URL,is-referenced-by-count,type"
        "&mailto=researcher@localhost"
    )
    try:
        with httpx.Client(timeout=25.0, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return []
            data = resp.json()
    except Exception:  # noqa: BLE001
        return []

    out: list[dict[str, Any]] = []
    for item in (data.get("message") or {}).get("items") or []:
        titles = item.get("title") or []
        title = titles[0] if titles else ""
        if not title:
            continue
        authors = []
        for a in item.get("author") or []:
            name = " ".join(x for x in [a.get("given"), a.get("family")] if x).strip()
            if name:
                authors.append(name)
        year = ""
        for key in ("published-print", "published-online"):
            parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
            if parts:
                year = str(parts[0])
                break
        abstract = item.get("abstract") or ""
        abstract = re.sub(r"<[^>]+>", " ", abstract)
        abstract = re.sub(r"\s+", " ", abstract).strip()
        doi = (item.get("DOI") or "").strip()
        url_out = item.get("URL") or (f"https://doi.org/{doi}" if doi else "")
        venue = ""
        ct = item.get("container-title") or []
        if ct:
            venue = ct[0]
        out.append(
            {
                "source": "crossref",
                "title": title,
                "authors": authors,
                "author": ", ".join(authors[:4]) + (" et al." if len(authors) > 4 else ""),
                "year": year,
                "venue": venue,
                "abstract": abstract[:600],
                "doi": doi,
                "url": url_out,
                "cited_by_count": int(item.get("is-referenced-by-count") or 0),
                "work_type": item.get("type") or "",
            }
        )
    return out


def search_semantic_scholar(
    query: str,
    *,
    limit: int = 10,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if len(q) < 2:
        return []
    fields = "title,authors,year,abstract,url,citationCount,externalIds,venue"
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={quote(q)}&limit={max(1, min(limit, 20))}&fields={fields}"
    )
    headers = {"User-Agent": USER_AGENT}
    if api_key:
        headers["x-api-key"] = api_key
    try:
        with httpx.Client(timeout=25.0, headers=headers) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return []
            data = resp.json()
    except Exception:  # noqa: BLE001
        return []

    out: list[dict[str, Any]] = []
    for item in data.get("data") or []:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        authors = [a.get("name") for a in (item.get("authors") or []) if a.get("name")]
        ext = item.get("externalIds") or {}
        doi = (ext.get("DOI") or "").strip()
        url_out = item.get("url") or (f"https://doi.org/{doi}" if doi else "")
        abstract = (item.get("abstract") or "").strip()
        out.append(
            {
                "source": "semantic_scholar",
                "title": title,
                "authors": authors,
                "author": ", ".join(authors[:4]) + (" et al." if len(authors) > 4 else ""),
                "year": str(item.get("year") or ""),
                "venue": item.get("venue") or "",
                "abstract": abstract[:600],
                "doi": doi,
                "url": url_out,
                "cited_by_count": int(item.get("citationCount") or 0),
                "work_type": "paper",
            }
        )
    return out


def search_openalex(
    query: str,
    *,
    limit: int = 10,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if len(q) < 2:
        return []
    url = (
        "https://api.openalex.org/works"
        f"?search={quote(q)}&per_page={max(1, min(limit, 20))}"
        "&select=id,doi,title,authorships,publication_year,cited_by_count,"
        "primary_location,abstract_inverted_index,type"
    )
    headers = {"User-Agent": USER_AGENT}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        with httpx.Client(timeout=25.0, headers=headers) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return []
            data = resp.json()
    except Exception:  # noqa: BLE001
        return []

    out: list[dict[str, Any]] = []
    for item in data.get("results") or []:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        authors = []
        for a in item.get("authorships") or []:
            name = ((a.get("author") or {}).get("display_name") or "").strip()
            if name:
                authors.append(name)
        doi = (item.get("doi") or "").replace("https://doi.org/", "").strip()
        loc = item.get("primary_location") or {}
        url_out = (loc.get("landing_page_url") or "") or (
            f"https://doi.org/{doi}" if doi else item.get("id") or ""
        )
        venue = ((loc.get("source") or {}).get("display_name") or "").strip()
        # OpenAlex abstracts are often inverted index; skip rebuild for speed unless short.
        abstract = ""
        inv = item.get("abstract_inverted_index")
        if isinstance(inv, dict) and len(inv) < 400:
            try:
                positions: list[tuple[int, str]] = []
                for word, idxs in inv.items():
                    for i in idxs:
                        positions.append((i, word))
                positions.sort()
                abstract = " ".join(w for _, w in positions)[:600]
            except Exception:  # noqa: BLE001
                abstract = ""
        out.append(
            {
                "source": "openalex",
                "title": title,
                "authors": authors,
                "author": ", ".join(authors[:4]) + (" et al." if len(authors) > 4 else ""),
                "year": str(item.get("publication_year") or ""),
                "venue": venue,
                "abstract": abstract,
                "doi": doi,
                "url": url_out,
                "cited_by_count": int(item.get("cited_by_count") or 0),
                "work_type": item.get("type") or "",
            }
        )
    return out


def search_scholar(
    query: str,
    *,
    limit: int = 12,
    sources: list[str] | None = None,
    semantic_scholar_key: str | None = None,
    openalex_key: str | None = None,
) -> dict[str, Any]:
    """Search multiple scholarly APIs and rank for topic fit + impact."""
    q = (query or "").strip()
    if len(q) < 2:
        return {
            "query": q,
            "total": 0,
            "results": [],
            "sources_tried": [],
            "message": "Type at least 2 characters.",
        }

    wanted = sources or ["crossref", "semantic_scholar", "openalex"]
    wanted = [s.lower().strip() for s in wanted if s]
    per = max(5, min(int(limit or 12), 20))
    sources_tried: list[str] = []
    source_errors: list[str] = []
    merged: dict[str, dict[str, Any]] = {}

    def _add_all(rows: list[dict[str, Any]], source_name: str) -> None:
        sources_tried.append(source_name)
        for row in rows:
            key = _norm_key(row)
            if key in merged:
                # Prefer richer abstract / higher cite count.
                prev = merged[key]
                if (row.get("cited_by_count") or 0) > (prev.get("cited_by_count") or 0):
                    prev["cited_by_count"] = row["cited_by_count"]
                if len(row.get("abstract") or "") > len(prev.get("abstract") or ""):
                    prev["abstract"] = row["abstract"]
                if not prev.get("url") and row.get("url"):
                    prev["url"] = row["url"]
                prev["sources"] = sorted(set((prev.get("sources") or []) + [source_name]))
            else:
                item = dict(row)
                item["sources"] = [source_name]
                item["score"] = _score_item(item, q)
                merged[key] = item

    if "crossref" in wanted:
        try:
            _add_all(search_crossref(q, limit=per), "crossref")
        except Exception as exc:  # noqa: BLE001
            source_errors.append(f"crossref: {exc}")

    if "semantic_scholar" in wanted:
        try:
            _add_all(
                search_semantic_scholar(q, limit=per, api_key=semantic_scholar_key),
                "semantic_scholar",
            )
        except Exception as exc:  # noqa: BLE001
            source_errors.append(f"semantic_scholar: {exc}")

    if "openalex" in wanted:
        try:
            rows = search_openalex(q, limit=per, api_key=openalex_key)
            if rows:
                _add_all(rows, "openalex")
            else:
                sources_tried.append("openalex")
                if not openalex_key:
                    source_errors.append(
                        "openalex: no results (API key optional but often required now)"
                    )
        except Exception as exc:  # noqa: BLE001
            source_errors.append(f"openalex: {exc}")

    results = list(merged.values())
    for r in results:
        r["score"] = _score_item(r, q)
    results.sort(
        key=lambda r: (
            -float(r.get("score") or 0),
            -int(r.get("cited_by_count") or 0),
            str(r.get("year") or ""),
        )
    )
    results = results[: max(1, min(int(limit or 12), 25))]

    return {
        "query": q,
        "total": len(results),
        "results": results,
        "sources_tried": sources_tried,
        "source_errors": source_errors,
        "message": (
            ""
            if results
            else "No scholarly hits. Try a shorter topic phrase, technique name, or standard (e.g. MITRE ATT&CK exposure management)."
        ),
        "note": (
            "Ranked by topic match + citation impact + recency. "
            "Crossref is always free. Semantic Scholar works lightly without a key. "
            "OpenAlex may need a free API key in Settings."
        ),
    }


def to_citation_fields(item: dict[str, Any], style: str = "apa") -> dict[str, str]:
    """Map a scholar result into CitationCreate-ish fields."""
    title = (item.get("title") or "Untitled").strip()
    author = (item.get("author") or "Author").strip() or "Author"
    year = str(item.get("year") or "n.d.").strip() or "n.d."
    url = (item.get("url") or "").strip()
    if not url and item.get("doi"):
        url = f"https://doi.org/{item['doi']}"
    notes_bits = []
    if item.get("venue"):
        notes_bits.append(str(item["venue"]))
    if item.get("cited_by_count"):
        notes_bits.append(f"cited_by≈{item['cited_by_count']}")
    if item.get("sources"):
        notes_bits.append("via " + ",".join(item["sources"]))
    if item.get("abstract"):
        notes_bits.append(item["abstract"][:240])
    return {
        "style": style or "apa",
        "title": title,
        "url": url,
        "author": author,
        "year": year,
        "notes": " · ".join(notes_bits),
    }
