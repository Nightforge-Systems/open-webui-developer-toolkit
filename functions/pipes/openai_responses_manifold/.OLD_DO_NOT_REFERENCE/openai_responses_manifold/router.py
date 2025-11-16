"""Router that upgrades ambiguous GPT-5 requests."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from .logging_utils import truncate_text
from .models import ResponsesRequest, RouterDecision

if TYPE_CHECKING:
    from .client import ResponsesClient

_ROUTER_PROMPT = """# Role and Objective
Serve as a routing helper for selecting the most appropriate GPT-5 model for user messages.

# Output Format
Respond with JSON containing keys: model, reasoning_effort, explanation."""


class GPT5Router:
    """Simple reasoning router that selects a GPT-5 variant."""

    def __init__(self, client: ResponsesClient) -> None:
        """Store the HTTP client used to invoke meta-prompts."""
        self._client = client
        self.logger = logging.getLogger(__name__)

    def should_route(self, model_id: str) -> bool:
        """Return True if routing logic should run."""
        return model_id.endswith((".gpt-5-auto", ".gpt-5-auto-dev"))

    async def route(self, request: ResponsesRequest) -> RouterDecision | None:
        """Call the Responses API to determine a better model, if any."""
        self.logger.info("Invoking router for request model %s", request.model)
        payload = request.model_dump(exclude_none=True)
        payload.update(
            {
                "model": "gpt-5-mini",
                "reasoning": {"effort": "minimal"},
                "instructions": _ROUTER_PROMPT,
                "stream": False,
                "store": False,
            },
        )
        response = await self._client.invoke(ResponsesRequest(**payload))
        text = ""
        for item in response.get("output", []):
            if item.get("type") != "message":
                continue
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    text = block.get("text", "")
        if not text:
            self.logger.info("Router returned no text; keeping model %s", request.model)
            return None
        try:
            parsed: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            parsed = json.loads(text[start : end + 1]) if start != -1 and end > start else {}
            if not parsed:
                self.logger.warning("Router response not valid JSON: %s", truncate_text(text))
        if not parsed:
            self.logger.info("Router response lacked decision fields; keeping %s", request.model)
            return None
        self.logger.debug("Router decision payload: %s", parsed)
        return RouterDecision(
            model=parsed.get("model", request.model),
            reasoning_effort=parsed.get("reasoning_effort"),
            explanation=parsed.get("explanation"),
        )


__all__ = ["GPT5Router"]

logger = logging.getLogger(__name__)
