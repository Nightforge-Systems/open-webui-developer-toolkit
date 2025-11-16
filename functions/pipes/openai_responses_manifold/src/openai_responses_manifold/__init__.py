"""Public exports for the OpenAI Responses manifold package."""

from .app.pipe import Pipe
from .core import (
    CompletionsBody,
    ResponsesBody,
    SessionLogger,
    alias_defaults,
    base_model,
    create_marker,
    extract_markers,
    generate_item_id,
    merge_usage_stats,
    normalize,
    parse_marker,
    split_text_by_markers,
    supports,
    wrap_code_block,
    wrap_event_emitter,
    wrap_marker,
)
from .features import build_tools, route_gpt5_auto
from .infra import OpenAIResponsesClient, fetch_openai_response_items, persist_openai_response_items

__all__ = [
    "alias_defaults",
    "base_model",
    "CompletionsBody",
    "OpenAIResponsesClient",
    "Pipe",
    "ResponsesBody",
    "SessionLogger",
    "build_tools",
    "create_marker",
    "extract_markers",
    "fetch_openai_response_items",
    "generate_item_id",
    "merge_usage_stats",
    "normalize",
    "parse_marker",
    "persist_openai_response_items",
    "route_gpt5_auto",
    "split_text_by_markers",
    "supports",
    "wrap_code_block",
    "wrap_event_emitter",
    "wrap_marker",
]
