"""Conversion helpers between Open WebUI payloads and the Responses API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from .markers import contains_marker, extract_markers, split_text
from .models import (
    Completed,
    CompletionsRequest,
    Error,
    OutputItem,
    ReasoningSummary,
    ResponsesRequest,
    RunEvent,
    TextDelta,
)
from .persistence import fetch_items

logger = logging.getLogger(__name__)


UNSUPPORTED_COMPLETIONS_FIELDS: set[str] = {
    "frequency_penalty",
    "presence_penalty",
    "seed",
    "logit_bias",
    "logprobs",
    "top_logprobs",
    "n",
    "stop",
    "response_format",
    "suffix",
    "stream_options",
    "audio",
    "function_call",
    "functions",
    "reasoning_effort",
    "max_tokens",
    "tools",
    "extra_tools",
}


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Context needed to build a Responses request."""

    chat_id: str | None
    model_id: str | None
    truncation: Literal["auto", "disabled"]
    user_identifier: str


def _collect_required_markers(messages: list[dict[str, Any]]) -> set[str]:
    required: set[str] = set()
    for message in messages:
        if message.get("role") != "assistant":
            continue
        content = message.get("content", "")
        if not contains_marker(content):
            continue
        for marker in extract_markers(content, parsed=True):
            required.add(marker["ulid"])
    return required


def _normalize_user_blocks(blocks: list[dict[str, Any]] | str | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    payload = blocks or []
    if isinstance(payload, str):
        payload = [{"type": "text", "text": payload}]
    for block in payload:
        if block.get("type") == "text":
            normalized.append({"type": "input_text", "text": block.get("text", "")})
            continue
        if block.get("type") == "image_url":
            normalized.append(
                {
                    "type": "input_image",
                    "image_url": block.get("image_url", {}).get("url"),
                }
            )
            continue
        if block.get("type") == "input_file":
            normalized.append({"type": "input_file", "file_id": block.get("file_id")})
            continue
        normalized.append(block)
    return normalized


def _assistant_entries(content: str, lookup: dict[str, Any]) -> list[dict[str, Any]]:
    if not content:
        return []
    if not contains_marker(content):
        return [
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": content}],
            }
        ]
    entries: list[dict[str, Any]] = []
    for segment in split_text(content):
        if segment["type"] == "marker":
            item_id = segment["marker"].split(":")[-1].split("?")[0]
            item = lookup.get(item_id)
            if item is not None:
                entries.append(item)
            continue
        text = segment.get("text", "").strip()
        if text:
            entries.append(
                {
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            )
    return entries


def _owui_messages_to_input(
    messages: list[dict[str, Any]],
    *,
    chat_id: str | None,
    model_id: str | None,
) -> list[dict[str, Any]]:
    """Convert Open WebUI messages into Responses API input blocks."""
    required = _collect_required_markers(messages)
    lookup = (
        fetch_items(chat_id=chat_id, item_ids=required, model_id=model_id)
        if chat_id and model_id and required
        else {}
    )
    openai_input: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role == "user":
            openai_input.append(
                {
                    "role": "user",
                    "content": _normalize_user_blocks(message.get("content")),
                }
            )
            continue
        if role == "developer":
            openai_input.append({"role": "developer", "content": message.get("content", "")})
            continue
        if role == "assistant":
            openai_input.extend(_assistant_entries(message.get("content", ""), lookup))
    return openai_input


def build_responses_request(
    completions: CompletionsRequest,
    *,
    chat_id: str | None = None,
    model_id: str | None = None,
    truncation: Literal["auto", "disabled"] = "auto",
    user_identifier: str | None = None,
    extra_params: dict[str, Any] | None = None,
    context: RequestContext | None = None,
) -> ResponsesRequest:
    """Translate a Completions payload into a Responses request."""
    if context is None:
        if user_identifier is None:
            raise ValueError("user_identifier is required when context is not provided")
        context = RequestContext(
            chat_id=chat_id,
            model_id=model_id,
            truncation=truncation,
            user_identifier=user_identifier,
        )
    params = extra_params or {}
    raw = completions.model_dump(exclude_none=True)
    sanitized: dict[str, Any] = {}
    for key, value in raw.items():
        if key in UNSUPPORTED_COMPLETIONS_FIELDS:
            logger.debug("Dropping unsupported completions field: %s", key)
            continue
        sanitized[key] = value
    if "max_tokens" in raw:
        sanitized["max_output_tokens"] = raw["max_tokens"]
    if "reasoning_effort" in raw:
        block = sanitized.get("reasoning", {})
        block.setdefault("effort", raw["reasoning_effort"])
        sanitized["reasoning"] = block
    instructions = next(
        (
            msg["content"]
            for msg in reversed(raw.get("messages", []))
            if msg.get("role") == "system"
        ),
        None,
    )
    if instructions:
        sanitized["instructions"] = instructions
    sanitized.pop("messages", None)
    sanitized["input"] = _owui_messages_to_input(
        raw.get("messages", []),
        chat_id=context.chat_id,
        model_id=context.model_id,
    )
    return ResponsesRequest(
        **sanitized,
        truncation=context.truncation,
        user=context.user_identifier,
        **params,
    )


def map_stream_frame(frame: dict[str, Any]) -> list[RunEvent]:
    """Convert a streaming chunk into synthetic run events."""
    etype = frame.get("type")
    events: list[RunEvent] = []
    if etype == "response.output_text.delta":
        delta = frame.get("delta", "")
        events = [TextDelta(delta)] if delta else []
    elif etype == "response.reasoning_summary_text.done":
        text = (frame.get("text") or "").strip()
        events = [ReasoningSummary(text)] if text else []
    elif etype in {"response.output_item.added", "response.output_item.done"}:
        events = [OutputItem(frame.get("item", {}), event_type=etype)]
    elif etype == "response.completed":
        payload = frame.get("response", {})
        events = [Completed(output=payload.get("output", []), usage=payload.get("usage"))]
    elif etype == "response.error":
        events = [Error(frame.get("error", {}).get("message", "Unknown error"))]
    elif etype == "response.output_text.annotation.added":
        annotation = frame.get("annotation") or {}
        events = [OutputItem({"type": "annotation", **annotation}, event_type=etype)]
    return events


def map_batch_payload(payload: dict[str, Any]) -> list[RunEvent]:
    """Convert a batch response payload into run events."""
    events: list[RunEvent] = []
    for item in payload.get("output", []):
        if item.get("type") == "message":
            events.extend(
                TextDelta(block.get("text", ""))
                for block in item.get("content", [])
                if block.get("type") == "output_text"
            )
        else:
            events.append(OutputItem(item, event_type="response.output_item.done"))
    events.append(Completed(output=payload.get("output", []), usage=payload.get("usage")))
    return events


__all__ = [
    "RequestContext",
    "build_responses_request",
    "map_batch_payload",
    "map_stream_frame",
]
