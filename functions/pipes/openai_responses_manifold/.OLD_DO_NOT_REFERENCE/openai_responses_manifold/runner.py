"""Orchestrator that streams or batches Responses API calls."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from random import SystemRandom
from time import perf_counter
from typing import TYPE_CHECKING, Any, cast

from .adapters import map_batch_payload, map_stream_frame
from .emitters import (
    Emitter,
    emit_citation,
    emit_completion,
    emit_error,
    emit_message,
    emit_status,
)
from .models import (
    Completed,
    Error,
    OutputItem,
    ReasoningSummary,
    ResponsesRequest,
    RunEvent,
    TextDelta,
    Usage,
)
from .persistence import persist_items
from .session import SessionLogger
from .tools import run_function_calls

if TYPE_CHECKING:
    from logging import Logger

    from .client import ResponsesClient
    from .valves import Valves

_STATUS_SEQUENCE = [
    (0.0, "Thinking…"),
    (1.5, "Reading the user's question…"),
    (4.0, "Gathering my thoughts…"),
    (6.0, "Exploring possible responses…"),
    (7.0, "Building a plan…"),
]
_JITTER = SystemRandom()


@dataclass(slots=True)
class RunnerDeps:
    """Container for runner dependencies."""

    valves: Valves
    client: ResponsesClient
    emitter: Emitter
    metadata: dict[str, Any]
    tools: dict[str, dict[str, Any]] | None
    features: dict[str, Any]
    logger: Logger
    is_task_request: bool = False


class ResponseRunner:
    """Execute Responses API calls and emit intermediate events."""

    def __init__(
        self,
        *,
        request: ResponsesRequest,
        deps: RunnerDeps,
    ) -> None:
        """Store dependencies shared across streaming and batch modes."""
        self.request = request
        self.valves = deps.valves
        self.client = deps.client
        self.emit = deps.emitter
        self.metadata = deps.metadata
        self.tools = deps.tools or {}
        self.features = deps.features
        self.logger = deps.logger
        self.assistant = ""
        self.total_usage: dict[str, Any] = {}
        self._thinking_tasks: list[asyncio.Task] = []
        self._last_completed: Completed | None = None
        self.is_task_request = deps.is_task_request
        self.persist_tool_results = self.valves.PERSIST_TOOL_RESULTS and not self.is_task_request

    def _input_as_list(self) -> list[dict[str, Any]]:
        """Ensure the request input field is a mutable list."""
        if isinstance(self.request.input, list):
            return self.request.input
        block = {"type": "input_text", "text": self.request.input}
        self.request.input = [block]
        return cast(list[dict[str, Any]], self.request.input)

    @property
    def chat_id(self) -> str | None:
        """Return the active chat identifier, if any."""
        return self.metadata.get("chat_id")

    @property
    def message_id(self) -> str | None:
        """Return the assistant message identifier, if any."""
        return self.metadata.get("message_id")

    @property
    def model_id(self) -> str | None:
        """Return the Open WebUI model identifier, if any."""
        return self.metadata.get("model", {}).get("id")

    async def run(self) -> str:
        """Execute the Responses request in batch or streaming mode."""
        self.logger.info(
            "Starting Responses run (model=%s, stream=%s)",
            self.request.model,
            self.request.stream,
        )
        self.logger.debug(
            "Runner context chat_id=%s message_id=%s features=%s",
            self.chat_id,
            self.message_id,
            self.features,
        )
        if self.request.stream:
            return await self._run_streaming()
        return await self._run_batch()

    async def _run_streaming(self) -> str:
        self._schedule_thinking_updates()
        timer = perf_counter()
        try:
            for loop_index in range(self.valves.MAX_FUNCTION_CALL_LOOPS):
                self.logger.debug("Stream loop iteration %d", loop_index + 1)
                completed = await self._consume_stream()
                if completed is None:
                    message = "Responses API returned no completion event"
                    self.logger.error(message)
                    await emit_error(self.emit, message, show_logs=True, done=True)
                    break
                await self._handle_usage(completed)
                calls = [item for item in completed.output if item.get("type") == "function_call"]
                if not calls:
                    break
                self.logger.info("Executing %d function call(s)", len(calls))
                for call in calls:
                    self.logger.debug(
                        "Tool request name=%s call_id=%s", call.get("name"), call.get("call_id")
                    )
                outputs = await run_function_calls(calls, self.tools)
                self.logger.info("Function calls completed (%d outputs)", len(outputs))
                markers = ""
                if self.persist_tool_results:
                    markers = persist_items(
                        chat_id=self.chat_id,
                        message_id=self.message_id,
                        model_id=self.model_id,
                        items=outputs,
                    )
                if markers:
                    self.assistant += markers
                    await emit_message(self.emit, self.assistant)
                    self.logger.info("Persisted tool outputs for message %s", self.message_id)
                for output in outputs:
                    pretty = json.dumps(output.get("output"), default=str)
                    await emit_status(self.emit, f"Received tool result\n```\n{pretty}\n```")
                self._input_as_list().extend(outputs)
        finally:
            await self._cancel_thinking()
            elapsed = perf_counter() - timer
            self.logger.info("Streaming run completed in %.1fs", elapsed)
            if not self.is_task_request:
                await emit_status(self.emit, f"Thought for {elapsed:.1f} seconds", done=True)
                await emit_completion(self.emit, usage=self.total_usage, done=True)
            await self._flush_logs()
        return self.assistant

    async def _consume_stream(self) -> Completed | None:
        iterator = self.client.stream(self.request)
        if inspect.isawaitable(iterator):
            iterator = await iterator
        async for chunk in cast(AsyncIterator[dict[str, Any]], iterator):
            for event in map_stream_frame(chunk):
                terminate = await self._dispatch(event)
                if terminate:
                    return self._last_completed
        return self._last_completed

    async def _run_batch(self) -> str:
        timer = perf_counter()
        try:
            payload = await self.client.invoke(self.request)
            for event in map_batch_payload(payload):
                await self._dispatch(event)
            elapsed = perf_counter() - timer
            self.logger.info("Batch run completed in %.1fs", elapsed)
            if not self.is_task_request:
                await emit_completion(
                    self.emit,
                    content=self.assistant,
                    usage=self.total_usage,
                    done=True,
                )
            return self.assistant
        finally:
            await self._flush_logs()

    async def _dispatch(self, event: RunEvent) -> bool:
        if isinstance(event, TextDelta):
            self.assistant += event.text
            await emit_message(self.emit, self.assistant)
            return False
        if isinstance(event, ReasoningSummary):
            text = re.sub(r"\*\*(.+?)\*\*", "", event.text).strip()
            await emit_status(self.emit, text or "Thinking…")
            await self._cancel_thinking()
            self.logger.debug("Reasoning summary received: %s", text)
            return False
        if isinstance(event, OutputItem):
            await self._handle_output_item(event)
            return False
        if isinstance(event, Completed):
            self._last_completed = event
            self._input_as_list().extend(event.output)
            self.logger.info("Completion event received (%d output block(s))", len(event.output))
            return True
        if isinstance(event, Error):
            self.logger.error("Responses API error: %s", event.message)
            await emit_error(self.emit, event.message, show_logs=True)
            return True
        if isinstance(event, Usage):
            self.total_usage.update(event.stats)
            self.logger.debug("Usage update: %s", event.stats)
        return False

    async def _handle_output_item(self, event: OutputItem) -> None:
        item = event.item
        if self.is_task_request:
            return
        if event.event_type == "response.output_item.added":
            if item.get("type") == "message" and item.get("status") == "in_progress":
                await emit_status(self.emit, "Responding…")
            return
        if event.event_type != "response.output_item.done":
            return
        self.logger.debug("Output item done: %s", item.get("type"))
        if item.get("type") == "annotation":
            await self._handle_annotation(item)
            return
        if item.get("type") == "web_search_call":
            await self._handle_web_search(item)
            return
        if (
            item.get("type") == "reasoning"
            and self.valves.PERSIST_REASONING_TOKENS != "conversation"
        ):
            return
        if not self.persist_tool_results:
            return
        markers = persist_items(
            chat_id=self.chat_id,
            message_id=self.message_id,
            model_id=self.model_id,
            items=[item],
        )
        if markers:
            self.assistant += markers
            await emit_message(self.emit, self.assistant)
            self.logger.info("Persisted response output item (%s)", item.get("type"))

    async def _handle_web_search(self, item: dict[str, Any]) -> None:
        action = item.get("action", {}) or {}
        if action.get("type") != "search":
            return
        query = action.get("query")
        sources = [entry.get("url") for entry in action.get("sources", []) if entry.get("url")]
        self.logger.info(
            "Web search call processed (query=%s sources=%d)",
            query,
            len(sources),
        )
        if query:
            await emit_status(
                self.emit,
                "Searching",
                extra={"action": "web_search_queries_generated", "queries": [query]},
                done=False,
            )
        if sources:
            await emit_status(
                self.emit,
                "Sources retrieved",
                extra={"action": "sources_retrieved", "urls": sources},
                done=False,
            )
            await emit_status(
                self.emit,
                "Reading through {count} sites",
                extra={"action": "web_search", "query": query, "urls": sources},
                done=False,
            )

    async def _handle_annotation(self, annotation: dict[str, Any]) -> None:
        if annotation.get("type") != "url_citation":
            return
        url = (annotation.get("url") or "").strip()
        title = (annotation.get("title") or url).strip()
        self.logger.debug("Annotation cited: %s", url)
        await emit_citation(self.emit, f"{title}\n{url}", "web_search")

    async def _handle_usage(self, completed: Completed) -> None:
        usage = completed.usage or {}
        if usage:
            usage.setdefault("turn_count", 1)
            usage.setdefault(
                "function_call_count",
                sum(1 for item in completed.output if item.get("type") == "function_call"),
            )
            self.total_usage.update(usage)
            await emit_completion(self.emit, usage=self.total_usage, done=False)
            self.logger.debug("Usage totals updated: %s", self.total_usage)

    def _schedule_thinking_updates(self) -> None:
        if not self.request.stream or self.is_task_request:
            return
        for delay, message in _STATUS_SEQUENCE:
            jittered = delay + _JITTER.uniform(0, 0.5)
            task = asyncio.create_task(self._delayed_status(jittered, message))
            self._thinking_tasks.append(task)

    async def _delayed_status(self, delay: float, message: str) -> None:
        await asyncio.sleep(delay)
        await emit_status(self.emit, message)

    async def _cancel_thinking(self) -> None:
        while self._thinking_tasks:
            task = self._thinking_tasks.pop()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _flush_logs(self) -> None:
        """Emit buffered session logs and clear them."""
        session_id = SessionLogger.session_id.get()
        if not session_id:
            return
        logs = list(SessionLogger.logs.get(session_id, []))
        if logs and self.valves.LOG_LEVEL.upper() != "INHERIT":
            await emit_citation(self.emit, "\n".join(logs), "Logs")
        SessionLogger.logs.pop(session_id, None)


__all__ = ["ResponseRunner", "RunnerDeps"]
