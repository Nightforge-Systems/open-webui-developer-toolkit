"""
title: Status Timeline Demo (No WebSearch)
author: ChatGPT
version: 0.1.0
"""

from typing import Optional, Callable, Awaitable, Union
from pydantic import BaseModel, Field
import asyncio

class Pipe:
    class Valves(BaseModel):
        STEP_DELAY_SECONDS: float = Field(
            default=0.4, description="Delay between status updates"
        )
        STEPS: int = Field(
            default=4, ge=1, le=10, description="How many demo steps to show"
        )
        SHOW_NOISE_STEP: bool = Field(
            default=False, description="Emit a hidden(=True) status (debug)"
        )

    def __init__(self):
        self.type = "pipe"
        self.id = "status_timeline_demo_no_websearch"
        self.name = "Status Timeline Demo (No WebSearch)"
        self.valves = self.Valves()

    async def _emit_status(self, emitter, description: str, *, done: bool = False, hidden: bool = False, action: str = "stage"):
        """Minimal status event payload (no web_search)."""
        if emitter:
            await emitter({
                "type": "status",
                "data": {
                    "action": action,        # any string; UI fallback renders description
                    "description": description,
                    "done": done,
                    "hidden": hidden
                }
            })

    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None,
        __event_call__: Optional[Callable[[dict], Awaitable[dict]]] = None,
    ) -> Union[str, dict]:

        # Optional hidden/noise status (won't render but proves we can send it)
        if self.valves.SHOW_NOISE_STEP:
            await self._emit_status(__event_emitter__, "Internal prep…", hidden=True)

        # Build a simple multi-step workflow (no 'web_search' anywhere)
        labels = [
            "Queued job",
            "Downloading inputs",
            "Analyzing data",
            "Summarizing results",
        ]

        # Allow user to shorten/extend the flow via STEPS valve
        if self.valves.STEPS < len(labels):
            labels = labels[: self.valves.STEPS]
        elif self.valves.STEPS > len(labels):
            # pad extras
            labels += [f"Extra step {i}" for i in range(len(labels)+1, self.valves.STEPS+1)]

        # Emit each step as its own status item
        for i, label in enumerate(labels):
            is_last = (i == len(labels) - 1)
            await self._emit_status(
                __event_emitter__,
                f"{label}",
                done=is_last  # last one marked done -> stops shimmer
            )
            await asyncio.sleep(self.valves.STEP_DELAY_SECONDS)

        # Return a normal assistant message
        return "✅ Finished. Expand the status indicator to view all previous steps (no web_search used)."
