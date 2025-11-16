"""Open WebUI manifold entry point for the OpenAI Responses API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from .adapters import RequestContext, build_responses_request
from .client import ResponsesClient
from .emitters import emit_notification, wrap_event_emitter
from .logging_utils import redact_dict, summarize_request
from .models import CompletionsRequest
from .router import GPT5Router
from .runner import ResponseRunner, RunnerDeps
from .session import SessionLogger
from .tools import build_tool_specs
from .valves import UserValves, Valves, merge

BaseValves = Valves
BaseUserValves = UserValves
valves = Valves()
user_valves = UserValves()

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import Request


def _should_send_stream_usage(valves: Valves) -> bool:
    """Return True when stream usage hints should be forwarded upstream."""

    mode = getattr(valves, "STREAM_USAGE_MODE", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    host = urlparse(valves.BASE_URL or "").hostname or ""
    return host.endswith("openai.com")


def _ensure_usage_include(passthrough: dict[str, Any]) -> None:
    """Ensure the include list requests usage statistics."""

    include = passthrough.get("include")
    if isinstance(include, list):
        values = list(include)
    else:
        values = []
    if "usage" not in values:
        values.append("usage")
    passthrough["include"] = values


def _passthrough_payload(
    body: dict[str, Any], valves: Valves, logger: logging.Logger
) -> dict[str, Any]:
    """Return passthrough params with unsupported stream options removed."""

    passthrough = {
        key: value for key, value in body.items() if key not in CompletionsRequest.model_fields
    }
    stream_options = passthrough.get("stream_options")
    if not stream_options:
        return passthrough
    if _should_send_stream_usage(valves):
        return passthrough
    passthrough.pop("stream_options", None)
    if isinstance(stream_options, dict) and stream_options.get("include_usage"):
        _ensure_usage_include(passthrough)
        logger.info("Dropping stream_options.include_usage for base URL %s", valves.BASE_URL)
    return passthrough


def _task_name(metadata: dict[str, Any] | None, task: Any) -> str | None:
    """Return the normalized task identifier, if any."""

    candidate = task or (metadata or {}).get("task")
    if not candidate:
        return None
    label = str(candidate).strip()
    return label or None


class Pipe:
    """Implements the Open WebUI Manifold API for OpenAI's Responses endpoint."""

    class Valves(BaseValves):
        """Expose the valve schema in the shape Open WebUI expects."""

    class UserValves(BaseUserValves):
        """Expose the per-user valve schema."""

    def __init__(self) -> None:
        """Initialize the manifold metadata and logger."""
        self.type = "manifold"
        self.id = "openai_responses"
        seed = globals().get("valves")
        if isinstance(seed, BaseValves):
            self.valves = self.Valves(**seed.model_dump())
        else:
            self.valves = self.Valves()
        globals()["valves"] = self.valves
        self.logger = logging.getLogger(__name__)

    async def pipes(self) -> list[dict[str, str]]:
        """Expose User-selectable models registered in the valves."""
        entries: list[dict[str, str]] = []
        for raw in self.valves.MODEL_ID.split(","):
            model_id = raw.strip()
            if not model_id:
                continue
            entries.append({"id": model_id, "name": f"OpenAI: {model_id}"})
        return entries

    async def pipe(
        self,
        body: dict[str, Any],
        __user__: dict[str, Any],
        __request__: Request,
        __event_emitter__: Callable[[dict[str, Any]], Awaitable[None]],
        __event_call__: Callable[[dict[str, Any]], Awaitable[Any]] | None,
        __metadata__: dict[str, Any],
        __tools__: dict[str, Any] | list[dict[str, Any]] | None,
        __task__: dict[str, Any] | None = None,
        __task_body__: dict[str, Any] | None = None,
    ) -> str:
        """Execute a Responses API request on behalf of Open WebUI."""
        del __request__, __task_body__
        valves = merge(self.valves, UserValves.model_validate(__user__.get("valves", {})))
        SessionLogger.session_id.set(__metadata__.get("session_id"))
        SessionLogger.level.set(getattr(logging, valves.LOG_LEVEL.upper(), logging.INFO))
        SessionLogger.bind_context(
            chat_id=__metadata__.get("chat_id"),
            message_id=__metadata__.get("message_id"),
            model_id=__metadata__.get("model", {}).get("id"),
        )
        self.logger.debug("Merged valves: %s", redact_dict(valves.model_dump()))

        task_label = _task_name(__metadata__, __task__)
        is_task_request = bool(task_label)
        if is_task_request:
            self.logger.info("Handling background task: %s", task_label)

        if __event_call__:
            await __event_call__(
                {
                    "type": "execute",
                    "data": {
                        "code": """
                    (() => {
                        if (document.getElementById('owui-status-unclamp')) return 'ok';
                        const style = document.createElement('style');
                        style.id = 'owui-status-unclamp';
                        style.textContent = `
                            .status-description .line-clamp-1 {
                                display: block !important;
                                white-space: pre-wrap !important;
                            }
                        `;
                        document.head.appendChild(style);
                        return 'ok';
                    })();
                    """,
                    },
                }
            )

        completions = CompletionsRequest.model_validate(body)
        openwebui_model_id = __metadata__.get("model", {}).get("id", "")
        chat_id = __metadata__.get("chat_id")
        user_identifier = __user__[valves.PROMPT_CACHE_KEY]
        features = __metadata__.get("features", {}).get("openai_responses", {})

        passthrough = _passthrough_payload(body, valves, self.logger)
        responses_request = build_responses_request(
            completions,
            context=RequestContext(
                chat_id=chat_id,
                model_id=openwebui_model_id,
                truncation=valves.TRUNCATION,
                user_identifier=user_identifier,
            ),
            extra_params=passthrough,
        )

        if is_task_request:
            responses_request.stream = False

        SessionLogger.bind_context(request_model=responses_request.model)
        self.logger.info("Prepared Responses request: %s", summarize_request(responses_request))

        client = ResponsesClient(api_key=valves.API_KEY, base_url=valves.BASE_URL)
        router = GPT5Router(client)
        try:
            if not is_task_request and router.should_route(openwebui_model_id):
                self.logger.info("Evaluating routing decision for %s", openwebui_model_id)
                decision = await router.route(responses_request)
                if decision:
                    responses_request.model = decision.model
                    reasoning = dict(responses_request.reasoning or {})
                    if decision.reasoning_effort:
                        reasoning.setdefault("effort", decision.reasoning_effort)
                    responses_request.reasoning = reasoning
                    SessionLogger.bind_context(request_model=decision.model)
                    self.logger.info(
                        "Router selected model=%s (effort=%s)",
                        decision.model,
                        decision.reasoning_effort,
                    )
                    await emit_notification(
                        __event_emitter__,
                        f"Routing to {decision.model} (effort={decision.reasoning_effort})",
                        level="info",
                    )

            tool_specs: list[dict[str, Any]] = []
            if not is_task_request:
                tool_specs = build_tool_specs(
                    request_model=responses_request.model,
                    valves=valves,
                    registry=__tools__ if isinstance(__tools__, dict) else None,
                    features=features,
                    extra_tools=getattr(completions, "extra_tools", None),
                )
            responses_request.tools = tool_specs or None
            if tool_specs:
                tool_labels = [
                    tool.get("name") or tool.get("type", "unknown") for tool in tool_specs
                ]
                self.logger.info(
                    "Registered %d tool(s): %s", len(tool_specs), ", ".join(tool_labels)
                )
            else:
                self.logger.info("No tools registered for %s", responses_request.model)

            emitter = wrap_event_emitter(
                __event_emitter__,
                suppress_chat_messages=is_task_request,
                suppress_completion=is_task_request,
            )
            runner = ResponseRunner(
                request=responses_request,
                deps=RunnerDeps(
                    valves=valves,
                    client=client,
                    emitter=emitter,
                    metadata=__metadata__,
                    tools=__tools__ if isinstance(__tools__, dict) else {},
                    features=features,
                    logger=self.logger,
                    is_task_request=is_task_request,
                ),
            )
            self.logger.info(
                "Dispatching Responses runner (requested_model=%s stream=%s)",
                responses_request.model,
                responses_request.stream,
            )
            try:
                result = await runner.run()
            except Exception:
                self.logger.exception("Responses runner failed")
                raise
            self.logger.info("Responses runner completed (%d chars)", len(result))
        finally:
            await client.close()
        return result


ResponsesManifold = Pipe

__all__ = ["Pipe", "ResponsesManifold"]
