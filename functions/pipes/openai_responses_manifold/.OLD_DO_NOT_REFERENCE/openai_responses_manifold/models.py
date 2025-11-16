"""Data models shared across the manifold implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from .capabilities import alias_defaults, base_model


class CompletionsRequest(BaseModel):
    """Mirror of the payload Forwarded by Open WebUI."""

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[dict[str, Any]]
    stream: bool = True


class ResponsesRequest(BaseModel):
    """OpenAI Responses API payload."""

    model_config = ConfigDict(extra="allow")

    model: str
    input: str | list[dict[str, Any]]
    instructions: str | None = ""
    stream: bool = True
    store: bool | None = False
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    truncation: Literal["auto", "disabled"] | None = None
    reasoning: dict[str, Any] | None = None
    parallel_tool_calls: bool | None = True
    user: str | None = None
    tool_choice: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    include: list[str] | None = None

    @model_validator(mode="before")
    @classmethod
    def _apply_alias_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw_model = data.get("model", "")
        normalized = base_model(raw_model)
        defaults = alias_defaults(raw_model) or {}
        if normalized == raw_model and not defaults:
            return data
        payload = dict(data)
        payload["model"] = normalized

        def merge(target: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
            for key, value in overlay.items():
                if isinstance(value, dict):
                    base = target.get(key)
                    nested = base if isinstance(base, dict) else {}
                    target[key] = merge(nested, value)
                elif isinstance(value, list):
                    existing = target.get(key)
                    if isinstance(existing, list):
                        seen = set()
                        merged: list[Any] = []
                        for item in existing + value:
                            marker = (
                                ("json", str(item))
                                if isinstance(item, (dict, list))
                                else ("raw", item)
                            )
                            if marker not in seen:
                                seen.add(marker)
                                merged.append(item)
                        target[key] = merged
                    else:
                        target[key] = list(value)
                else:
                    target[key] = value
            return target

        merge(payload, defaults)
        return payload


@dataclass
class RouterDecision:
    """Result from routing a request to a more appropriate model."""

    model: str
    reasoning_effort: str | None = None
    explanation: str | None = None


@dataclass
class TextDelta:
    """Represents a token delta event."""

    text: str


@dataclass
class ReasoningSummary:
    """Summarized reasoning output emitted by the model."""

    text: str


@dataclass
class OutputItem:
    """Generic output block returned by the Responses API."""

    item: dict[str, Any]
    event_type: str | None = None


@dataclass
class Usage:
    """Usage statistics returned by OpenAI."""

    stats: dict[str, Any]


@dataclass
class Completed:
    """Final completion event from the Responses API."""

    output: list[dict[str, Any]]
    usage: dict[str, Any] | None = None


@dataclass
class Error:
    """Error message event emitted by the API."""

    message: str


RunEvent = TextDelta | ReasoningSummary | OutputItem | Usage | Completed | Error


__all__ = [
    "Completed",
    "CompletionsRequest",
    "Error",
    "OutputItem",
    "ReasoningSummary",
    "ResponsesRequest",
    "RouterDecision",
    "RunEvent",
    "TextDelta",
    "Usage",
]
