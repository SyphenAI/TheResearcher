"""Editable research templates stored locally under data/templates.json."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.services.frameworks_data import PROJECT_TEMPLATES


def templates_file() -> Path:
    path = get_settings().data_dir / "templates.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _slugify(value: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "template").strip().lower()).strip("_")
    return (base or "template")[:64]


def _normalize_template(key: str, raw: dict[str, Any]) -> dict[str, Any]:
    sections = raw.get("sections") or []
    clean_sections: list[str] = []
    for item in sections:
        if isinstance(item, str) and item.strip():
            clean_sections.append(item.strip())
        elif isinstance(item, dict) and item.get("title"):
            clean_sections.append(str(item["title"]).strip())
    if not clean_sections:
        clean_sections = ["Overview", "Analysis", "Findings", "Recommendations", "References"]

    section_defs = raw.get("section_defs")
    if not section_defs:
        section_defs = [
            {"title": title, "prompt": "", "seed": f"# {title}\n\n"} for title in clean_sections
        ]
    else:
        normalized_defs = []
        for sec in section_defs:
            title = str(sec.get("title") or "").strip()
            if not title:
                continue
            normalized_defs.append(
                {
                    "title": title,
                    "prompt": str(sec.get("prompt") or ""),
                    "seed": str(sec.get("seed") or f"# {title}\n\n"),
                }
            )
        if normalized_defs:
            section_defs = normalized_defs
            clean_sections = [s["title"] for s in section_defs]
        else:
            section_defs = [
                {"title": title, "prompt": "", "seed": f"# {title}\n\n"} for title in clean_sections
            ]

    return {
        "key": key,
        "title": str(raw.get("title") or key).strip() or key,
        "description": str(raw.get("description") or "").strip(),
        "sections": clean_sections,
        "section_defs": section_defs,
        "builtin": bool(raw.get("builtin", False)),
    }


def builtin_seed() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, val in PROJECT_TEMPLATES.items():
        payload = deepcopy(val)
        payload["builtin"] = True
        if not payload.get("section_defs"):
            payload["section_defs"] = [
                {"title": t, "prompt": "", "seed": f"# {t}\n\n"} for t in payload.get("sections", [])
            ]
        out[key] = _normalize_template(key, payload)
    return out


def load_templates() -> dict[str, dict[str, Any]]:
    path = templates_file()
    if not path.exists():
        seed = builtin_seed()
        _write_all(seed)
        return seed
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        seed = builtin_seed()
        _write_all(seed)
        return seed

    templates = raw.get("templates") if isinstance(raw, dict) else None
    if not isinstance(templates, dict) or not templates:
        seed = builtin_seed()
        _write_all(seed)
        return seed

    out: dict[str, dict[str, Any]] = {}
    for key, val in templates.items():
        if not isinstance(val, dict):
            continue
        out[str(key)] = _normalize_template(str(key), val)

    # Ensure builtins remain available; refresh empty prompts from code seeds.
    builtins = builtin_seed()
    changed = False
    for key, val in builtins.items():
        if key not in out:
            out[key] = val
            changed = True
            continue
        existing_defs = out[key].get("section_defs") or []
        has_prompts = any(str(d.get("prompt") or "").strip() for d in existing_defs)
        # Built-in packs get richer seeds from code when stored prompts are empty.
        if out[key].get("builtin") and not has_prompts:
            out[key] = val
            changed = True

    if not out:
        out = builtins
        changed = True
    if changed:
        _write_all(out)
    return out


def list_templates() -> list[dict[str, Any]]:
    data = load_templates()
    rows = list(data.values())
    rows.sort(key=lambda t: (0 if t.get("key") == "blank" else 1, t.get("title", "").lower()))
    return rows


def get_template(key: str) -> dict[str, Any] | None:
    data = load_templates()
    return data.get(key) or data.get("blank")


def _write_all(templates: dict[str, dict[str, Any]]) -> None:
    path = templates_file()
    payload = {
        "templates": {
            key: {
                "title": val["title"],
                "description": val.get("description", ""),
                "sections": val.get("sections", []),
                "section_defs": val.get("section_defs", []),
                "builtin": bool(val.get("builtin", False)),
            }
            for key, val in templates.items()
        }
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def create_template(
    *,
    title: str,
    description: str = "",
    sections: list[str] | None = None,
    section_defs: list[dict[str, Any]] | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    data = load_templates()
    base_key = _slugify(key or title)
    final_key = base_key
    n = 2
    while final_key in data:
        final_key = f"{base_key}_{n}"
        n += 1

    raw = {
        "title": title,
        "description": description,
        "sections": sections or [],
        "section_defs": section_defs,
        "builtin": False,
    }
    item = _normalize_template(final_key, raw)
    data[final_key] = item
    _write_all(data)
    return item


def update_template(key: str, updates: dict[str, Any]) -> dict[str, Any]:
    data = load_templates()
    if key not in data:
        raise KeyError(f"Template not found: {key}")
    current = deepcopy(data[key])
    if "title" in updates and updates["title"] is not None:
        current["title"] = str(updates["title"]).strip() or current["title"]
    if "description" in updates and updates["description"] is not None:
        current["description"] = str(updates["description"]).strip()
    if "sections" in updates and updates["sections"] is not None:
        current["sections"] = updates["sections"]
        # rebuild section_defs titles if only sections provided
        if "section_defs" not in updates:
            old_defs = {d["title"]: d for d in current.get("section_defs") or []}
            current["section_defs"] = [
                old_defs.get(title)
                or {"title": title, "prompt": "", "seed": f"# {title}\n\n"}
                for title in current["sections"]
            ]
    if "section_defs" in updates and updates["section_defs"] is not None:
        current["section_defs"] = updates["section_defs"]
        current["sections"] = [
            str(s.get("title") or "").strip()
            for s in updates["section_defs"]
            if str(s.get("title") or "").strip()
        ]
    item = _normalize_template(key, current)
    # preserve builtin flag from original unless explicitly clearing via recreate
    item["builtin"] = bool(data[key].get("builtin", False))
    data[key] = item
    _write_all(data)
    return item


def delete_template(key: str) -> None:
    data = load_templates()
    if key not in data:
        raise KeyError(f"Template not found: {key}")
    if key == "blank":
        raise ValueError("The blank template cannot be deleted.")
    del data[key]
    if not data:
        data = builtin_seed()
    _write_all(data)


def reset_templates_to_builtin() -> list[dict[str, Any]]:
    seed = builtin_seed()
    _write_all(seed)
    return list_templates()
