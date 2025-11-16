"""Helpers for persisting tool results in the Open WebUI chat store."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

from open_webui.models.chats import Chats

from .markers import create_marker, split_text, wrap_marker

PIPE_KEY = "openai_responses_pipe"
logger = logging.getLogger(__name__)


def persist_items(
    *,
    chat_id: str | None,
    message_id: str | None,
    model_id: str | None,
    items: Iterable[dict[str, Any]],
) -> str:
    """Persist tool outputs and return rendered markers."""
    if not chat_id or not message_id or not model_id:
        logger.debug(
            "Skipping persistence due to incomplete metadata (chat_id=%s message_id=%s model_id=%s)",
            chat_id,
            message_id,
            model_id,
        )
        return ""
    materialized = list(items)
    if not materialized:
        logger.debug("No tool outputs to persist")
        return ""

    chat = Chats.get_chat_by_id(chat_id)
    if not chat:
        logger.warning("Chat %s not found; unable to persist tool outputs", chat_id)
        return ""

    bucket = chat.chat.setdefault(PIPE_KEY, {"__v": 3})
    store = bucket.setdefault("items", {})
    index = bucket.setdefault("messages_index", {})
    message_entry = index.setdefault(
        message_id,
        {"role": "assistant", "done": True, "item_ids": []},
    )

    now = int(datetime.datetime.now(datetime.UTC).timestamp())
    markers: list[str] = []
    for payload in materialized:
        marker = create_marker(payload.get("type", "unknown"))
        ulid = marker.split(":")[-1].split("?")[0]
        store[ulid] = {
            "model": model_id,
            "created_at": now,
            "payload": payload,
            "message_id": message_id,
        }
        message_entry["item_ids"].append(ulid)
        markers.append(wrap_marker(marker))

    Chats.update_chat_by_id(chat_id, chat.chat)
    logger.info(
        "Persisted %d item(s) for chat=%s message=%s",
        len(materialized),
        chat_id,
        message_id,
    )
    return "".join(markers)


def fetch_items(
    *,
    chat_id: str | None,
    item_ids: Iterable[str],
    model_id: str | None,
) -> dict[str, dict[str, Any]]:
    """Lookup stored tool outputs for reuse in follow-up requests."""
    if not chat_id:
        return {}
    chat = Chats.get_chat_by_id(chat_id)
    if not chat:
        logger.warning("Chat %s not found while fetching stored tool outputs", chat_id)
        return {}
    store = chat.chat.get(PIPE_KEY, {}).get("items", {})
    result: dict[str, dict[str, Any]] = {}
    for item_id in item_ids:
        record = store.get(item_id)
        if not record:
            continue
        if model_id and record.get("model") != model_id:
            logger.debug(
                "Skipping stored item %s due to model mismatch (%s != %s)",
                item_id,
                record.get("model"),
                model_id,
            )
            continue
        result[item_id] = record.get("payload", {})
    return result


def split_assistant_segments(text: str) -> list[dict[str, str]]:
    """Return structured segments for assistant text."""
    return split_text(text)


__all__ = ["fetch_items", "persist_items", "split_assistant_segments"]
