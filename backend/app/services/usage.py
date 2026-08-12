"""LLM usage logging and rough USD cost estimates (not billing truth)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import LlmUsageEvent

# Rough list prices USD per 1M tokens (input, output). Update as markets move.
# Prefer family matches over exact IDs.
_RATE_TABLE: list[tuple[str, float, float]] = [
    ("claude-opus", 15.0, 75.0),
    ("claude-sonnet", 3.0, 15.0),
    ("claude-haiku", 0.80, 4.0),
    ("gpt-5", 1.25, 10.0),
    ("gpt-4.1", 2.0, 8.0),
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4o", 2.50, 10.0),
    ("o3", 2.0, 8.0),
    ("o1", 15.0, 60.0),
    ("grok-3-mini", 0.30, 0.50),
    ("grok-3", 3.0, 15.0),
    ("grok-2", 2.0, 10.0),
    ("gemini-2.0-flash", 0.10, 0.40),
    ("gemini-1.5-flash", 0.075, 0.30),
    ("gemini-1.5-pro", 1.25, 5.0),
    ("default", 1.0, 3.0),
]


def estimate_tokens_from_text(text: str) -> int:
    """Rough token estimate when provider usage is missing (~4 chars/token)."""
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def rates_for_model(model: str) -> tuple[float, float]:
    m = (model or "").lower()
    for key, inp, out in _RATE_TABLE:
        if key == "default":
            continue
        if key in m:
            return inp, out
    return _RATE_TABLE[-1][1], _RATE_TABLE[-1][2]


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    inp_rate, out_rate = rates_for_model(model)
    cost = (max(0, input_tokens) / 1_000_000.0) * inp_rate + (
        max(0, output_tokens) / 1_000_000.0
    ) * out_rate
    return round(cost, 6)


def log_usage(
    db: Session,
    *,
    provider: str,
    model: str,
    purpose: str = "chat",
    label: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    ok: bool = True,
    error: str = "",
    project_id: int | None = None,
    created_by: str = "",
    estimated_cost_usd: float | None = None,
) -> LlmUsageEvent:
    cost = (
        estimated_cost_usd
        if estimated_cost_usd is not None
        else estimate_cost_usd(model, input_tokens, output_tokens)
    )
    row = LlmUsageEvent(
        provider=(provider or "")[:64],
        model=(model or "")[:128],
        purpose=(purpose or "chat")[:64],
        label=(label or "")[:128],
        input_tokens=int(input_tokens or 0),
        output_tokens=int(output_tokens or 0),
        estimated_cost_usd=float(cost or 0.0),
        latency_ms=int(latency_ms or 0),
        ok=bool(ok),
        error=(error or "")[:512],
        project_id=project_id,
        created_by=(created_by or "")[:64],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def usage_summary(db: Session, *, days: int = 30, limit: int = 50) -> dict[str, Any]:
    days = max(1, min(int(days or 30), 365))
    limit = max(1, min(int(limit or 50), 200))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    q = db.query(LlmUsageEvent).filter(LlmUsageEvent.created_at >= since)
    total_calls = q.count()
    totals = (
        db.query(
            func.coalesce(func.sum(LlmUsageEvent.input_tokens), 0),
            func.coalesce(func.sum(LlmUsageEvent.output_tokens), 0),
            func.coalesce(func.sum(LlmUsageEvent.estimated_cost_usd), 0.0),
        )
        .filter(LlmUsageEvent.created_at >= since)
        .one()
    )
    cost_24h = (
        db.query(func.coalesce(func.sum(LlmUsageEvent.estimated_cost_usd), 0.0))
        .filter(LlmUsageEvent.created_at >= since_24h)
        .scalar()
    )
    cost_24h = round(float(cost_24h or 0.0), 4)
    try:
        from app.services.app_settings import load_app_settings

        threshold = float(load_app_settings().get("daily_cost_alert_usd") or 0.0)
    except Exception:  # noqa: BLE001
        threshold = 2.0
    cost_alert = bool(threshold > 0 and cost_24h >= threshold)
    by_provider_rows = (
        db.query(
            LlmUsageEvent.provider,
            func.count(LlmUsageEvent.id),
            func.coalesce(func.sum(LlmUsageEvent.input_tokens), 0),
            func.coalesce(func.sum(LlmUsageEvent.output_tokens), 0),
            func.coalesce(func.sum(LlmUsageEvent.estimated_cost_usd), 0.0),
        )
        .filter(LlmUsageEvent.created_at >= since)
        .group_by(LlmUsageEvent.provider)
        .order_by(func.sum(LlmUsageEvent.estimated_cost_usd).desc())
        .all()
    )
    by_model_rows = (
        db.query(
            LlmUsageEvent.provider,
            LlmUsageEvent.model,
            func.count(LlmUsageEvent.id),
            func.coalesce(func.sum(LlmUsageEvent.input_tokens), 0),
            func.coalesce(func.sum(LlmUsageEvent.output_tokens), 0),
            func.coalesce(func.sum(LlmUsageEvent.estimated_cost_usd), 0.0),
        )
        .filter(LlmUsageEvent.created_at >= since)
        .group_by(LlmUsageEvent.provider, LlmUsageEvent.model)
        .order_by(func.sum(LlmUsageEvent.estimated_cost_usd).desc())
        .limit(20)
        .all()
    )
    recent = (
        db.query(LlmUsageEvent)
        .order_by(LlmUsageEvent.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "days": days,
        "total_calls": int(total_calls),
        "input_tokens": int(totals[0] or 0),
        "output_tokens": int(totals[1] or 0),
        "estimated_cost_usd": round(float(totals[2] or 0.0), 4),
        "estimated_cost_usd_24h": cost_24h,
        "daily_cost_alert_usd": threshold,
        "cost_alert": cost_alert,
        "cost_alert_message": (
            f"Estimated spend in last 24h is ${cost_24h:.4f}, at or above your ${threshold:.2f} alert."
            if cost_alert
            else ""
        ),
        "note": (
            "Costs are rough estimates from public list prices, not invoices. "
            "Missing usage fields are estimated from text length."
        ),
        "by_provider": [
            {
                "provider": r[0] or "unknown",
                "calls": int(r[1] or 0),
                "input_tokens": int(r[2] or 0),
                "output_tokens": int(r[3] or 0),
                "estimated_cost_usd": round(float(r[4] or 0.0), 4),
            }
            for r in by_provider_rows
        ],
        "by_model": [
            {
                "provider": r[0] or "unknown",
                "model": r[1] or "unknown",
                "calls": int(r[2] or 0),
                "input_tokens": int(r[3] or 0),
                "output_tokens": int(r[4] or 0),
                "estimated_cost_usd": round(float(r[5] or 0.0), 4),
            }
            for r in by_model_rows
        ],
        "recent": [
            {
                "id": e.id,
                "provider": e.provider,
                "model": e.model,
                "purpose": e.purpose,
                "input_tokens": e.input_tokens,
                "output_tokens": e.output_tokens,
                "estimated_cost_usd": e.estimated_cost_usd,
                "latency_ms": e.latency_ms,
                "ok": e.ok,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in recent
        ],
    }
