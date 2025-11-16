"""Tool helpers for the Responses manifold."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import TYPE_CHECKING, Any, cast

from .capabilities import supports as model_supports
from .logging_utils import compact_json

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from .valves import Valves
else:  # pragma: no cover - runtime fallback for type checking
    Callable = Any  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Coerce a JSON schema into the strict shape required by OpenAI."""
    normalized = _coerce_to_object(schema)
    stack = [normalized]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        if _is_object_schema(node):
            _normalize_object_node(node)
        stack.extend(_iter_child_nodes(node))
    return normalized


def _coerce_to_object(schema: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }
    clone = json.loads(json.dumps(schema))
    if _is_object_schema(clone):
        return clone
    return {
        "type": "object",
        "properties": {"value": clone},
        "required": ["value"],
        "additionalProperties": False,
    }


def _is_object_schema(node: dict[str, Any]) -> bool:
    node_type = node.get("type")
    return (
        node_type == "object"
        or (isinstance(node_type, list) and "object" in node_type)
        or isinstance(node.get("properties"), dict)
    )


def _normalize_object_node(node: dict[str, Any]) -> None:
    properties = node.get("properties")
    if not isinstance(properties, dict):
        properties = {}
        node["properties"] = properties
    node["additionalProperties"] = False
    original_required = set(node.get("required") or [])
    node["required"] = list(properties.keys())
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        if name not in original_required:
            ptype = prop.get("type")
            if isinstance(ptype, str) and ptype != "null":
                prop["type"] = [ptype, "null"]
            elif isinstance(ptype, list) and "null" not in ptype:
                prop["type"] = [*ptype, "null"]


def _iter_child_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    props = node.get("properties")
    if isinstance(props, dict):
        children.extend(entry for entry in props.values() if isinstance(entry, dict))
    items = node.get("items")
    if isinstance(items, dict):
        children.append(items)
    elif isinstance(items, list):
        children.extend(entry for entry in items if isinstance(entry, dict))
    for branch_key in ("anyOf", "oneOf"):
        branch = node.get(branch_key)
        if isinstance(branch, list):
            children.extend(entry for entry in branch if isinstance(entry, dict))
    return children


def build_function_tools(__tools__: dict[str, Any] | None, *, strict: bool) -> list[dict[str, Any]]:
    """Convert WebUI tool registry entries into Responses tool specs."""
    if not __tools__:
        return []
    tools: list[dict[str, Any]] = []
    for entry in __tools__.values():
        spec = entry.get("spec") or {}
        name = spec.get("name")
        if not name:
            continue
        params = spec.get("parameters") or {"type": "object", "properties": {}}
        candidate = {
            "type": "function",
            "name": name,
            "description": spec.get("description") or name,
            "parameters": strict_schema(params) if strict else params,
        }
        if strict:
            candidate["strict"] = True
        tools.append(candidate)
    return tools


def _dedupe(tools: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    registry: dict[tuple[str, str | None], dict[str, Any]] = {}
    for tool in tools:
        tool_type = tool.get("type")
        if not isinstance(tool_type, str):
            continue
        key: tuple[str, str | None]
        if tool_type == "function":
            name = tool.get("name")
            if not isinstance(name, str):
                continue
            key = ("function", name)
        else:
            key = (tool_type, None)
        registry[key] = tool
    return list(registry.values())


def build_tool_specs(
    *,
    request_model: str,
    valves: Valves,
    registry: dict[str, Any] | None,
    features: dict[str, Any] | None = None,
    extra_tools: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Generate the tool list provided to a Responses API request."""
    if not model_supports("function_calling", request_model):
        return []
    features = features or {}
    specs: list[dict[str, Any]] = []
    specs.extend(build_function_tools(registry, strict=valves.ENABLE_STRICT_TOOL_CALLING))

    allow_web = model_supports("web_search_tool", request_model) and (
        valves.ENABLE_WEB_SEARCH_TOOL or features.get("web_search")
    )
    if allow_web:
        tool = {"type": "web_search", "search_context_size": valves.WEB_SEARCH_CONTEXT_SIZE}
        if valves.WEB_SEARCH_USER_LOCATION:
            try:
                tool["user_location"] = json.loads(valves.WEB_SEARCH_USER_LOCATION)
            except json.JSONDecodeError as exc:  # pragma: no cover
                logger.warning("Invalid WEB_SEARCH_USER_LOCATION JSON: %s", exc)
        specs.append(tool)

    if valves.REMOTE_MCP_SERVERS_JSON:
        specs.extend(_build_mcp_tools(valves.REMOTE_MCP_SERVERS_JSON))

    if extra_tools:
        specs.extend(extra_tools)
    return _dedupe(specs)


def _build_mcp_tools(payload: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:  # pragma: no cover
        logger.warning("REMOTE_MCP_SERVERS_JSON invalid: %s", exc)
        return []
    candidates = data if isinstance(data, list) else [data]
    allowed = {"server_label", "server_url", "require_approval", "allowed_tools", "headers"}
    output: list[dict[str, Any]] = []
    for idx, entry in enumerate(candidates, start=1):
        if not isinstance(entry, dict):
            logger.warning("MCP entry %d ignored: not an object", idx)
            continue
        if not entry.get("server_label") or not entry.get("server_url"):
            logger.warning("MCP entry %d ignored: missing label/url", idx)
            continue
        request = {"type": "mcp"}
        request.update({k: entry[k] for k in allowed if k in entry})
        output.append(request)
    return output


def _parse_call_arguments(call: dict[str, Any]) -> dict[str, Any]:
    payload = call.get("arguments")
    if not payload:
        return {}
    try:
        args = json.loads(payload)
    except json.JSONDecodeError as exc:
        logger.warning("Tool %s received invalid JSON arguments: %s", call.get("name"), exc)
        return {}
    return args if isinstance(args, dict) else {}


async def _execute_tool_call(
    call: dict[str, Any], registry: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    name = call.get("name") or "<unknown>"
    call_id = call.get("call_id") or "<none>"
    logger.info("Executing tool %s (call_id=%s)", name, call_id)
    config = registry.get(name)
    if not config:
        logger.warning("Tool %s not found in registry", name)
        return {"type": "function_call_output", "call_id": call_id, "output": "Tool not found"}
    func = config.get("callable")
    if not callable(func):
        logger.warning("Tool %s has no callable attached", name)
        return {"type": "function_call_output", "call_id": call_id, "output": "Tool not callable"}
    args = _parse_call_arguments(call)
    logger.debug("Tool %s args=%s", name, compact_json(args))
    callable_func = cast("Callable[..., Any]", func)
    try:
        if inspect.iscoroutinefunction(callable_func):
            result = await callable_func(**args)
        else:
            result = await asyncio.to_thread(callable_func, **args)
    except Exception as exc:
        logger.exception("Tool %s raised an exception", name)
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": f"Tool execution failed: {exc}",
        }
    return {"type": "function_call_output", "call_id": call_id, "output": str(result)}


async def run_function_calls(
    calls: list[dict[str, Any]],
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Execute asynchronous function calls defined by the registry."""
    if not calls:
        return []
    tasks = [_execute_tool_call(call, registry) for call in calls]
    return await asyncio.gather(*tasks)


__all__ = [
    "build_function_tools",
    "build_tool_specs",
    "run_function_calls",
    "strict_schema",
]
