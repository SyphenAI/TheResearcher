"""Local storage layout under the tool directory (never user home scatter).

Layout:
  storage/
    projects/{project_id}_{slug}/   active project files
    archive/{project_id}_{slug}/    soft-deleted projects
    tmp/                            short-lived upload staging
    .gitkeep
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings


def storage_root() -> Path:
    settings = get_settings()
    # Prefer explicit STORAGE_DIR; otherwise sibling of data_dir named storage,
    # or /app/storage in Docker when data_dir is /app/data.
    if getattr(settings, "storage_dir", None):
        root = Path(settings.storage_dir)
    else:
        data = Path(settings.data_dir)
        if data.name == "data":
            root = data.parent / "storage"
        else:
            root = data / "storage"
    _ensure_tree(root)
    return root


def projects_root() -> Path:
    path = storage_root() / "projects"
    path.mkdir(parents=True, exist_ok=True)
    return path


def archive_root() -> Path:
    path = storage_root() / "archive"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tmp_root() -> Path:
    path = storage_root() / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(title: str, project_id: int) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", (title or "project").strip().lower()).strip("-")
    base = (base or "project")[:48]
    return f"{project_id}_{base}"


def project_dir(project_id: int, title: str = "project", create: bool = True) -> Path:
    """Resolve active project folder; migrate legacy data/artifacts if present."""
    root = projects_root()
    existing = _find_folder(root, project_id)
    if existing:
        path = existing
    else:
        path = root / slugify(title, project_id)
    if create:
        path.mkdir(parents=True, exist_ok=True)
        (path / "artifacts").mkdir(exist_ok=True)
        (path / "exports").mkdir(exist_ok=True)
        (path / "uploads").mkdir(exist_ok=True)
        meta = path / "project.json"
        if not meta.exists():
            meta.write_text(
                json.dumps(
                    {
                        "project_id": project_id,
                        "title": title,
                        "status": "active",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        _maybe_migrate_legacy_artifacts(project_id, path / "artifacts")
    return path


def artifacts_dir(project_id: int, title: str = "project") -> Path:
    path = project_dir(project_id, title) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def exports_dir(project_id: int, title: str = "project") -> Path:
    path = project_dir(project_id, title) / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def archive_project_folder(project_id: int, title: str = "project") -> Path:
    """Move active project storage into archive/. Returns archive path."""
    src = _find_folder(projects_root(), project_id)
    if not src:
        # create empty archive stub so restore path is consistent
        dest = archive_root() / slugify(title, project_id)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "artifacts").mkdir(exist_ok=True)
    else:
        dest = archive_root() / src.name
        if dest.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            dest = archive_root() / f"{src.name}_{stamp}"
        shutil.move(str(src), str(dest))

    meta_path = dest / "archive_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "project_id": project_id,
                "title": title,
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "status": "archived",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    proj_meta = dest / "project.json"
    if proj_meta.exists():
        try:
            data = json.loads(proj_meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        data["status"] = "archived"
        data["archived_at"] = datetime.now(timezone.utc).isoformat()
        proj_meta.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return dest


def restore_project_folder(project_id: int) -> Path | None:
    """Move newest matching archive folder back to projects/."""
    candidates = sorted(
        [p for p in archive_root().iterdir() if p.is_dir() and p.name.startswith(f"{project_id}_")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    src = candidates[0]
    dest = projects_root() / re.sub(r"_\d{8}T\d{6}Z$", "", src.name)
    if dest.exists():
        dest = projects_root() / src.name
    shutil.move(str(src), str(dest))
    meta = dest / "project.json"
    if meta.exists():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        data["status"] = "active"
        data.pop("archived_at", None)
        meta.write_text(json.dumps(data, indent=2), encoding="utf-8")
    arch = dest / "archive_meta.json"
    if arch.exists():
        arch.unlink()
    return dest


def list_archived_folders() -> list[dict]:
    rows = []
    for path in sorted(archive_root().iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_dir():
            continue
        meta = {}
        for name in ("archive_meta.json", "project.json"):
            fp = path / name
            if fp.exists():
                try:
                    meta.update(json.loads(fp.read_text(encoding="utf-8")))
                except json.JSONDecodeError:
                    pass
        m = re.match(r"^(\d+)_", path.name)
        pid = int(m.group(1)) if m else meta.get("project_id")
        rows.append(
            {
                "folder": path.name,
                "project_id": pid,
                "title": meta.get("title") or path.name,
                "archived_at": meta.get("archived_at"),
                "path": str(path),
            }
        )
    return rows


def _find_folder(root: Path, project_id: int) -> Path | None:
    prefix = f"{project_id}_"
    matches = [p for p in root.iterdir() if p.is_dir() and p.name.startswith(prefix)]
    if not matches:
        # exact id folder fallback
        exact = root / str(project_id)
        if exact.is_dir():
            return exact
        return None
    return sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _maybe_migrate_legacy_artifacts(project_id: int, dest: Path) -> None:
    settings = get_settings()
    legacy = Path(settings.data_dir) / "artifacts" / str(project_id)
    if not legacy.is_dir():
        return
    for item in legacy.iterdir():
        target = dest / item.name
        if not target.exists():
            shutil.move(str(item), str(target))
    try:
        if not any(legacy.iterdir()):
            legacy.rmdir()
    except OSError:
        pass


def _ensure_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "projects").mkdir(exist_ok=True)
    (root / "archive").mkdir(exist_ok=True)
    (root / "tmp").mkdir(exist_ok=True)
    keep = root / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")
