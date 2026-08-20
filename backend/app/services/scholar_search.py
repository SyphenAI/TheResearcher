"""Scholarly article search for research notes.

Providers: Crossref, Semantic Scholar, OpenAlex, and Google Scholar via SerpAPI.
"""

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


def _parse_year(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        y = int(str(value).strip()[:4])
    except (TypeError, ValueError):
        return None
    if 1800 <= y <= 2100:
        return y
    return None


def _last_day_of_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    from datetime import date, timedelta

    return (date(year, month + 1, 1) - timedelta(days=1)).day


def _parse_date_bound(value: Any, *, end: bool = False) -> tuple[int | None, str | None]:
    """Parse YYYY / YYYY-MM / YYYY-MM-DD into (year, iso_date).

    start bound -> first day of precision; end bound -> last day of precision.
    """
    if value is None or value == "":
        return None, None
    raw = str(value).strip()
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", raw)
    if not m:
        # Fall back to year-only scrape (e.g. "2024-ish")
        y = _parse_year(raw)
        if y is None:
            return None, None
        iso = f"{y}-12-31" if end else f"{y}-01-01"
        return y, iso
    year = int(m.group(1))
    if not (1800 <= year <= 2100):
        return None, None
    month_s, day_s = m.group(2), m.group(3)
    if month_s is None:
        return year, (f"{year}-12-31" if end else f"{year}-01-01")
    month = int(month_s)
    if not (1 <= month <= 12):
        return year, (f"{year}-12-31" if end else f"{year}-01-01")
    if day_s is None:
        day = _last_day_of_month(year, month) if end else 1
        return year, f"{year:04d}-{month:02d}-{day:02d}"
    day = int(day_s)
    day = min(max(day, 1), _last_day_of_month(year, month))
    return year, f"{year:04d}-{month:02d}-{day:02d}"


def _bound_label(raw: Any, year: int | None, iso: str | None) -> str:
    text = str(raw or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", text):
        return text[:7]
    if year is not None:
        return str(year)
    if iso:
        return iso[:7]
    return "…"


def _normalize_date_range(
    *,
    date_from: int | str | None = None,
    date_to: int | str | None = None,
    year_from: int | str | None = None,
    year_to: int | str | None = None,
) -> dict[str, Any]:
    """Normalize optional date/year bounds for provider filters + post-filter."""
    # Prefer explicit date_* over year_* when both are sent.
    start_raw = date_from if date_from not in (None, "") else year_from
    end_raw = date_to if date_to not in (None, "") else year_to
    y_from, iso_from = _parse_date_bound(start_raw, end=False)
    y_to, iso_to = _parse_date_bound(end_raw, end=True)
    if iso_from and iso_to and iso_from > iso_to:
        start_raw, end_raw = end_raw, start_raw
        y_from, iso_from = _parse_date_bound(start_raw, end=False)
        y_to, iso_to = _parse_date_bound(end_raw, end=True)
    label = ""
    if iso_from or iso_to:
        label = f"{_bound_label(start_raw, y_from, iso_from)}–{_bound_label(end_raw, y_to, iso_to)}"
    return {
        "year_from": y_from,
        "year_to": y_to,
        "iso_from": iso_from,
        "iso_to": iso_to,
        "label": label,
    }


def _normalize_year_range(
    year_from: int | str | None = None,
    year_to: int | str | None = None,
) -> tuple[int | None, int | None]:
    bounds = _normalize_date_range(year_from=year_from, year_to=year_to)
    return bounds["year_from"], bounds["year_to"]


def _year_in_range(
    year: Any,
    year_from: int | None,
    year_to: int | None,
    *,
    include_unknown: bool = False,
) -> bool:
    if year_from is None and year_to is None:
        return True
    y = _parse_year(year)
    if y is None:
        return include_unknown
    if year_from is not None and y < year_from:
        return False
    if year_to is not None and y > year_to:
        return False
    return True


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


def search_crossref(
    query: str,
    *,
    limit: int = 10,
    year_from: int | None = None,
    year_to: int | None = None,
    iso_from: str | None = None,
    iso_to: str | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if len(q) < 2:
        return []
    filters: list[str] = []
    start = iso_from or (f"{year_from}-01-01" if year_from is not None else None)
    end = iso_to or (f"{year_to}-12-31" if year_to is not None else None)
    if start:
        filters.append(f"from-pub-date:{start}")
    if end:
        filters.append(f"until-pub-date:{end}")
    filter_q = f"&filter={quote(','.join(filters))}" if filters else ""
    url = (
        "https://api.crossref.org/works"
        f"?query={quote(q)}&rows={max(1, min(limit, 20))}"
        "&select=DOI,title,author,published-print,published-online,container-title,"
        "abstract,URL,is-referenced-by-count,type"
        f"{filter_q}"
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
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if len(q) < 2:
        return []
    fields = "title,authors,year,abstract,url,citationCount,externalIds,venue"
    # Semantic Scholar accepts year=YYYY or year=YYYY-YYYY (open ends with trailing/leading -)
    year_q = ""
    if year_from is not None and year_to is not None:
        year_q = f"&year={year_from}-{year_to}"
    elif year_from is not None:
        year_q = f"&year={year_from}-"
    elif year_to is not None:
        year_q = f"&year=-{year_to}"
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={quote(q)}&limit={max(1, min(limit, 20))}&fields={fields}{year_q}"
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
    year_from: int | None = None,
    year_to: int | None = None,
    iso_from: str | None = None,
    iso_to: str | None = None,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if len(q) < 2:
        return []
    filters: list[str] = []
    start = iso_from or (f"{year_from}-01-01" if year_from is not None else None)
    end = iso_to or (f"{year_to}-12-31" if year_to is not None else None)
    if start:
        filters.append(f"from_publication_date:{start}")
    if end:
        filters.append(f"to_publication_date:{end}")
    filter_q = f"&filter={quote(','.join(filters))}" if filters else ""
    url = (
        "https://api.openalex.org/works"
        f"?search={quote(q)}&per_page={max(1, min(limit, 20))}"
        "&select=id,doi,title,authorships,publication_year,cited_by_count,"
        "primary_location,abstract_inverted_index,type"
        f"{filter_q}"
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


def _extract_doi(*candidates: Any) -> str:
    for raw in candidates:
        if not raw:
            continue
        text = str(raw)
        m = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, flags=re.I)
        if m:
            return m.group(0).rstrip(").,;")
    return ""


def _parse_gs_publication(summary: str) -> tuple[str, str, str]:
    """Best-effort author / year / venue from Google Scholar publication_info.summary."""
    summary = (summary or "").strip()
    if not summary:
        return "", "", ""
    year = ""
    m_year = re.search(r"\b(19|20)\d{2}\b", summary)
    if m_year:
        year = m_year.group(0)
    # Typical: "A Author, B Author - Venue, 2021 - publisher.com"
    left = summary
    venue = ""
    if " - " in summary:
        parts = [p.strip() for p in summary.split(" - ") if p.strip()]
        if parts:
            left = parts[0]
        if len(parts) >= 2:
            venue = re.sub(r",?\s*(19|20)\d{2}\b", "", parts[1]).strip(" ,")
    authors = [a.strip() for a in re.split(r",\s*|\s+and\s+", left) if a.strip()]
    author = ", ".join(authors[:4]) + (" et al." if len(authors) > 4 else "")
    return author, year, venue


def search_google_scholar(
    query: str,
    *,
    limit: int = 10,
    api_key: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[dict[str, Any]]:
    """Google Scholar organic results via SerpAPI (requires api_key)."""
    q = (query or "").strip()
    key = (api_key or "").strip()
    if len(q) < 2 or not key:
        return []

    params: dict[str, Any] = {
        "engine": "google_scholar",
        "q": q,
        "api_key": key,
        "num": max(1, min(int(limit or 10), 20)),
        "hl": "en",
    }
    if year_from is not None:
        params["as_ylo"] = int(year_from)
    if year_to is not None:
        params["as_yhi"] = int(year_to)

    try:
        with httpx.Client(timeout=35.0, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get("https://serpapi.com/search.json", params=params)
            if resp.status_code >= 400:
                return []
            data = resp.json()
    except Exception:  # noqa: BLE001
        return []

    if isinstance(data, dict) and data.get("error"):
        return []

    out: list[dict[str, Any]] = []
    for item in data.get("organic_results") or []:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        pub = item.get("publication_info") or {}
        authors_list = [
            a.get("name")
            for a in (pub.get("authors") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        author_from_summary, year, venue = _parse_gs_publication(str(pub.get("summary") or ""))
        if authors_list:
            author = ", ".join(authors_list[:4]) + (" et al." if len(authors_list) > 4 else "")
            authors = authors_list
        else:
            author = author_from_summary
            authors = [a.strip() for a in author_from_summary.split(",") if a.strip()]

        link = (item.get("link") or "").strip()
        resources = item.get("resources") or []
        resource_links = [
            str(r.get("link") or "")
            for r in resources
            if isinstance(r, dict) and r.get("link")
        ]
        doi = _extract_doi(link, *resource_links, item.get("snippet") or "")
        url_out = link or (f"https://doi.org/{doi}" if doi else "")
        if doi and "doi.org" not in (url_out or "").lower():
            # Prefer a stable DOI landing page when we found one in resources.
            for cand in resource_links:
                if "doi.org" in cand.lower() or _extract_doi(cand):
                    url_out = cand if "doi.org" in cand.lower() else f"https://doi.org/{doi}"
                    break

        cited = 0
        try:
            cited = int(((item.get("inline_links") or {}).get("cited_by") or {}).get("total") or 0)
        except (TypeError, ValueError):
            cited = 0

        abstract = re.sub(r"\s+", " ", str(item.get("snippet") or "")).strip()
        out.append(
            {
                "source": "google_scholar",
                "title": title,
                "authors": authors,
                "author": author or "Author",
                "year": year,
                "venue": venue,
                "abstract": abstract[:600],
                "doi": doi,
                "url": url_out,
                "cited_by_count": cited,
                "work_type": str(item.get("type") or "paper"),
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
    serpapi_key: str | None = None,
    year_from: int | str | None = None,
    year_to: int | str | None = None,
    date_from: int | str | None = None,
    date_to: int | str | None = None,
) -> dict[str, Any]:
    """Search multiple scholarly APIs and rank for topic fit + impact.

    Optional date_from / date_to (YYYY, YYYY-MM, or YYYY-MM-DD). year_from / year_to
    still accepted. Crossref + OpenAlex use full dates; Semantic Scholar + Google Scholar
    use publication year. Google Scholar requires a SerpAPI key.
    """
    q = (query or "").strip()
    if len(q) < 2:
        return {
            "query": q,
            "total": 0,
            "results": [],
            "sources_tried": [],
            "year_from": None,
            "year_to": None,
            "date_from": None,
            "date_to": None,
            "message": "Type at least 2 characters.",
        }

    bounds = _normalize_date_range(
        date_from=date_from,
        date_to=date_to,
        year_from=year_from,
        year_to=year_to,
    )
    y_from = bounds["year_from"]
    y_to = bounds["year_to"]
    iso_from = bounds["iso_from"]
    iso_to = bounds["iso_to"]
    range_label = bounds["label"]

    wanted = sources or ["crossref", "semantic_scholar", "openalex", "google_scholar"]
    wanted = [s.lower().strip() for s in wanted if s]
    per = max(5, min(int(limit or 12), 20))
    sources_tried: list[str] = []
    source_errors: list[str] = []
    merged: dict[str, dict[str, Any]] = {}

    def _add_all(rows: list[dict[str, Any]], source_name: str) -> None:
        sources_tried.append(source_name)
        for row in rows:
            if not _year_in_range(row.get("year"), y_from, y_to, include_unknown=False):
                continue
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
            _add_all(
                search_crossref(
                    q,
                    limit=per,
                    year_from=y_from,
                    year_to=y_to,
                    iso_from=iso_from,
                    iso_to=iso_to,
                ),
                "crossref",
            )
        except Exception as exc:  # noqa: BLE001
            source_errors.append(f"crossref: {exc}")

    if "semantic_scholar" in wanted:
        try:
            _add_all(
                search_semantic_scholar(
                    q,
                    limit=per,
                    api_key=semantic_scholar_key,
                    year_from=y_from,
                    year_to=y_to,
                ),
                "semantic_scholar",
            )
        except Exception as exc:  # noqa: BLE001
            source_errors.append(f"semantic_scholar: {exc}")

    if "openalex" in wanted:
        try:
            rows = search_openalex(
                q,
                limit=per,
                api_key=openalex_key,
                year_from=y_from,
                year_to=y_to,
                iso_from=iso_from,
                iso_to=iso_to,
            )
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

    if "google_scholar" in wanted:
        if not (serpapi_key or "").strip():
            sources_tried.append("google_scholar")
            source_errors.append(
                "google_scholar: set SerpAPI key in Settings to include Google Scholar"
            )
        else:
            try:
                rows = search_google_scholar(
                    q,
                    limit=per,
                    api_key=serpapi_key,
                    year_from=y_from,
                    year_to=y_to,
                )
                if rows:
                    _add_all(rows, "google_scholar")
                else:
                    sources_tried.append("google_scholar")
                    source_errors.append(
                        "google_scholar: no results (check SerpAPI key / quota / query)"
                    )
            except Exception as exc:  # noqa: BLE001
                source_errors.append(f"google_scholar: {exc}")

    results = list(merged.values())
    for r in results:
        r["score"] = _score_item(r, q)
    results.sort(
        key=lambda r: (
            -float(r.get("score") or 0),
            -int(r.get("cited_by_count") or 0),
            -(_parse_year(r.get("year")) or 0),
        )
    )
    results = results[: max(1, min(int(limit or 12), 25))]

    range_note = f" Published {range_label}." if range_label else ""

    if results:
        empty_msg = ""
    elif range_label:
        empty_msg = (
            f"No scholarly hits in {range_label}. "
            "Try a tighter topic (add domain words like cybersecurity / exposure management), "
            "widen the date range, or clear the date filters."
        )
    else:
        empty_msg = (
            "No scholarly hits. Add domain terms to the query "
            "(e.g. cybersecurity exposure management prioritization), "
            "or try a technique / standard name."
        )

    return {
        "query": q,
        "total": len(results),
        "results": results,
        "sources_tried": sources_tried,
        "source_errors": source_errors,
        "year_from": y_from,
        "year_to": y_to,
        "date_from": iso_from[:7] if iso_from else None,
        "date_to": iso_to[:7] if iso_to else None,
        "message": empty_msg,
        "note": (
            "Ranked by topic match + citation impact + recency. "
            "Crossref/OpenAlex honor month-level dates; Semantic Scholar + Google Scholar "
            "filter by year. Google Scholar needs a SerpAPI key in Settings."
            + range_note
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
