"""Local backup and restore for app data + storage directories."""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings


def backup_dir() -> Path:
    path = get_settings().data_dir / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _add_path(zf: zipfile.ZipFile, item: Path, arc_prefix: str) -> int:
    """Add a file or directory under arc_prefix. Returns number of files added."""
    if not item.exists():
        return 0
    count = 0
    if item.is_file():
        # Skip writing into the live backups folder content as nested zip spam
        if item.parent.resolve() == backup_dir().resolve() and item.suffix == ".zip":
            return 0
        zf.write(item, arcname=f"{arc_prefix}/{item.name}")
        return 1

    for path in item.rglob("*"):
        if not path.is_file():
            continue
        # Never nest other backup zips inside a new backup
        try:
            if backup_dir() in path.parents or path.parent.resolve() == backup_dir().resolve():
                if path.suffix == ".zip":
                    continue
        except OSError:
            pass
        rel = path.relative_to(item)
        zf.write(path, arcname=f"{arc_prefix}/{rel.as_posix()}")
        count += 1
    return count


def create_backup() -> dict:
    settings = get_settings()
    data_dir = Path(settings.data_dir)
    from app.services.storage_paths import storage_root

    store = storage_root()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = backup_dir() / f"theresearcher-backup-{ts}.zip"
    file_count = 0

    # data/ and storage/ live as sibling roots in Docker (/app/data, /app/storage).
    # Zip with explicit prefixes so restore can put each tree back correctly.
    data_items = [
        data_dir / "theresearcher.db",
        data_dir / "app_settings.json",
        data_dir / "templates.json",
        data_dir / "artifacts",  # legacy
        data_dir / "refs",
    ]

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in data_items:
            file_count += _add_path(zf, item, "data")
        file_count += _add_path(zf, store, "storage")
        meta = {
            "created_at": ts,
            "app": "TheResearcher",
            "layout": "data+storage",
            "file_count": file_count,
            "note": (
                "Local backup of DB, settings, templates, and storage. "
                "API tokens stay encrypted inside the DB if present."
            ),
        }
        zf.writestr("backup_meta.json", json.dumps(meta, indent=2))

    return {
        "filename": out.name,
        "path": str(out),
        "size_bytes": out.stat().st_size,
        "created_at": ts,
        "file_count": file_count,
    }


def list_backups() -> list[dict]:
    rows = []
    for path in sorted(backup_dir().glob("theresearcher-backup-*.zip"), reverse=True):
        rows.append(
            {
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    return rows


def restore_backup(filename: str) -> dict:
    settings = get_settings()
    src = backup_dir() / Path(filename).name
    if not src.exists() or not src.is_file():
        raise FileNotFoundError("Backup file not found")

    data_dir = Path(settings.data_dir)
    from app.services.storage_paths import storage_root

    store = storage_root()
    data_dir.mkdir(parents=True, exist_ok=True)
    store.mkdir(parents=True, exist_ok=True)

    # Safety copy of current DB before overwrite
    db_path = data_dir / "theresearcher.db"
    if db_path.exists():
        shutil.copy2(db_path, data_dir / f"theresearcher.db.pre-restore-{src.stem}")

    restored = 0
    with zipfile.ZipFile(src, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if not name or name.endswith("/"):
                continue
            if name == "backup_meta.json":
                continue
            # Path traversal guard
            parts = Path(name).parts
            if ".." in parts:
                continue

            if name.startswith("data/"):
                target = data_dir / name[len("data/") :]
            elif name.startswith("storage/"):
                target = store / name[len("storage/") :]
            else:
                # Legacy backups that dumped flat into data_dir
                target = data_dir / name

            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src_f, open(target, "wb") as dst_f:
                shutil.copyfileobj(src_f, dst_f)
            restored += 1

    return {
        "ok": True,
        "restored_from": src.name,
        "files_restored": restored,
        "message": "Backup restored into data/ and storage/. Restart recommended.",
    }
