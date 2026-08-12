"""Local backup and restore for app data directory contents."""

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


def create_backup() -> dict:
    settings = get_settings()
    data_dir = settings.data_dir
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = backup_dir() / f"theresearcher-backup-{ts}.zip"
    from app.services.storage_paths import storage_root

    include = [
        data_dir / "theresearcher.db",
        data_dir / "artifacts",  # legacy
        data_dir / "refs",
        storage_root(),
    ]
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in include:
            if not item.exists():
                continue
            if item.is_file():
                zf.write(item, arcname=item.name)
            else:
                for path in item.rglob("*"):
                    if path.is_file():
                        zf.write(path, arcname=str(path.relative_to(data_dir)))
        meta = {
            "created_at": ts,
            "app": "TheResearcher",
            "note": "Local backup of DB, artifacts, refs. Tokens are encrypted in DB if present.",
        }
        zf.writestr("backup_meta.json", json.dumps(meta, indent=2))
    return {
        "filename": out.name,
        "path": str(out),
        "size_bytes": out.stat().st_size,
        "created_at": ts,
    }


def list_backups() -> list[dict]:
    rows = []
    for path in sorted(backup_dir().glob("theresearcher-backup-*.zip"), reverse=True):
        rows.append(
            {
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return rows


def restore_backup(filename: str) -> dict:
    settings = get_settings()
    src = backup_dir() / Path(filename).name
    if not src.exists() or not src.is_file():
        raise FileNotFoundError("Backup file not found")
    data_dir = settings.data_dir
    # safety copy current db
    db_path = data_dir / "theresearcher.db"
    if db_path.exists():
        shutil.copy2(db_path, data_dir / f"theresearcher.db.pre-restore-{src.stem}")
    with zipfile.ZipFile(src, "r") as zf:
        zf.extractall(data_dir)
    return {"ok": True, "restored_from": src.name, "message": "Backup restored into data directory. Restart recommended."}
