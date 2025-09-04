"""
title: OpenAI Prompt Object Filter
id: openai_prompt_object_filter
author: OpenAI Codex
description: Strip system messages when a Prompt Object is provided.
version: 0.1.0
license: MIT
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict
from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=0, description="Priority level for the filter operations."
        )

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def inlet(
        self,
        body: Dict[str, Any],
        __event_emitter__: Callable[[Dict[str, Any]], Awaitable[None]] | None = None,
        __metadata__: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Remove system messages when a prompt object is present."""

        prompt = body.get("prompt")
        if isinstance(prompt, dict) and prompt.get("id"):
            messages = body.get("messages")
            if isinstance(messages, list):
                body["messages"] = [
                    m for m in messages if m.get("role") != "system"
                ]
        return body
