"""Basic tests for marker helpers and persistence utilities."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import openai_responses_manifold as orm


class FakeChats:
    """Minimal in-memory stand-in for open_webui.models.chats.Chats."""

    def __init__(self) -> None:
        self.store: dict[str, SimpleNamespace] = {}

    def bootstrap(self, chat_id: str) -> None:
        self.store[chat_id] = SimpleNamespace(chat={"id": chat_id})

    def get_chat_by_id(self, chat_id: str) -> SimpleNamespace | None:
        return self.store.get(chat_id)

    def update_chat_by_id(self, chat_id: str, payload: dict[str, Any]) -> None:
        if chat_id not in self.store:
            self.store[chat_id] = SimpleNamespace(chat={})
        self.store[chat_id].chat = payload


@pytest.fixture()
def fake_chats(monkeypatch: pytest.MonkeyPatch) -> FakeChats:
    fake = FakeChats()
    monkeypatch.setattr(orm, "Chats", fake)
    return fake


def test_marker_roundtrip() -> None:
    """create_marker, wrap_marker, extract_markers, and split_text_by_markers align."""
    raw_marker = orm.create_marker(
        "function_call",
        ulid="A1B2C3D4E5F6G7H8",
        metadata={"tool": "search"},
    )
    wrapped = orm.wrap_marker(raw_marker)
    sample = f"before{wrapped}after"

    assert orm.contains_marker(sample)

    parsed = orm.extract_markers(sample, parsed=True)
    assert parsed[0]["metadata"]["tool"] == "search"

    segments = orm.split_text_by_markers(sample)
    assert segments[0]["type"] == "text" and segments[0]["text"].strip() == "before"
    assert segments[1]["type"] == "marker"


def test_persist_and_fetch(fake_chats: FakeChats) -> None:
    """Persisted response items can be retrieved by ULID and filtered by model."""
    fake_chats.bootstrap("chat-123")

    payloads = [
        {"type": "reasoning", "content": [{"type": "output_text", "text": "thinking"}]},
    ]
    marker_blob = orm.persist_openai_response_items(
        "chat-123",
        "msg-1",
        payloads,
        openwebui_model_id="openai_responses.gpt-4o",
    )

    assert orm.contains_marker(marker_blob)
    ulid = orm.extract_markers(marker_blob, parsed=True)[0]["ulid"]

    fetched = orm.fetch_openai_response_items(
        "chat-123",
        [ulid],
        openwebui_model_id="openai_responses.gpt-4o",
    )
    assert ulid in fetched
    assert fetched[ulid]["content"][0]["text"] == "thinking"

    filtered = orm.fetch_openai_response_items(
        "chat-123",
        [ulid],
        openwebui_model_id="different.model",
    )
    assert filtered == {}
