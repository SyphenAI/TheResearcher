"""Multi-provider LLM client (OpenAI, Anthropic, xAI/Grok, Google)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models import ApiToken
from app.security import decrypt_secret

PROVIDER_DEFAULTS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "chat_path": "/chat/completions",
        "default_model": "gpt-4o-mini",
        "model_fallbacks": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"],
        "style": "openai",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "chat_path": "/messages",
        # Prefer current Sonnet/Haiku IDs; runtime can also discover via /v1/models.
        "default_model": "claude-sonnet-4-5-20250929",
        "model_fallbacks": [
            "claude-sonnet-4-5-20250929",
            "claude-sonnet-4-6",
            "claude-sonnet-5",
            "claude-haiku-4-5-20251001",
            "claude-opus-4-5-20251101",
            "claude-opus-4-6",
            "claude-opus-5",
        ],
        "style": "anthropic",
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "chat_path": "/chat/completions",
        "default_model": "grok-2-latest",
        "model_fallbacks": ["grok-2-latest", "grok-3-mini", "grok-3"],
        "style": "openai",
    },
    "google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "chat_path": "/models/{model}:generateContent",
        "default_model": "gemini-2.0-flash",
        "model_fallbacks": ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        "style": "google",
    },
    "azure_openai": {
        "base_url": "",
        "chat_path": "/chat/completions",
        "default_model": "gpt-4o-mini",
        "model_fallbacks": ["gpt-4o-mini"],
        "style": "openai",
    },
}


def _discover_anthropic_models(api_key: str, base_url: str) -> list[str]:
    try:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(f"{base_url.rstrip('/')}/models", headers=headers)
            if resp.status_code >= 400:
                return []
            data = resp.json()
        ids = [str(m.get("id") or "").strip() for m in (data.get("data") or [])]
        # Prefer sonnet/haiku for general research; keep opus available as later fallback.
        preferred = [i for i in ids if "sonnet" in i.lower()]
        secondary = [i for i in ids if "haiku" in i.lower()]
        rest = [i for i in ids if i and i not in preferred and i not in secondary]
        return preferred + secondary + rest
    except Exception:  # noqa: BLE001
        return []


def _model_candidates(
    meta: dict[str, Any],
    preferred: str | None = None,
    *,
    api_key: str | None = None,
    provider: str | None = None,
) -> list[str]:
    models: list[str] = []
    if preferred:
        models.append(preferred)
    models.append(meta.get("default_model") or "")
    models.extend(meta.get("model_fallbacks") or [])
    if provider == "anthropic" and api_key:
        models.extend(_discover_anthropic_models(api_key, meta.get("base_url", "")))
    out: list[str] = []
    seen: set[str] = set()
    for model in models:
        name = (model or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _is_model_not_found_error(err: str) -> bool:
    text = (err or "").lower()
    return (
        "model:" in text
        or "not_found_error" in text
        or "does not exist" in text
        or "model_not_found" in text
        or ("404" in text and "model" in text)
    )


@dataclass
class LLMResult:
    content: str
    provider: str
    model: str
    used_live: bool
    error: str | None = None


def list_active_providers(
    db: Session,
    *,
    purpose: str = "research",
) -> list[dict[str, Any]]:
    """purpose: research | judge | any"""
    q = db.query(ApiToken).filter(ApiToken.is_active.is_(True))
    purpose = (purpose or "research").lower()
    if purpose == "research":
        q = q.filter(ApiToken.use_for_research.is_(True))
    elif purpose == "judge":
        q = q.filter(ApiToken.use_for_judge.is_(True))
    rows = q.order_by(ApiToken.provider.asc(), ApiToken.label.asc()).all()
    out = []
    for row in rows:
        meta = PROVIDER_DEFAULTS.get(row.provider, {})
        preferred = (getattr(row, "model", "") or "").strip()
        out.append(
            {
                "id": row.id,
                "provider": row.provider,
                "label": row.label,
                "model": preferred,
                "default_model": preferred or meta.get("default_model", "default"),
                "style": meta.get("style", "openai"),
                "use_for_research": bool(getattr(row, "use_for_research", True)),
                "use_for_judge": bool(getattr(row, "use_for_judge", True)),
            }
        )
    return out


def get_provider_token(
    db: Session,
    provider: str,
    label: str = "default",
    *,
    purpose: str = "any",
) -> ApiToken | None:
    provider = provider.strip().lower()
    purpose = (purpose or "any").lower()

    def _purpose_ok(row: ApiToken) -> bool:
        if not row.is_active:
            return False
        if purpose == "research":
            return bool(getattr(row, "use_for_research", True))
        if purpose == "judge":
            return bool(getattr(row, "use_for_judge", True))
        return True

    row = (
        db.query(ApiToken)
        .filter(
            ApiToken.provider == provider,
            ApiToken.label == label,
            ApiToken.is_active.is_(True),
        )
        .first()
    )
    if row and _purpose_ok(row):
        return row
    # fall back to any active label for provider matching purpose
    candidates = (
        db.query(ApiToken)
        .filter(ApiToken.provider == provider, ApiToken.is_active.is_(True))
        .order_by(ApiToken.id.asc())
        .all()
    )
    for candidate in candidates:
        if _purpose_ok(candidate):
            return candidate
    return None


def test_token_connection(db: Session, token_row: ApiToken) -> dict[str, Any]:
    """Minimal live call to verify a stored token can authenticate and respond."""
    provider = (token_row.provider or "").strip().lower()
    meta = PROVIDER_DEFAULTS.get(provider)
    if not meta:
        return {
            "ok": False,
            "provider": provider,
            "label": token_row.label,
            "model": "",
            "message": f"Unknown provider '{provider}'.",
            "latency_ms": None,
        }

    try:
        api_key = decrypt_secret(token_row.encrypted_value)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "provider": provider,
            "label": token_row.label,
            "model": meta.get("default_model", ""),
            "message": f"Could not decrypt token: {exc}",
            "latency_ms": None,
        }

    style = meta["style"]
    preferred = (getattr(token_row, "model", "") or "").strip() or None
    candidates = _model_candidates(
        meta, preferred, api_key=api_key, provider=provider
    )
    started = datetime.now(timezone.utc)
    last_err = ""
    last_model = candidates[0] if candidates else meta.get("default_model", "")

    for model in candidates:
        last_model = model
        try:
            if style == "anthropic":
                content = _anthropic_chat(
                    api_key,
                    meta,
                    model,
                    [{"role": "user", "content": "Reply with exactly: pong"}],
                    system="You are a connectivity probe. Reply with only the word pong.",
                    max_tokens=16,
                    temperature=0,
                )
            elif style == "google":
                content = _google_chat(
                    api_key,
                    meta,
                    model,
                    [{"role": "user", "content": "Reply with exactly: pong"}],
                    system="You are a connectivity probe. Reply with only the word pong.",
                    max_tokens=16,
                    temperature=0,
                )
            else:
                content = _openai_style_chat(
                    api_key,
                    meta,
                    model,
                    [{"role": "user", "content": "Reply with exactly: pong"}],
                    system="You are a connectivity probe. Reply with only the word pong.",
                    max_tokens=16,
                    temperature=0,
                    provider=provider,
                )
            elapsed = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            token_row.last_used_at = datetime.now(timezone.utc)
            db.commit()
            preview = (content or "").strip().replace("\n", " ")[:80]
            return {
                "ok": True,
                "provider": provider,
                "label": token_row.label,
                "model": model,
                "message": f"Connected via {model}. Model responded ({preview or 'empty body'}).",
                "latency_ms": elapsed,
                "active": bool(token_row.is_active),
                "use_for_research": bool(getattr(token_row, "use_for_research", True)),
                "use_for_judge": bool(getattr(token_row, "use_for_judge", True)),
            }
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            if _is_model_not_found_error(last_err):
                continue
            break

    elapsed = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    err = last_err
    if len(err) > 320:
        err = err[:319] + "…"
    return {
        "ok": False,
        "provider": provider,
        "label": token_row.label,
        "model": last_model,
        "message": err or "Connectivity test failed.",
        "latency_ms": elapsed,
        "active": bool(token_row.is_active),
        "use_for_research": bool(getattr(token_row, "use_for_research", True)),
        "use_for_judge": bool(getattr(token_row, "use_for_judge", True)),
    }


def chat(
    db: Session,
    *,
    provider: str,
    messages: list[dict[str, str]],
    model: str | None = None,
    label: str = "default",
    temperature: float = 0.4,
    max_tokens: int = 2200,
    system: str | None = None,
) -> LLMResult:
    provider = provider.strip().lower()
    meta = PROVIDER_DEFAULTS.get(provider)
    if not meta:
        return LLMResult("", provider, model or "", False, f"Unknown provider: {provider}")

    token_row = get_provider_token(db, provider, label, purpose="any")
    if not token_row or not token_row.is_active:
        return LLMResult(
            "",
            provider,
            model or meta["default_model"],
            False,
            f"No active token for {provider}. Add one in Security.",
        )

    api_key = decrypt_secret(token_row.encrypted_value)
    style = meta["style"]
    preferred = model or (getattr(token_row, "model", "") or "").strip() or None
    last_err = ""
    for use_model in _model_candidates(
        meta, preferred, api_key=api_key, provider=provider
    ):
        try:
            if style == "anthropic":
                content = _anthropic_chat(
                    api_key, meta, use_model, messages, system, max_tokens, temperature
                )
            elif style == "google":
                content = _google_chat(
                    api_key, meta, use_model, messages, system, max_tokens, temperature
                )
            else:
                content = _openai_style_chat(
                    api_key, meta, use_model, messages, system, max_tokens, temperature, provider
                )
            token_row.last_used_at = datetime.now(timezone.utc)
            db.commit()
            return LLMResult(
                content=content.strip(),
                provider=provider,
                model=use_model,
                used_live=True,
            )
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            if _is_model_not_found_error(last_err):
                continue
            return LLMResult(
                content="",
                provider=provider,
                model=use_model,
                used_live=False,
                error=last_err,
            )
    return LLMResult(
        content="",
        provider=provider,
        model=model or meta["default_model"],
        used_live=False,
        error=last_err or f"No working model for {provider}",
    )


def _openai_style_chat(
    api_key: str,
    meta: dict[str, Any],
    model: str,
    messages: list[dict[str, str]],
    system: str | None,
    max_tokens: int,
    temperature: float,
    provider: str,
) -> str:
    base = meta["base_url"].rstrip("/")
    if not base:
        raise ValueError(f"{provider} base URL is not configured")
    payload_messages = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": payload_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    with httpx.Client(timeout=90.0) as client:
        resp = client.post(f"{base}{meta['chat_path']}", headers=headers, json=body)
        if resp.status_code >= 400:
            raise RuntimeError(f"{provider} API {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
    return data["choices"][0]["message"]["content"]


def _anthropic_chat(
    api_key: str,
    meta: dict[str, Any],
    model: str,
    messages: list[dict[str, str]],
    system: str | None,
    max_tokens: int,
    temperature: float,
) -> str:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"],
    }
    if system:
        body["system"] = system
    with httpx.Client(timeout=90.0) as client:
        resp = client.post(
            f"{meta['base_url'].rstrip('/')}{meta['chat_path']}",
            headers=headers,
            json=body,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"anthropic API {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
    parts = data.get("content") or []
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def _google_chat(
    api_key: str,
    meta: dict[str, Any],
    model: str,
    messages: list[dict[str, str]],
    system: str | None,
    max_tokens: int,
    temperature: float,
) -> str:
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    path = meta["chat_path"].format(model=model)
    url = f"{meta['base_url'].rstrip('/')}{path}?key={api_key}"
    with httpx.Client(timeout=90.0) as client:
        resp = client.post(url, json=body)
        if resp.status_code >= 400:
            raise RuntimeError(f"google API {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
    cands = data.get("candidates") or []
    if not cands:
        return ""
    parts = cands[0].get("content", {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts)
