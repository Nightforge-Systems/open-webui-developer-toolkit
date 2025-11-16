"""Utilities for consistent, masked logging payloads."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

_SENSITIVE_TOKENS = ("key", "token", "secret", "password", "authorization")


def mask_secret(value: str | None, *, placeholder: str = "[redacted]") -> str:
    """Return a short representation that hides the underlying secret."""

    if not value:
        return placeholder
    compact = value.strip()
    if len(compact) <= 6:
        return placeholder
    return f"{compact[:4]}…{compact[-2:]}"


def redact_dict(
    payload: dict[str, Any] | None,
    *,
    extra_secret_fields: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return a shallow copy with sensitive fields masked."""

    if not isinstance(payload, dict):
        return {}
    extra = {field.lower() for field in (extra_secret_fields or [])}
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        lower = str(key).lower()
        if any(token in lower for token in _SENSITIVE_TOKENS) or lower in extra:
            sanitized[key] = mask_secret(value if isinstance(value, str) else None)
            continue
        if isinstance(value, dict):
            sanitized[key] = redact_dict(value, extra_secret_fields=extra)
            continue
        sanitized[key] = value
    return sanitized


def compact_json(value: Any, *, limit: int = 400) -> str:
    """Return a JSON snippet trimmed to the desired length."""

    try:
        text = json.dumps(value, default=str, separators=(",", ":"))
    except TypeError:
        text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def summarize_request(payload: Any) -> dict[str, Any]:
    """Return high-level Responses request attributes safe for logging."""

    raw: dict[str, Any]
    if hasattr(payload, "model_dump"):
        raw = payload.model_dump(exclude_none=True)
    elif isinstance(payload, dict):
        raw = payload
    else:  # pragma: no cover - defensive fallback
        return {"type": str(type(payload))}
    blocks = raw.get("input") or []
    roles = [block.get("role") for block in blocks if isinstance(block, dict) and block.get("role")]
    reasoning = (raw.get("reasoning") or {}).get("effort")
    response_format = None
    if isinstance(raw.get("response_format"), dict):
        response_format = raw["response_format"].get("type")
    summary = {
        "model": raw.get("model"),
        "stream": raw.get("stream", False),
        "input_blocks": len(blocks),
        "input_roles": roles,
        "tool_count": len(raw.get("tools") or []),
        "store": raw.get("store"),
        "max_output_tokens": raw.get("max_output_tokens"),
        "reasoning_effort": reasoning,
        "response_format": response_format,
    }
    metadata = raw.get("metadata")
    if isinstance(metadata, dict):
        summary["metadata_fields"] = sorted(metadata.keys())
    return summary


def truncate_text(value: str | None, *, limit: int = 200) -> str | None:
    """Return a text snippet capped at the limit for logging."""

    if not value:
        return value
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}…"
