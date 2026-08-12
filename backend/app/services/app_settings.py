"""Global app rules stored locally under data/ (not git)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import get_settings

DEFAULTS: dict[str, Any] = {
    "max_agent_pct": 10.0,
    "max_ai_checker_pct": 10.0,
    "evidence_coverage_min_pct": 70.0,
    "enforce_publish_gate": True,
    "allow_force_export": True,
    "default_evidence_mode": True,
    "default_template_key": "blank",
    "require_citations_for_publish": True,
    "humanize_before_export_hint": True,
}


def settings_file() -> Path:
    path = get_settings().data_dir / "app_settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_app_settings() -> dict[str, Any]:
    path = settings_file()
    if not path.exists():
        save_app_settings(DEFAULTS.copy())
        return DEFAULTS.copy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULTS.copy()
    merged = DEFAULTS.copy()
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    return merged


def save_app_settings(updates: dict[str, Any]) -> dict[str, Any]:
    current = load_app_settings()
    for key, value in updates.items():
        if key not in DEFAULTS:
            continue
        current[key] = value
    # clamp percents
    current["max_agent_pct"] = float(min(100.0, max(0.0, current["max_agent_pct"])))
    current["max_ai_checker_pct"] = float(min(100.0, max(0.0, current["max_ai_checker_pct"])))
    current["evidence_coverage_min_pct"] = float(
        min(100.0, max(0.0, current["evidence_coverage_min_pct"]))
    )
    path = settings_file()
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current
