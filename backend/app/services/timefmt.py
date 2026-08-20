"""UTC datetime helpers for API responses.

SQLite often returns naive datetimes even when we store UTC. Always emit ISO-8601
with an explicit UTC marker so browsers convert to the user's local timezone.
"""

from __future__ import annotations

from datetime import datetime, timezone


def to_iso_utc(dt: datetime | None) -> str | None:
    """Serialize datetime as UTC ISO string ending in Z."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume naive values from SQLite are UTC wall times.
        aware = dt.replace(tzinfo=timezone.utc)
    else:
        aware = dt.astimezone(timezone.utc)
    return aware.isoformat().replace("+00:00", "Z")
