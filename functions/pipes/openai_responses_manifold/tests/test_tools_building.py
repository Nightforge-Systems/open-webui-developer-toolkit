"""Tests for tool construction helpers."""

from __future__ import annotations

import json

import openai_responses_manifold as orm
from openai_responses_manifold import ResponsesBody


def _responses_body(model: str = "gpt-4o") -> ResponsesBody:
    return ResponsesBody(model=model, input=[], stream=True)


def test_build_tools_includes_web_search_when_enabled() -> None:
    valves = orm.Pipe.Valves(
        ENABLE_WEB_SEARCH_TOOL=True,
        WEB_SEARCH_CONTEXT_SIZE="high",
        WEB_SEARCH_USER_LOCATION='{"country":"US"}',
    )
    tools = orm.build_tools(_responses_body(), valves)

    web_search = next(tool for tool in tools if tool["type"] == "web_search")
    assert web_search["search_context_size"] == "high"
    assert web_search["user_location"]["country"] == "US"


def test_build_tools_adds_remote_mcp_servers() -> None:
    valves = orm.Pipe.Valves(
        REMOTE_MCP_SERVERS_JSON=json.dumps(
            {
                "server_label": "Docs",
                "server_url": "https://example.com/mcp",
                "model_preference": {"gpt-4o": 1.0},
            }
        )
    )
    tools = orm.build_tools(_responses_body(), valves)

    mcp = next(tool for tool in tools if tool["type"] == "mcp")
    assert mcp["server_label"] == "Docs"
    assert mcp["server_url"] == "https://example.com/mcp"
    assert mcp["model_preference"]["gpt-4o"] == 1.0


def test_build_tools_dedupes_function_specs() -> None:
    owui_tools = {
        "a": {
            "spec": {
                "name": "duplicate",
                "description": "First",
                "parameters": {"type": "object", "properties": {}},
            }
        },
        "b": {
            "spec": {
                "name": "duplicate",
                "description": "Second",
                "parameters": {"type": "object", "properties": {}},
            }
        },
    }
    valves = orm.Pipe.Valves(ENABLE_STRICT_TOOL_CALLING=True)
    tools = orm.build_tools(_responses_body(), valves, __tools__=owui_tools)

    function_tools = [tool for tool in tools if tool["type"] == "function"]
    assert len(function_tools) == 1
    assert function_tools[0]["name"] == "duplicate"
