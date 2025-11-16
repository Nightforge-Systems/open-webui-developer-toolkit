"""Valve models controlling how the Responses manifold behaves."""

from __future__ import annotations

import os
from typing import Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

_LOG_LEVELS: Final[set[str]] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _default_log_level() -> Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    candidate = (os.getenv("GLOBAL_LOG_LEVEL") or "INFO").strip().upper()
    value = candidate if candidate in _LOG_LEVELS else "INFO"
    return cast(Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], value)


class Valves(BaseModel):
    """Global valve configuration for the manifold."""

    model_config = ConfigDict(extra="forbid")

    BASE_URL: str = Field(
        default=((os.getenv("OPENAI_API_BASE_URL") or "").strip() or "https://api.openai.com/v1"),
        description="OpenAI API base URL.",
    )
    API_KEY: str = Field(
        default=(os.getenv("OPENAI_API_KEY") or "").strip() or "sk-xxxxx",
        description="OpenAI API key.",
    )
    MODEL_ID: str = Field(
        default="gpt-5-auto, gpt-5-chat-latest, gpt-4o",
        description="Comma-separated OpenAI model IDs registered in WebUI.",
    )
    REASONING_SUMMARY: Literal["auto", "concise", "detailed", "disabled"] = "disabled"
    PERSIST_REASONING_TOKENS: Literal["response", "conversation", "disabled"] = "disabled"
    PERSIST_TOOL_RESULTS: bool = True
    PARALLEL_TOOL_CALLS: bool = True
    ENABLE_STRICT_TOOL_CALLING: bool = True
    MAX_TOOL_CALLS: int | None = None
    MAX_FUNCTION_CALL_LOOPS: int = 10
    ENABLE_WEB_SEARCH_TOOL: bool = False
    WEB_SEARCH_CONTEXT_SIZE: Literal["low", "medium", "high"] | None = "medium"
    WEB_SEARCH_USER_LOCATION: str | None = None
    REMOTE_MCP_SERVERS_JSON: str | None = None
    TRUNCATION: Literal["auto", "disabled"] = "auto"
    PROMPT_CACHE_KEY: Literal["id", "email"] = "id"
    STREAM_USAGE_MODE: Literal["auto", "always", "never"] = Field(
        default="auto",
        description="Control when stream_options.include_usage is forwarded (auto limits to api.openai.com).",
    )
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default_factory=_default_log_level
    )


class UserValves(BaseModel):
    """User-specific overrides for select valves."""

    model_config = ConfigDict(extra="forbid")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "INHERIT"] = "INHERIT"


def merge(global_valves: Valves, user_valves: UserValves | None) -> Valves:
    """Merge user-level overrides into the global valve configuration."""
    if not user_valves:
        return global_valves
    override = {
        key: value
        for key, value in user_valves.model_dump().items()
        if value is not None and str(value).upper() != "INHERIT"
    }
    return global_valves.model_copy(update=override)


__all__ = ["UserValves", "Valves", "merge"]
