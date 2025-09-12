"""Status Emitter Demo.

title: Status Emitter Demo
id: status_emitter_example
author: OpenAI Codex
description: Demonstrates emitting diverse status actions with delays.
version: 1.0.0
license: MIT
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Awaitable, Callable


class Pipe:
    """Simple pipe that emits a variety of status events."""

    async def pipe(
        self,
        _body: dict[str, Any],
        __event_emitter__: Callable[[dict[str, Any]], Awaitable[None]] | None,
        __metadata__: dict[str, Any] | None = None,
        *_,
    ) -> AsyncGenerator[str, None]:
        """Emit example status events, pausing two seconds between each."""

        if not __event_emitter__:
            yield "No event emitter provided."
            return

        statuses = [
            {"description": "Starting demo", "done": False},
            {
                "action": "web_search",
                "description": "Searched {{count}} sites",
                "query": "open webui",
                "items": [
                    {"title": "Open WebUI", "link": "https://github.com/open-webui/open-webui"},
                    {"title": "Open WebUI Docs", "link": "https://docs.openwebui.com"},
                ],
                "done": True,
            },
            {
                "action": "web_search",
                "description": "Searched {{count}} sites",
                "query": "open webui",
                "urls": [
                    "https://github.com/open-webui/open-webui",
                    "https://docs.openwebui.com",
                ],
                "done": True,
            },
            {
                "action": "knowledge_search",
                "query": "vector database",
                "done": False,
            },
            {
                "action": "web_search_queries_generated",
                "queries": ["Open WebUI", "status events"],
                "done": False,
            },
            {
                "action": "queries_generated",
                "queries": ["vector search", "semantic ranking"],
                "done": False,
            },
            {
                "action": "sources_retrieved",
                "count": 2,
                "done": True,
            },
            {"description": "Hidden completion", "done": True, "hidden": True},
            {"description": "Search failed", "done": True, "error": True},
        ]

        for data in statuses:
            await __event_emitter__({"type": "status", "data": data})
            await asyncio.sleep(2)

        yield "Status emitter demo complete."
