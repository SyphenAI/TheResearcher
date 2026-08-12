"""Generate Mermaid diagrams from research context."""

from __future__ import annotations

import re
from typing import Any


def attack_path_mermaid(title: str, techniques: list[dict[str, str]], notes: str = "") -> str:
    safe_title = _safe(title or "Attack path")
    lines = ["flowchart LR", f"  A[\"{_safe('Internet / Actor')}\"] --> B[\"{_safe(safe_title)}\"]"]
    prev = "B"
    for i, tech in enumerate(techniques[:8]):
        node = f"T{i}"
        label = f"{tech.get('id', '')} {tech.get('name', '')}".strip()
        lines.append(f"  {prev} --> {node}[\"{_safe(label)}\"]")
        prev = node
    lines.append(f"  {prev} --> Z[\"{_safe('Impact / Objective')}\"]")
    if notes:
        lines.append(f"  %% {_safe(notes)[:120]}")
    return "\n".join(lines)


def stride_mermaid(mappings: list[dict[str, Any]]) -> str:
    lines = ["flowchart TB", "  Asset[\"Asset / Process\"]"]
    for i, m in enumerate(mappings[:12]):
        cat = m.get("category") or m.get("stride") or f"C{i}"
        note = m.get("note") or m.get("finding") or ""
        lines.append(f"  Asset --> N{i}[\"{_safe(str(cat))}: {_safe(str(note)[:40])}\"]")
    if len(lines) == 2:
        lines.append("  Asset --> None[\"No STRIDE mappings yet\"]")
    return "\n".join(lines)


def control_gap_mermaid(controls: list[dict[str, Any]]) -> str:
    lines = ["flowchart LR", "  Req[\"Control requirements\"]"]
    for i, c in enumerate(controls[:12]):
        name = c.get("name") or c.get("control") or f"Control {i}"
        status = (c.get("status") or "unknown").lower()
        shape = f"C{i}[\"{_safe(name)} ({_safe(status)})\"]"
        lines.append(f"  Req --> {shape}")
    return "\n".join(lines)


def from_section_text(text: str, kind: str = "attack") -> str:
    techs = []
    for match in re.finditer(r"\b(T\d{4}(?:\.\d{3})?)\b", text or ""):
        techs.append({"id": match.group(1), "name": "Mapped technique"})
    if kind == "stride":
        cats = []
        for name in ["Spoofing", "Tampering", "Repudiation", "Information Disclosure", "Denial of Service", "Elevation of Privilege"]:
            if re.search(name, text or "", re.I):
                cats.append({"category": name, "note": "mentioned in section"})
        return stride_mermaid(cats)
    return attack_path_mermaid("Section attack path", techs or [{"id": "T1190", "name": "Public app"}, {"id": "T1078", "name": "Valid Accounts"}])


def _safe(value: str) -> str:
    return (
        (value or "")
        .replace('"', "'")
        .replace("\n", " ")
        .replace(";", ",")
        .replace("--", ", ")
    )
