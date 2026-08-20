#!/usr/bin/env python3
"""TheResearcher MCP bridge — external AI agents call this local desk via tools.

============================================================================
WHAT THIS FILE IS
============================================================================
A stdio MCP server that sits *beside* the Docker/web app. Host agents
(Claude Desktop, Cursor, other MCP clients) connect here. This process then
HTTP-calls the same FastAPI endpoints the browser desk uses.

It is NOT the main product server. The desk still runs via:
  docker compose up  →  http://127.0.0.1:50080

============================================================================
TWO RUN MODES
============================================================================
1) Preferred — official MCP Python SDK (FastMCP, protocol-compatible hosts):
     pip install "mcp>=1.9,<2"
     set TR_TOKEN=...
     python mcp_server.py

2) Fallback — stdlib-only NDJSON (no pip). Same tools, simpler protocol:
     python mcp_server.py
   If the `mcp` package is missing, fallback starts automatically.

============================================================================
REQUIREMENTS
============================================================================
1) App healthy on TR_BASE (default http://127.0.0.1:50080)
2) TR_TOKEN = Bearer JWT from POST /api/auth/login  (or use tool login)
3) Optional: pip install "mcp>=1.9,<2" for real MCP hosts

Windows PowerShell:
  $env:TR_BASE = "http://127.0.0.1:50080"
  $env:TR_TOKEN = "<access_token>"
  python mcp_server.py

Claude Desktop config sketch (after pip install mcp):
  {
    "mcpServers": {
      "theresearcher": {
        "command": "python",
        "args": ["D:\\\\TheResearcher\\\\mcp_server.py"],
        "env": {
          "TR_BASE": "http://127.0.0.1:50080",
          "TR_TOKEN": "<jwt>"
        }
      }
    }
  }

============================================================================
TOOLS (name → local API)
============================================================================
  login                 POST /api/auth/login/json   (stores token in-process)
  health                GET  /api/health
  list_projects         GET  /api/projects
  get_project           GET  /api/projects/{id}
  list_sections         GET  /api/projects/{id}/sections
  update_section        PATCH .../sections/{id}
  resync_contributions  POST .../resync-contributions
  research_assistant    POST /api/research/assistant   (slow multi-agent)
  apply_assistant       POST /api/research/assistant/apply
  rewrite               POST /api/research/rewrite     (local|live|auto)
  ai_check              POST /api/research/ai-check
  judge                 POST /api/research/judge
  evidence_analyze      POST /api/workspace/evidence/analyze
  publish_gate          GET  /api/workspace/projects/{id}/publish-gate
  scholar_search        GET  /api/workspace/scholar/search
  add_citation          POST /api/workspace/citations
  list_citations        GET  /api/workspace/projects/{id}/citations
  list_tasks            GET  /api/projects/{id}/tasks
  create_task           POST /api/projects/{id}/tasks
  update_task           PATCH /api/projects/{id}/tasks/{task_id}
  delete_task           DELETE /api/projects/{id}/tasks/{task_id}
  search_library        GET  /api/search
  list_providers        GET  /api/workspace/providers
  summarize             POST /api/research/summarize

============================================================================
LIMITS
============================================================================
- research_assistant often 1–3+ minutes (timeout 300s)
- apply_assistant is required to write paper (draft alone does not)
- Never returns raw API keys; Security tokens stay in the app DB
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = os.environ.get("TR_BASE", "http://127.0.0.1:50080").rstrip("/")
TOKEN = os.environ.get("TR_TOKEN", "")

# Long timeout for multi-agent research; shorter default for other calls.
DEFAULT_TIMEOUT = float(os.environ.get("TR_HTTP_TIMEOUT", "120"))
RESEARCH_TIMEOUT = float(os.environ.get("TR_RESEARCH_TIMEOUT", "300"))


# ---------------------------------------------------------------------------
# HTTP client → local FastAPI
# ---------------------------------------------------------------------------


def _headers(*, auth: bool = True) -> dict[str, str]:
    h = {
        "Content-Type": "application/json",
        "User-Agent": "TheResearcher-MCP",
        "Accept": "application/json",
    }
    if auth and TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def api(
    method: str,
    path: str,
    body: dict | None = None,
    *,
    auth: bool = True,
    timeout: float | None = None,
) -> Any:
    """JSON request against TR_BASE. path starts with /api/..."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method.upper(),
        headers=_headers(auth=auth),
    )
    wait = DEFAULT_TIMEOUT if timeout is None else timeout
    try:
        with urllib.request.urlopen(req, timeout=wait) as resp:
            raw = resp.read().decode("utf-8")
            if resp.status == 204 or not raw.strip():
                return {"ok": True, "status": resp.status}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:800]}") from exc


def _as_json_text(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool implementations (shared by FastMCP and NDJSON fallback)
# ---------------------------------------------------------------------------


def tool_login(username: str = "researcher", password: str = "password") -> dict:
    """Login and store JWT in this process (also set TR_TOKEN env for children)."""
    global TOKEN
    data = api(
        "POST",
        "/api/auth/login/json",
        {"username": username, "password": password},
        auth=False,
        timeout=30,
    )
    token = data.get("access_token") or ""
    if not token:
        raise RuntimeError(f"Login failed: {data}")
    TOKEN = token
    os.environ["TR_TOKEN"] = token
    return {
        "ok": True,
        "token_type": data.get("token_type", "bearer"),
        "note": "Token stored in this MCP process. Prefer env TR_TOKEN for permanent config.",
        "must_change_password": data.get("must_change_password"),
    }


def tool_health() -> dict:
    """Check local app health (no auth)."""
    return api("GET", "/api/health", auth=False, timeout=30)


def tool_list_projects() -> Any:
    """List non-archived research projects."""
    return api("GET", "/api/projects")


def tool_get_project(project_id: int) -> Any:
    """Get one project including progress and contribution %."""
    return api("GET", f"/api/projects/{int(project_id)}")


def tool_list_sections(project_id: int) -> Any:
    """List sections (title, prompt, content_md, agent/human chars)."""
    return api("GET", f"/api/projects/{int(project_id)}/sections")


def tool_update_section(
    project_id: int,
    section_id: int,
    content_md: str | None = None,
    prompt: str | None = None,
    title: str | None = None,
) -> Any:
    """Patch section paper body and/or research prompt."""
    body: dict[str, Any] = {}
    if content_md is not None:
        body["content_md"] = content_md
    if prompt is not None:
        body["prompt"] = prompt
    if title is not None:
        body["title"] = title
    if not body:
        raise ValueError("Provide content_md, prompt, and/or title")
    return api("PATCH", f"/api/projects/{int(project_id)}/sections/{int(section_id)}", body)


def tool_resync_contributions(project_id: int) -> Any:
    """Re-align agent/human % after deletes; fixes stuck 100% agent."""
    return api("POST", f"/api/projects/{int(project_id)}/resync-contributions")


def tool_research_assistant(
    prompt: str,
    section_id: int | None = None,
    multi_agent: bool = True,
    rewrite_human: bool = True,
) -> Any:
    """Run Research Assistant draft (does NOT write paper until apply_assistant)."""
    return api(
        "POST",
        "/api/research/assistant",
        {
            "prompt": prompt,
            "section_id": section_id,
            "multi_agent": multi_agent,
            "rewrite_human": rewrite_human,
            "mode": "research",
        },
        timeout=RESEARCH_TIMEOUT,
    )


def tool_apply_assistant(
    section_id: int,
    content: str,
    mark_as_agent: bool = True,
) -> Any:
    """Append assistant draft into section paper (bumps agent contribution if mark_as_agent)."""
    return api(
        "POST",
        "/api/research/assistant/apply",
        {
            "section_id": int(section_id),
            "content": content,
            "mark_as_agent": mark_as_agent,
        },
    )


def tool_rewrite(
    text: str,
    mode: str = "local",
    strength: str = "high",
    provider: str | None = None,
    model: str | None = None,
) -> Any:
    """Humanize rewrite. mode: local | live | auto. Does not save to a section."""
    body: dict[str, Any] = {
        "text": text,
        "mode": mode,
        "strength": strength,
    }
    if provider:
        body["provider"] = provider
    if model:
        body["model"] = model
    return api("POST", "/api/research/rewrite", body, timeout=RESEARCH_TIMEOUT)


def tool_ai_check(text: str, mode: str = "quick", source_label: str = "mcp") -> Any:
    """AI likelihood score. mode=quick is local free heuristic; live adds model panel."""
    return api(
        "POST",
        "/api/research/ai-check",
        {"text": text, "source_label": source_label, "mode": mode},
        timeout=RESEARCH_TIMEOUT if mode == "live" else DEFAULT_TIMEOUT,
    )


def tool_judge(
    text: str,
    project_id: int | None = None,
    section_id: int | None = None,
) -> Any:
    """Judge draft quality (local + judge-enabled models)."""
    body: dict[str, Any] = {"text": text}
    if project_id is not None:
        body["project_id"] = int(project_id)
    if section_id is not None:
        body["section_id"] = int(section_id)
    return api("POST", "/api/research/judge", body, timeout=RESEARCH_TIMEOUT)


def tool_evidence_analyze(text: str, project_id: int | None = None) -> Any:
    """Scan claims vs citations; returns evidence + publish_gate snippet."""
    body: dict[str, Any] = {"text": text}
    if project_id is not None:
        body["project_id"] = int(project_id)
    return api("POST", "/api/workspace/evidence/analyze", body)


def tool_publish_gate(project_id: int) -> Any:
    """Publish readiness blockers for a project."""
    return api("GET", f"/api/workspace/projects/{int(project_id)}/publish-gate")


def tool_scholar_search(
    q: str,
    limit: int = 12,
    year_from: int | None = None,
    year_to: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> Any:
    """World scholar search (Crossref + Semantic Scholar + OpenAlex + Google Scholar via SerpAPI)."""
    params: dict[str, str] = {"q": q, "limit": str(max(1, min(int(limit), 25)))}
    if date_from:
        params["date_from"] = str(date_from)
    if date_to:
        params["date_to"] = str(date_to)
    if year_from is not None:
        params["year_from"] = str(int(year_from))
    if year_to is not None:
        params["year_to"] = str(int(year_to))
    qs = urllib.parse.urlencode(params)
    return api("GET", f"/api/workspace/scholar/search?{qs}", timeout=60)


def tool_add_citation(
    project_id: int,
    title: str,
    url: str = "",
    author: str = "",
    year: str = "",
    style: str = "apa",
    notes: str = "",
) -> Any:
    """Add a citation row to a project library."""
    return api(
        "POST",
        "/api/workspace/citations",
        {
            "project_id": int(project_id),
            "title": title,
            "url": url,
            "author": author,
            "year": year,
            "style": style,
            "notes": notes,
        },
    )


def tool_list_citations(project_id: int) -> Any:
    """List citations for a project."""
    return api("GET", f"/api/workspace/projects/{int(project_id)}/citations")


def tool_list_tasks(project_id: int) -> Any:
    """List research tasks for a project."""
    return api("GET", f"/api/projects/{int(project_id)}/tasks")


def tool_create_task(project_id: int, title: str, status: str = "todo") -> Any:
    """Create a task (todo/done)."""
    return api(
        "POST",
        f"/api/projects/{int(project_id)}/tasks",
        {"title": title, "status": status},
    )


def tool_update_task(
    project_id: int,
    task_id: int,
    title: str | None = None,
    status: str | None = None,
) -> Any:
    """Update task title and/or status (todo|done)."""
    body: dict[str, Any] = {}
    if title is not None:
        body["title"] = title
    if status is not None:
        body["status"] = status
    if not body:
        raise ValueError("Provide title and/or status")
    return api("PATCH", f"/api/projects/{int(project_id)}/tasks/{int(task_id)}", body)


def tool_delete_task(project_id: int, task_id: int) -> Any:
    """Delete a task permanently."""
    return api("DELETE", f"/api/projects/{int(project_id)}/tasks/{int(task_id)}")


def tool_search_library(q: str, limit: int = 30) -> Any:
    """Full-text search local projects/sections/citations/artifacts."""
    qs = urllib.parse.urlencode({"q": q, "limit": str(max(1, min(int(limit), 100)))})
    return api("GET", f"/api/search?{qs}")


def tool_list_providers() -> Any:
    """List active research/judge providers (no secrets)."""
    return api("GET", "/api/workspace/providers")


def tool_summarize(
    text: str = "",
    url: str = "",
    mode: str = "auto",
) -> Any:
    """Summarize pasted text or a public URL. mode: local|live|auto."""
    body: dict[str, Any] = {"mode": mode}
    if text:
        body["text"] = text
    if url:
        body["url"] = url
    if not text and not url:
        raise ValueError("Provide text and/or url")
    return api("POST", "/api/research/summarize", body, timeout=RESEARCH_TIMEOUT)


# Dispatch table for NDJSON fallback
TOOL_IMPL: dict[str, Any] = {
    "login": tool_login,
    "health": tool_health,
    "list_projects": tool_list_projects,
    "get_project": tool_get_project,
    "list_sections": tool_list_sections,
    "update_section": tool_update_section,
    "resync_contributions": tool_resync_contributions,
    "research_assistant": tool_research_assistant,
    "apply_assistant": tool_apply_assistant,
    "rewrite": tool_rewrite,
    "ai_check": tool_ai_check,
    "judge": tool_judge,
    "evidence_analyze": tool_evidence_analyze,
    "publish_gate": tool_publish_gate,
    "scholar_search": tool_scholar_search,
    "add_citation": tool_add_citation,
    "list_citations": tool_list_citations,
    "list_tasks": tool_list_tasks,
    "create_task": tool_create_task,
    "update_task": tool_update_task,
    "delete_task": tool_delete_task,
    "search_library": tool_search_library,
    "list_providers": tool_list_providers,
    "summarize": tool_summarize,
}


# ---------------------------------------------------------------------------
# Official MCP SDK (FastMCP) when installed
# ---------------------------------------------------------------------------


def run_fastmcp() -> None:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        "TheResearcher",
        instructions=(
            "Local SecOps research desk bridge. App must be running on TR_BASE. "
            "Use login or TR_TOKEN. research_assistant is slow; apply_assistant writes paper. "
            "Do not invent API keys; tokens live in the app Security tab."
        ),
    )

    @mcp.tool()
    def login(username: str = "researcher", password: str = "password") -> str:
        """Login to TheResearcher and store JWT for subsequent tools."""
        return _as_json_text(tool_login(username, password))

    @mcp.tool()
    def health() -> str:
        """Check TheResearcher local health."""
        return _as_json_text(tool_health())

    @mcp.tool()
    def list_projects() -> str:
        """List research projects."""
        return _as_json_text(tool_list_projects())

    @mcp.tool()
    def get_project(project_id: int) -> str:
        """Get project metrics and metadata."""
        return _as_json_text(tool_get_project(project_id))

    @mcp.tool()
    def list_sections(project_id: int) -> str:
        """List sections for a project (includes content_md)."""
        return _as_json_text(tool_list_sections(project_id))

    @mcp.tool()
    def update_section(
        project_id: int,
        section_id: int,
        content_md: str | None = None,
        prompt: str | None = None,
        title: str | None = None,
    ) -> str:
        """Update section paper and/or prompt."""
        return _as_json_text(
            tool_update_section(project_id, section_id, content_md, prompt, title)
        )

    @mcp.tool()
    def resync_contributions(project_id: int) -> str:
        """Resync agent/human contribution after paper deletes."""
        return _as_json_text(tool_resync_contributions(project_id))

    @mcp.tool()
    def research_assistant(
        prompt: str,
        section_id: int | None = None,
        multi_agent: bool = True,
        rewrite_human: bool = True,
    ) -> str:
        """Run multi-agent Research Assistant. Slow (1-3+ min). Draft only until apply_assistant."""
        return _as_json_text(
            tool_research_assistant(prompt, section_id, multi_agent, rewrite_human)
        )

    @mcp.tool()
    def apply_assistant(section_id: int, content: str, mark_as_agent: bool = True) -> str:
        """Write assistant draft into section paper."""
        return _as_json_text(tool_apply_assistant(section_id, content, mark_as_agent))

    @mcp.tool()
    def rewrite(
        text: str,
        mode: str = "local",
        strength: str = "high",
        provider: str | None = None,
        model: str | None = None,
    ) -> str:
        """Humanize text (local rules or live model). mode=local|live|auto."""
        return _as_json_text(tool_rewrite(text, mode, strength, provider, model))

    @mcp.tool()
    def ai_check(text: str, mode: str = "quick") -> str:
        """Score AI likelihood. mode=quick (local) or live."""
        return _as_json_text(tool_ai_check(text, mode=mode))

    @mcp.tool()
    def judge(
        text: str,
        project_id: int | None = None,
        section_id: int | None = None,
    ) -> str:
        """Judge draft quality with local + live judge models."""
        return _as_json_text(tool_judge(text, project_id, section_id))

    @mcp.tool()
    def evidence_analyze(text: str, project_id: int | None = None) -> str:
        """Analyze uncited claims and evidence coverage."""
        return _as_json_text(tool_evidence_analyze(text, project_id))

    @mcp.tool()
    def publish_gate(project_id: int) -> str:
        """Evaluate publish readiness blockers."""
        return _as_json_text(tool_publish_gate(project_id))

    @mcp.tool()
    def scholar_search(
        q: str,
        limit: int = 12,
        year_from: int | None = None,
        year_to: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> str:
        """Search scholarly papers; optional date_from/date_to (YYYY-MM) or year_from/year_to."""
        return _as_json_text(
            tool_scholar_search(
                q,
                limit,
                year_from,
                year_to,
                date_from=date_from,
                date_to=date_to,
            )
        )

    @mcp.tool()
    def add_citation(
        project_id: int,
        title: str,
        url: str = "",
        author: str = "",
        year: str = "",
        style: str = "apa",
        notes: str = "",
    ) -> str:
        """Add citation to project library."""
        return _as_json_text(
            tool_add_citation(project_id, title, url, author, year, style, notes)
        )

    @mcp.tool()
    def list_citations(project_id: int) -> str:
        """List project citations."""
        return _as_json_text(tool_list_citations(project_id))

    @mcp.tool()
    def list_tasks(project_id: int) -> str:
        """List project tasks."""
        return _as_json_text(tool_list_tasks(project_id))

    @mcp.tool()
    def create_task(project_id: int, title: str, status: str = "todo") -> str:
        """Create a research task."""
        return _as_json_text(tool_create_task(project_id, title, status))

    @mcp.tool()
    def update_task(
        project_id: int,
        task_id: int,
        title: str | None = None,
        status: str | None = None,
    ) -> str:
        """Update task title/status (status=done to complete)."""
        return _as_json_text(tool_update_task(project_id, task_id, title, status))

    @mcp.tool()
    def delete_task(project_id: int, task_id: int) -> str:
        """Delete a task."""
        return _as_json_text(tool_delete_task(project_id, task_id))

    @mcp.tool()
    def search_library(q: str, limit: int = 30) -> str:
        """Search local project library text."""
        return _as_json_text(tool_search_library(q, limit))

    @mcp.tool()
    def list_providers() -> str:
        """List active LLM providers (no secrets)."""
        return _as_json_text(tool_list_providers())

    @mcp.tool()
    def summarize(text: str = "", url: str = "", mode: str = "auto") -> str:
        """Summarize text or public URL (local or live)."""
        return _as_json_text(tool_summarize(text, url, mode))

    mcp.run(transport="stdio")


# ---------------------------------------------------------------------------
# Stdlib NDJSON fallback (no mcp package)
# ---------------------------------------------------------------------------


def _tool_schemas() -> list[dict[str, Any]]:
    """Minimal JSON-schema-ish tool list for NDJSON hosts."""
    return [
        {"name": n, "description": (fn.__doc__ or n).strip(), "inputSchema": {"type": "object"}}
        for n, fn in TOOL_IMPL.items()
    ]


def call_tool(name: str, args: dict | None) -> Any:
    fn = TOOL_IMPL.get(name)
    if not fn:
        raise ValueError(f"Unknown tool: {name}. Known: {', '.join(sorted(TOOL_IMPL))}")
    args = args or {}
    # Filter unexpected keys so hosts can send extras
    import inspect

    sig = inspect.signature(fn)
    accepted = {
        k: v
        for k, v in args.items()
        if k in sig.parameters
    }
    return fn(**accepted)


def run_ndjson_fallback() -> None:
    """Line-oriented JSON protocol when official SDK is not installed."""
    print(
        json.dumps(
            {
                "event": "ready",
                "mode": "ndjson-fallback",
                "base": BASE,
                "has_token": bool(TOKEN),
                "tools": list(TOOL_IMPL.keys()),
                "hint": 'Send: {"id":"1","method":"tools/list"} or tools/call',
            }
        ),
        flush=True,
        file=sys.stderr,
    )
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            mid = msg.get("id")
            method = msg.get("method")
            if method in {"tools/list", "list_tools"}:
                print(json.dumps({"id": mid, "result": {"tools": _tool_schemas()}}), flush=True)
            elif method in {"tools/call", "call_tool"}:
                params = msg.get("params") or {}
                name = params.get("name") or params.get("tool")
                arguments = params.get("arguments") or params.get("args") or {}
                result = call_tool(name, arguments)
                print(json.dumps({"id": mid, "result": result}, default=str), flush=True)
            elif method == "initialize":
                print(
                    json.dumps(
                        {
                            "id": mid,
                            "result": {
                                "protocolVersion": "ndjson-fallback",
                                "serverInfo": {"name": "TheResearcher", "version": "0.2.0"},
                                "capabilities": {"tools": {}},
                            },
                        }
                    ),
                    flush=True,
                )
            else:
                print(json.dumps({"id": mid, "error": f"unknown method {method}"}), flush=True)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"error": str(exc)}), flush=True)


def main() -> None:
    # Prefer real MCP for Claude/Cursor; fall back to stdlib NDJSON.
    try:
        import mcp  # noqa: F401

        run_fastmcp()
    except ImportError:
        sys.stderr.write(
            "mcp package not installed — running stdlib NDJSON fallback.\n"
            'For Claude/Cursor: pip install "mcp>=1.9,<2"\n'
        )
        run_ndjson_fallback()


if __name__ == "__main__":
    main()
