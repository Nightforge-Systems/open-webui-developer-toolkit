"""Lightweight helpers for emitting Open WebUI events."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

Emitter = Callable[[dict[str, Any]], Awaitable[None]]


async def emit_status(
    emit: Emitter | None,
    description: str,
    *,
    done: bool = False,
    extra: Mapping[str, object] | None = None,
) -> None:
    """Send a status update to the chat UI."""
    if emit is None:
        return
    payload = {"description": description, **(dict(extra) if extra else {})}
    if done:
        payload["done"] = True
    await emit({"type": "status", "data": payload})


async def emit_message(emit: Emitter | None, content: str) -> None:
    """Send the assistant transcript so far to the UI."""
    if emit is None:
        return
    await emit({"type": "chat:message", "data": {"content": content}})


async def emit_completion(
    emit: Emitter | None,
    *,
    content: str = "",
    usage: dict[str, Any] | None = None,
    error: str | None = None,
    done: bool = True,
) -> None:
    """Emit a completion payload, optionally including an error."""
    if emit is None:
        return
    data: dict[str, Any] = {"done": done, "content": content}
    if usage:
        data["usage"] = usage
    if error:
        data["error"] = {"message": error}
    await emit({"type": "chat:completion", "data": data})


async def emit_citation(emit: Emitter | None, document: str | list[str], source_name: str) -> None:
    """Display a citation or supporting document."""
    if emit is None:
        return
    docs = document if isinstance(document, list) else [document]
    await emit({"type": "citation", "data": {"source": {"name": source_name}, "document": docs}})


async def emit_notification(emit: Emitter | None, content: str, *, level: str = "info") -> None:
    """Emit a transient notification card."""
    if emit is None:
        return
    await emit({"type": "notification", "data": {"type": level, "content": content}})


async def emit_error(
    emit: Emitter | None,
    message: str,
    *,
    show_logs: bool = False,
    done: bool = False,
) -> None:
    """Emit an error event and optionally mirror details in a citation."""
    if emit is None:
        return
    await emit({"type": "chat:completion", "data": {"error": {"message": message}, "done": done}})
    if show_logs:
        await emit(
            {
                "type": "citation",
                "data": {"source": {"name": "Logs"}, "document": [message]},
            }
        )


def wrap_event_emitter(
    emitter: Emitter | None,
    *,
    suppress_chat_messages: bool = False,
    suppress_completion: bool = False,
) -> Emitter:
    """Wrap an emitter to suppress specific event types."""
    if emitter is None:

        async def _noop(_: dict[str, Any]) -> None:
            return

        return _noop

    async def _wrapped(event: dict[str, Any]) -> None:
        etype = event.get("type")
        if suppress_chat_messages and etype == "chat:message":
            return
        if suppress_completion and etype == "chat:completion":
            return
        await emitter(event)

    return _wrapped


__all__ = [
    "Emitter",
    "emit_citation",
    "emit_completion",
    "emit_error",
    "emit_message",
    "emit_notification",
    "emit_status",
    "wrap_event_emitter",
]
