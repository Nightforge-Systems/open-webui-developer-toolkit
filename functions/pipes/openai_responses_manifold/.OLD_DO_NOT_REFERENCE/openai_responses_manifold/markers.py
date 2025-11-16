"""Helpers for encoding and decoding tool output markers."""

from __future__ import annotations

import re
import secrets
from typing import Any

ULID_LENGTH = 16
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_SENTINEL = "[openai_responses:v2:"
_MARKER_RE = re.compile(
    rf"\[openai_responses:v2:(?P<kind>[a-z0-9_]{{2,30}}):(?P<ulid>[A-Z0-9]{{{ULID_LENGTH}}})(?:\?(?P<query>[^\]]+))?\]:\s*#",
    re.IGNORECASE,
)


def generate_ulid() -> str:
    """Return a pseudo-ULID compatible with Open WebUI markers."""
    return "".join(secrets.choice(ALPHABET) for _ in range(ULID_LENGTH))


def _encode_query(meta: dict[str, str]) -> str:
    return "&".join(f"{k}={v}" for k, v in meta.items()) if meta else ""


def _decode_query(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    parts = [segment.split("=", 1) for segment in value.split("&") if "=" in segment]
    return dict(parts)


def create_marker(
    kind: str,
    *,
    ulid: str | None = None,
    metadata: dict[str, str] | None = None,
) -> str:
    """Build a marker identifier encapsulating metadata."""
    if not re.fullmatch(r"[a-z0-9_]{2,30}", kind):
        message = "marker kind must match [a-z0-9_]{2,30}"
        raise ValueError(message)
    meta = {**(metadata or {})}
    base = f"openai_responses:v2:{kind}:{ulid or generate_ulid()}"
    encoded = _encode_query(meta)
    return f"{base}?{encoded}" if encoded else base


def wrap_marker(marker: str) -> str:
    """Wrap a marker in the sentinel format stored in transcripts."""
    return f"\n[{marker}]: #\n"


def contains_marker(text: str) -> bool:
    """Return True when the string contains a marker sentinel."""
    return _SENTINEL in text


def parse_marker(marker: str) -> dict[str, Any]:
    """Convert a serialized marker into its components."""
    if not marker.startswith("openai_responses:v2:"):
        message = "not an openai_responses marker"
        raise ValueError(message)
    _, _, kind, rest = marker.split(":", 3)
    ulid, _, query = rest.partition("?")
    return {
        "kind": kind,
        "ulid": ulid,
        "metadata": _decode_query(query or None),
    }


def extract_markers(text: str, *, parsed: bool = False) -> list[Any]:
    """Find markers in text, optionally parsing the metadata."""
    results: list[Any] = []
    for match in _MARKER_RE.finditer(text):
        marker = f"openai_responses:v2:{match.group('kind')}:{match.group('ulid')}"
        if match.group("query"):
            marker += f"?{match.group('query')}"
        results.append(parse_marker(marker) if parsed else marker)
    return results


def split_text(text: str) -> list[dict[str, str]]:
    """Split text into alternating segments of content and markers."""
    segments: list[dict[str, str]] = []
    last = 0
    for match in _MARKER_RE.finditer(text):
        if match.start() > last:
            segments.append({"type": "text", "text": text[last : match.start()]})
        marker = f"openai_responses:v2:{match.group('kind')}:{match.group('ulid')}"
        if match.group("query"):
            marker += f"?{match.group('query')}"
        segments.append({"type": "marker", "marker": marker})
        last = match.end()
    if last < len(text):
        segments.append({"type": "text", "text": text[last:]})
    return segments


__all__ = [
    "contains_marker",
    "create_marker",
    "extract_markers",
    "generate_ulid",
    "parse_marker",
    "split_text",
    "wrap_marker",
]
