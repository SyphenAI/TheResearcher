#!/usr/bin/env python3
"""Minimal MCP-style stdio tool server for TheResearcher local API.

Exposes research, judge, ai-check, and extract helpers so host agents
(Claude, Cursor, etc.) can call the same local stack.

Run (with the app up on 50080 and a bearer token):

  set TR_TOKEN=...
  python mcp_server.py

Protocol: newline-delimited JSON requests:
  {"id":"1","method":"tools/list"}
  {"id":"2","method":"tools/call","params":{"name":"ai_check","arguments":{"text":"..."}}}
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("TR_BASE", "http://127.0.0.1:50080")
TOKEN = os.environ.get("TR_TOKEN", "")

TOOLS = [
    {
        "name": "health",
        "description": "Check TheResearcher local health",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_projects",
        "description": "List research projects",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "research_assistant",
        "description": "Run multi-agent research assistant",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "section_id": {"type": "integer"},
                "multi_agent": {"type": "boolean"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "ai_check",
        "description": "Score AI-likeness of text",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "evidence_analyze",
        "description": "Analyze claim/citation coverage",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "project_id": {"type": "integer"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "publish_gate",
        "description": "Evaluate publish readiness for a project",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "integer"}},
            "required": ["project_id"],
        },
    },
]


def api(method: str, path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "TheResearcher-MCP",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:500]}") from exc


def call_tool(name: str, args: dict):
    if name == "health":
        req = urllib.request.Request(f"{BASE}/api/health", headers={"User-Agent": "TheResearcher-MCP"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    if name == "list_projects":
        return api("GET", "/api/projects")
    if name == "research_assistant":
        return api(
            "POST",
            "/api/research/assistant",
            {
                "prompt": args.get("prompt", ""),
                "section_id": args.get("section_id"),
                "multi_agent": args.get("multi_agent", True),
                "rewrite_human": True,
                "mode": "research",
            },
        )
    if name == "ai_check":
        return api("POST", "/api/research/ai-check", {"text": args.get("text", ""), "source_label": "mcp"})
    if name == "evidence_analyze":
        return api(
            "POST",
            "/api/workspace/evidence/analyze",
            {"text": args.get("text", ""), "project_id": args.get("project_id")},
        )
    if name == "publish_gate":
        pid = args.get("project_id")
        return api("GET", f"/api/workspace/projects/{pid}/publish-gate")
    raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            mid = msg.get("id")
            method = msg.get("method")
            if method == "tools/list":
                print(json.dumps({"id": mid, "result": {"tools": TOOLS}}), flush=True)
            elif method == "tools/call":
                params = msg.get("params") or {}
                result = call_tool(params.get("name"), params.get("arguments") or {})
                print(json.dumps({"id": mid, "result": result}), flush=True)
            else:
                print(json.dumps({"id": mid, "error": f"unknown method {method}"}), flush=True)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"error": str(exc)}), flush=True)


if __name__ == "__main__":
    main()
