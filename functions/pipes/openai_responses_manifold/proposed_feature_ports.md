# Proposed Feature Ports from Nightforge to Manifold

**Date:** 2025-11-16
**Source:** nightforge_agent_pipe.py
**Target:** openai_responses_manifold.py
**Author:** https://github.com/paul-nightforge-systems

## Overview

This document outlines the proposed features to port from the Nightforge Agent pipe into the OpenAI Responses Manifold pipe. The goal is to enhance the manifold with production-ready features while preserving its existing strengths (model aliasing, item persistence, verbosity control).

---

## Must-Have Features

### 1. RequestContext Dataclass

**Status:** =4 Not Started
**Priority:** CRITICAL
**Estimated Effort:** 2 hours
**Dependencies:** None

#### Current State (Manifold)
```python
# In _run_streaming_loop():
assistant_message = ""
total_usage: dict[str, Any] = {}
ordinal_by_url: dict[str, int] = {}
emitted_citations: list[dict] = []
status_indicator = ExpandableStatusIndicator(event_emitter)
```

State is managed via local variables in each loop method. This works but makes it harder to:
- Track requests across functions
- Add timeout detection
- Debug concurrent requests
- Extend with new state fields

#### Proposed Solution (from Nightforge)
```python
@dataclass
class RequestContext:
    """Request-scoped state container for thread-safe isolation."""

    # Core identification
    request_id: str = ""
    start_time: float = 0.0

    # Response accumulation
    assistant_message: str = ""

    # Citation tracking
    citations: list = field(default_factory=list)
    url_title_to_index: dict = field(default_factory=dict)
    emitted_citations: list = field(default_factory=list)

    # Usage tracking
    total_usage: dict = field(default_factory=dict)

    # Timeout detection
    last_activity_time: float = 0.0

    # Tool call state
    pending_tool_outputs: list = field(default_factory=list)
    active_tool_calls: dict = field(default_factory=dict)

    # MCP tracking
    mcp_server_labels: list = field(default_factory=list)
```

#### Benefits
-  Centralized state management
-  Request tracking via unique ID
-  Easier to add timeout checking
-  Thread-safe by design (new instance per request)
-  Self-documenting (all fields in one place)

#### Implementation Steps
1. Add `@dataclass` import from dataclasses
2. Add `field` import for default_factory
3. Define RequestContext class after imports
4. Update `_run_streaming_loop()` to create ctx at start
5. Replace `assistant_message` ’ `ctx.assistant_message`
6. Replace `total_usage` ’ `ctx.total_usage`
7. Replace `ordinal_by_url` ’ `ctx.url_title_to_index`
8. Replace `emitted_citations` ’ `ctx.emitted_citations`
9. Pass `ctx` to status_indicator and event handlers
10. Update `_run_nonstreaming_loop()` similarly

#### Testing
- Verify single request works
- Verify concurrent requests don't bleed state
- Verify all citations still work
- Verify usage tracking still works

---

### 2. AsyncOpenAI Client

**Status:** =4 Not Started
**Priority:** HIGH
**Estimated Effort:** 4 hours
**Dependencies:** RequestContext (recommended, not required)

#### Current State (Manifold)
Uses `aiohttp.ClientSession` directly:
```python
async with self.session.post(url, json=request_body, headers=headers) as resp:
    resp.raise_for_status()
    async for chunk in resp.content.iter_chunked(4096):
        # Manual SSE parsing
        buf.extend(chunk)
        # ... parse data: lines ...
        yield json.loads(data_part.decode("utf-8"))
```

**Issues:**
- Manual SSE parsing (error-prone)
- No type safety on events (dict, not Pydantic)
- No built-in retry logic
- Must manually manage session lifecycle

#### Proposed Solution (from Nightforge)
```python
from openai import AsyncOpenAI

async def _get_async_client(self) -> AsyncOpenAI:
    """Get or create AsyncOpenAI client."""
    limits = httpx.Limits(
        max_connections=10,
        max_keepalive_connections=5,
        keepalive_expiry=30.0
    )

    timeout = httpx.Timeout(
        connect=30.0,
        read=self.valves.REQUEST_TIMEOUT,
        write=30.0,
        pool=10.0
    )

    async_http_client = httpx.AsyncClient(
        limits=limits,
        timeout=timeout,
        http2=True,
        verify=self.valves.VERIFY_SSL
    )

    return AsyncOpenAI(
        api_key=self.valves.API_KEY,
        timeout=self.valves.REQUEST_TIMEOUT,
        http_client=async_http_client
    )

# Usage:
client = await self._get_async_client()
stream = await client.responses.create(
    model=body.model,
    input=body.input,
    stream=True,
    **extra_params
)

async for event in stream:
    # event is typed Pydantic object
    if event.type == "response.output_text.delta":
        print(event.delta)
```

#### Benefits
-  Type-safe events (Pydantic models)
-  Official OpenAI SDK support
-  Built-in SSE parsing
-  HTTP/2 support for better performance
-  Automatic retry on transient errors
-  Better error messages

#### Implementation Steps
1. Add `from openai import AsyncOpenAI` import
2. Add `import httpx` import
3. Add `_get_async_client()` method
4. Add `VERIFY_SSL` valve (default: True)
5. Replace `send_openai_responses_streaming_request()` with AsyncOpenAI calls
6. Update event handling to use typed event objects instead of dicts
7. Remove manual SSE parsing code
8. Update `send_openai_responses_nonstreaming_request()` similarly
9. Remove `_get_or_init_http_session()` (no longer needed)
10. Clean up aiohttp imports

#### Testing
- Test streaming responses
- Test non-streaming responses
- Test with tool calls
- Test error handling
- Test HTTP/2 fallback to HTTP/1.1

#### Notes
- This is a larger refactor but provides significant benefits
- Can be done incrementally (streaming first, then non-streaming)
- May change event field names (dict keys ’ object attributes)

---

### 3. Connection Retry Logic

**Status:** =4 Not Started
**Priority:** HIGH
**Estimated Effort:** 2 hours
**Dependencies:** None (but works better with AsyncOpenAI)

#### Current State (Manifold)
No retry logic. Connection errors are fatal:
```python
async with self.session.post(url, ...) as resp:
    resp.raise_for_status()  # Dies on any error
```

**Common errors that should be retried:**
- "Connection reset by peer"
- "Incomplete chunked read"
- "Remote end closed connection"
- HTTP 429 (rate limit)
- HTTP 503 (service unavailable)

#### Proposed Solution (from Nightforge)
```python
async def _handle_connection_error(
    self,
    error: Exception,
    attempt: int,
    max_retries: int = 3
) -> bool:
    """
    Handle connection errors with exponential backoff.

    Returns True if should retry, False otherwise.
    """
    error_str = str(error).lower()

    retryable_errors = [
        "peer closed connection",
        "incomplete chunked read",
        "connection reset",
        "connection aborted",
        "remote protocol error"
    ]

    should_retry = (
        any(err in error_str for err in retryable_errors)
        and attempt <= max_retries
    )

    if should_retry:
        # Exponential backoff: 1s, 2s, 4s
        wait_time = 2 ** (attempt - 1)
        self.logger.warning(
            "Connection error (attempt %s/%s): %s. Retrying in %ss...",
            attempt, max_retries, error, wait_time
        )
        await asyncio.sleep(wait_time)
        return True

    self.logger.error(
        "Connection error (final failure after %s attempts): %s",
        attempt, error
    )
    return False

# Usage in streaming loop:
max_retries = 3
for attempt in range(1, max_retries + 1):
    try:
        response = await client.responses.create(...)
        break  # Success
    except Exception as e:
        if not await self._handle_connection_error(e, attempt, max_retries):
            raise  # Give up
```

#### Benefits
-  Handles transient network errors gracefully
-  Exponential backoff prevents overwhelming server
-  Configurable retry count
-  Clear logging of retry attempts
-  Doesn't retry on permanent errors (401, 404, etc.)

#### Implementation Steps
1. Add `_handle_connection_error()` method
2. Add `MAX_RETRIES` valve (default: 3)
3. Wrap API calls in retry loop
4. Add appropriate logging
5. Test with simulated connection errors

#### Testing
- Simulate "connection reset" error
- Verify retries with backoff
- Verify gives up after max_retries
- Verify doesn't retry on 401/403/404

---

### 4. Stream Timeout Protection

**Status:** =4 Not Started
**Priority:** HIGH
**Estimated Effort:** 1 hour
**Dependencies:** RequestContext (stores last_activity_time)

#### Current State (Manifold)
No stream timeout detection. A stalled stream will hang indefinitely.

**Problem:**
- If OpenAI server stops sending events but doesn't close connection
- Request hangs until global timeout (3600s read timeout)
- No way to detect "dead" streams

#### Proposed Solution (from Nightforge)
```python
class StreamTimeoutError(Exception):
    """Raised when stream activity timeout is exceeded."""

def _check_stream_timeout(self, ctx: RequestContext):
    """
    Check if stream has been inactive for too long.

    Raises StreamTimeoutError if inactive > STREAM_TIMEOUT seconds.
    """
    if ctx.last_activity_time == 0.0:
        ctx.last_activity_time = time.time()
        return

    current_time = time.time()
    time_since_activity = current_time - ctx.last_activity_time

    if time_since_activity > self.valves.STREAM_TIMEOUT:
        self.logger.warning(
            "Stream timeout: %.2fs (req: %s)",
            time_since_activity, ctx.request_id
        )
        raise StreamTimeoutError(
            f"Stream inactive for {time_since_activity:.2f}s"
        )

def _update_stream_activity(self, ctx: RequestContext):
    """Update stream activity timestamp."""
    ctx.last_activity_time = time.time()

# Usage in event loop:
async for event in stream:
    self._check_stream_timeout(ctx)  # Check first

    # Handle event...

    self._update_stream_activity(ctx)  # Update after
```

#### Benefits
-  Detects stalled streams
-  Configurable timeout threshold
-  Clear error message
-  Prevents indefinite hangs

#### Implementation Steps
1. Add `StreamTimeoutError` exception class
2. Add `STREAM_TIMEOUT` valve (default: 60 seconds)
3. Add `_check_stream_timeout()` method
4. Add `_update_stream_activity()` method
5. Add `last_activity_time` to RequestContext
6. Call `_check_stream_timeout()` at start of event loop iteration
7. Call `_update_stream_activity()` after processing event
8. Wrap in try/except to catch StreamTimeoutError

#### Testing
- Simulate stalled stream (mock)
- Verify timeout raises exception
- Verify active streams don't timeout
- Verify timeout is configurable via valve

---

### 5. Credential Redaction

**Status:** =4 Not Started
**Priority:** HIGH (Security)
**Estimated Effort:** 1 hour
**Dependencies:** None

#### Current State (Manifold)
No credential redaction. API keys and tokens can leak into logs:
```python
self.logger.debug("Request body: %s", request_body)
# If DEBUG enabled, logs: {"api_key": "sk-proj-abc123..."}
```

**Security Risk:**
- API keys in logs (if DEBUG_EVENTS enabled)
- Bearer tokens in error messages
- Passwords in tool arguments
- Compliance violations (SOC2, GDPR, PCI)

#### Proposed Solution (from Nightforge)
```python
def _redact_sensitive_data(self, text: str) -> str:
    """
    Redact API keys, tokens, and credentials from text.

    Safe for logging potentially sensitive data.
    """
    if not isinstance(text, str):
        text = str(text)

    patterns = [
        # OpenAI API keys
        (r'sk-proj-[a-zA-Z0-9_-]{20,}', 'sk-proj-***REDACTED***'),
        (r'sk-[a-zA-Z0-9_-]{20,}', 'sk-***REDACTED***'),

        # Bearer tokens
        (r'Bearer\s+[a-zA-Z0-9._-]{20,}', 'Bearer ***REDACTED***'),

        # Generic API keys
        (r'api[_-]?key["\s:=]+[\'"]?([a-zA-Z0-9_-]{20,})',
         'api_key=***REDACTED***'),

        # Passwords
        (r'password["\s:=]+[\'"]?([^\s\'"]+)',
         'password=***REDACTED***'),
    ]

    redacted = text
    for pattern, replacement in patterns:
        redacted = re.sub(
            pattern,
            replacement,
            redacted,
            flags=re.IGNORECASE
        )

    return redacted

# Usage:
self.logger.debug(
    "Request body: %s",
    self._redact_sensitive_data(json.dumps(request_body))
)
```

#### Benefits
-  Prevents API key leaks
-  Compliance friendly
-  Safe debug logging
-  Minimal performance impact (only when logging)

#### Implementation Steps
1. Add `_redact_sensitive_data()` method
2. Wrap all `self.logger.debug()` calls that log request/response data
3. Wrap error messages that might contain credentials
4. Test with actual API keys to verify redaction

#### Testing
- Log message with real API key ’ verify redacted
- Log message with Bearer token ’ verify redacted
- Log message with password ’ verify redacted
- Verify performance impact is minimal

---

### 6. MCP Tool Execution

**Status:** =4 Not Started
**Priority:** MEDIUM
**Estimated Effort:** 3 hours
**Dependencies:** None

#### Current State (Manifold)
MCP tools are prepared but **not executed locally**:
```python
# _build_mcp_tools() creates MCP tool specs
# But no _execute_mcp_tool() method exists
```

**Clarification:**
The Responses API supports MCP tools as **server-side tools**:
- OpenAI ’ Your Open WebUI MCP endpoint ’ MCP Server
- No local execution needed in most cases

**When you need local MCP execution:**
1. You want to execute MCP tools without going through OpenAI
2. You want to test MCP tools locally
3. You want to provide MCP results to model without server-side MCP

#### Proposed Solution (from Nightforge)
```python
async def _execute_mcp_tool(
    self,
    tool_name: str,
    arguments: str,
    __request__: Optional[Request] = None
) -> str:
    """
    Execute an MCP tool using Open WebUI's internal MCPClient.

    Args:
        tool_name: Full tool name (e.g., "netsuite_mcp_searchCustomer")
        arguments: JSON string of tool arguments
        __request__: FastAPI Request object for accessing app state

    Returns:
        JSON string with tool result or error
    """
    if MCPClient is None:
        return json.dumps({
            "error": "MCP execution not available",
            "tool": tool_name
        })

    try:
        # Parse tool name: {server_id}_mcp_{tool_name}
        parts = tool_name.split('_mcp_', 1)
        if len(parts) != 2:
            return json.dumps({
                "error": f"Invalid MCP tool name: {tool_name}"
            })

        server_id, actual_tool_name = parts

        # Parse arguments
        args = json.loads(arguments) if arguments else {}

        # Get MCP server config from request context
        mcp_servers = __request__.app.state.config.TOOL_SERVER_CONNECTIONS
        server_config = next(
            (s for s in mcp_servers
             if s.get("type") == "mcp"
             and s.get("info", {}).get("id") == server_id),
            None
        )

        if not server_config:
            return json.dumps({
                "error": f"MCP server '{server_id}' not found"
            })

        # Execute via MCPClient
        async with MCPClient() as mcp_client:
            await mcp_client.connect(
                server_config["url"],
                headers=server_config.get("headers", {})
            )
            result = await mcp_client.call_tool(actual_tool_name, args)

            return json.dumps(result) if isinstance(result, dict) else str(result)

    except Exception as e:
        return json.dumps({
            "error": f"MCP execution failed: {str(e)}",
            "tool": tool_name
        })

def _is_mcp_tool(self, tool_name: str, mcp_server_labels: list) -> bool:
    """Check if tool is from an MCP server."""
    if not tool_name:
        return False

    tool_lower = tool_name.lower()

    # Check if tool name starts with known MCP server label
    for label in mcp_server_labels:
        if label and tool_lower.startswith(label.lower()):
            return True

    # Check for _mcp_ pattern
    return '_mcp_' in tool_lower or tool_lower.startswith('mcp_')
```

#### Benefits
-  Local MCP tool testing
-  Bypass OpenAI for MCP calls (lower latency)
-  Direct integration with Open WebUI MCP system
-  Error handling for MCP failures

#### Implementation Steps
1. Add `from open_webui.utils.mcp.client import MCPClient` import
2. Add try/except wrapper for graceful fallback if import fails
3. Add `_execute_mcp_tool()` method
4. Add `_is_mcp_tool()` helper method
5. Integrate into `_execute_function_calls()` to detect and route MCP tools
6. Test with sample MCP server

#### Testing
- Test with NetSuite MCP server (if available)
- Test with mock MCP server
- Test error cases (server not found, connection failed, etc.)
- Verify fallback when MCPClient not available

#### Note
**Decision needed:** Do we want local MCP execution or rely on server-side MCP?
- Server-side: OpenAI handles MCP calls (simpler, but requires OpenAI)
- Local: We execute MCP calls (more control, works offline)

**Recommendation:** Port this for **flexibility**, but make it optional.

---

### 7. Tool Output Limits

**Status:** =4 Not Started
**Priority:** MEDIUM
**Estimated Effort:** 1 hour
**Dependencies:** None

#### Current State (Manifold)
No limits on tool output size:
```python
return [
    {
        "type": "function_call_output",
        "call_id": call["call_id"],
        "output": str(result),  # Could be huge!
    }
    for call, result in zip(calls, results)
]
```

**Problem:**
- Large tool outputs (e.g., database dumps) can exhaust token limits
- Causes 400 error: "This model's maximum context length is X tokens"
- No warning to user about truncation

#### Proposed Solution (from Nightforge)
```python
class Pipe:
    # Class constant
    MAX_TOOL_OUTPUT_CHARS = 50000  # ~12k tokens

# In _execute_function_calls():
results = await asyncio.gather(*tasks)

outputs = []
for call, result in zip(calls, results):
    output_str = str(result)

    # Truncate if too large
    if len(output_str) > self.MAX_TOOL_OUTPUT_CHARS:
        self.logger.warning(
            "Tool output truncated: %s (%s ’ %s chars)",
            call["name"],
            len(output_str),
            self.MAX_TOOL_OUTPUT_CHARS
        )
        output_str = (
            output_str[:self.MAX_TOOL_OUTPUT_CHARS]
            + f"\n\n[Output truncated: exceeded {self.MAX_TOOL_OUTPUT_CHARS} character limit]"
        )

    outputs.append({
        "type": "function_call_output",
        "call_id": call["call_id"],
        "output": output_str,
    })

return outputs
```

#### Benefits
-  Prevents token overflow
-  Clear user message when truncated
-  Logged for debugging
-  Configurable limit

#### Implementation Steps
1. Add `MAX_TOOL_OUTPUT_CHARS` class constant (50000)
2. Add truncation logic in `_execute_function_calls()`
3. Add warning log when truncating
4. Add truncation message to output
5. Optionally add valve to make limit configurable

#### Testing
- Test with normal tool output (< 50k chars) ’ no truncation
- Test with huge tool output (> 50k chars) ’ truncated
- Verify truncation message appears
- Verify model still gets result (just truncated)

---

### 8. GPT-5.1 and GPT-5-Codex Model Support

**Status:** =â COMPLETE
**Priority:** HIGH
**Estimated Effort:** 1 hour
**Dependencies:** None

#### Changes Made
 Updated FEATURE_SUPPORT dict with new models
 Added model aliases for gpt-5.1 family
 Updated MODEL_ID valve description

See git commit for details.

---

## Implementation Order

### Phase 1: Foundation (Week 1)
**Goal:** Infrastructure without breaking changes

1.  GPT-5.1 / Codex model support (COMPLETE)
2. RequestContext dataclass
3. Stream timeout protection
4. Tool output limits

**Rationale:** These are non-breaking and provide immediate value.

---

### Phase 2: Security (Week 2)
**Goal:** Production hardening

5. Credential redaction
6. Connection retry logic

**Rationale:** Security is important but doesn't change functionality.

---

### Phase 3: Modernization (Week 3)
**Goal:** Better architecture

7. AsyncOpenAI client migration

**Rationale:** Bigger refactor, do after foundation is solid.

---

### Phase 4: Features (Week 4)
**Goal:** Optional enhancements

8. MCP tool execution (if needed)

**Rationale:** Nice-to-have, can skip if not needed.

---

## Success Criteria

### Must Pass
-  All existing functionality still works
-  No regressions in streaming
-  No regressions in tool execution
-  No regressions in citations
-  New models work correctly

### Performance
- <¯ Stream latency unchanged (or better)
- <¯ Memory usage similar (or better)
- <¯ No deadlocks or hangs

### Security
- = No API keys in logs
- = Timeouts prevent hangs
- = Tool outputs capped

---

**Last Updated:** 2025-11-16
**Status:** Phase 1 Item 1 Complete (Model Support)
