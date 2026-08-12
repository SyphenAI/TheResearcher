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
    data_dir = Path(get_settings().data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "app_settings.json"


def _write_settings(data: dict[str, Any]) -> dict[str, Any]:
    current = DEFAULTS.copy()
    current.update({k: v for k, v in data.items() if k in DEFAULTS})
    current["max_agent_pct"] = float(min(100.0, max(0.0, float(current["max_agent_pct"]))))
    current["max_ai_checker_pct"] = float(
        min(100.0, max(0.0, float(current["max_ai_checker_pct"])))
    )
    current["evidence_coverage_min_pct"] = float(
        min(100.0, max(0.0, float(current["evidence_coverage_min_pct"])))
    )
    path = settings_file()
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def load_app_settings() -> dict[str, Any]:
    path = settings_file()
    if not path.exists():
        # Write defaults directly. Do not call save_app_settings() here
        # (that would recurse back into load_app_settings).
        return _write_settings(DEFAULTS.copy())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _write_settings(DEFAULTS.copy())
    except (OSError, json.JSONDecodeError):
        return _write_settings(DEFAULTS.copy())
    merged = DEFAULTS.copy()
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    return merged


def save_app_settings(updates: dict[str, Any]) -> dict[str, Any]:
    path = settings_file()
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except (OSError, json.JSONDecodeError):
            existing = {}
    else:
        existing = {}
    current = DEFAULTS.copy()
    current.update({k: v for k, v in existing.items() if k in DEFAULTS})
    current.update({k: v for k, v in updates.items() if k in DEFAULTS})
    return _write_settings(current)
