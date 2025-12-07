# OpenAI Responses Manifold Pipeline Architecture

**Last Updated:** 2025-11-16
**Pipeline:** `openai_responses_manifold.py`
**OpenAI API:** Responses API (GPT-5, o-series)
**Author (this document only):** https://github.com/paul-nightforge-systems

## Overview

The OpenAI Responses Manifold Pipeline provides a unified interface to OpenAI's Responses API, supporting GPT-5, o-series, and other OpenAI models through a manifold pattern. It handles streaming responses, tool execution, reasoning token persistence, and citation management.

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ENTRY POINT: pipe()                                │
│  - Receives body from Open WebUI                                            │
│  - Merges global and user-level valves                                      │
│  - Initializes session logger with session_id                               │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  PHASE 1: REQUEST TRANSFORMATION                            │
│  CompletionsBody → ResponsesBody:                                           │
│  1. Validate incoming body with Pydantic                                    │
│  2. Normalize model ID (strip prefix, map aliases)                          │
│     - "o3-mini-high" → "o3-mini" with reasoning_effort="high"               │
│     - "gpt-5-thinking-minimal" → "gpt-5" with reasoning_effort="minimal"    │
│  3. Extract last system message → instructions                              │
│  4. Convert messages to Responses API input format                          │
│     - Skip system messages (go to instructions)                             │
│     - User messages: text → input_text blocks                               │
│     - Assistant messages with markers → fetch persisted items from DB       │
│  5. Drop unsupported params (frequency_penalty, etc.)                       │
│  6. Rename max_tokens → max_output_tokens                                   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PHASE 2: FEATURE DETECTION                              │
│  Normalize model family (strip date: "o3-2025-04-16" → "o3"):               │
│  1. Check FEATURE_SUPPORT for model capabilities                            │
│  2. Detect if task model (generate title/tags) → special handling           │
│  3. Detect GPT-5-Auto → route to gpt-5-chat-latest (future: smart routing)  │
│  4. Check verbosity directives ("Add Details"/"More Concise")               │
│     - Map to text.verbosity parameter (high/low)                            │
│     - Remove directive stub from input                                      │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PHASE 3: TOOL ASSEMBLY                                  │
│  1. Transform __tools__ from Open WebUI format:                             │
│     - __tools__ dict with "spec" → Responses API format                     │
│     - Chat-Completions wrapper → flatten to native format                   │
│     - Non-function tools (web_search) → pass through verbatim               │
│  2. Deduplicate tools (later wins):                                         │
│     - Functions keyed by "name"                                             │
│     - Non-functions keyed by "type"                                         │
│  3. Apply strict mode if requested (all params required, nullable types)    │
│  4. Add web_search_preview if enabled and supported                         │
│     - Attach search_context_size, user_location config                      │
│     - Skip if reasoning_effort="minimal" (incompatible)                     │
│  5. Append remote MCP servers from REMOTE_MCP_SERVERS_JSON valve            │
│     - Parse JSON array/object                                               │
│     - Validate required keys (server_label, server_url)                     │
│     - Whitelist allowed MCP fields                                          │
│  6. Auto-enable native function calling in model config if needed           │
│     - Check OpenWebUI model params["function_calling"]                      │
│     - Update to "native" if tools present and model supports it             │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  PHASE 4: REASONING & PERSISTENCE CONFIG                    │
│  1. Enable reasoning summary if valve enabled and supported                 │
│     - reasoning.summary = "auto"/"concise"/"detailed"                       │
│  2. Request encrypted reasoning tokens if enabled:                          │
│     - PERSIST_REASONING_TOKENS="response" → in-turn carry only              │
│     - PERSIST_REASONING_TOKENS="conversation" → persist across turns        │
│     - Add "reasoning.encrypted_content" to include[] array                  │
│  3. Set service_tier, truncation, user identifier for caching               │
│  4. Apply max_tool_calls limit if configured                                │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  Stream or blocking?   │
                    └────────────┬───────────┘
                                 │
                    Stream       │        Blocking
            ┌────────────────────┼────────────────────┐
            ▼                                         ▼
┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│ PHASE 5A: STREAMING LOOP         │  │ PHASE 5B: NON-STREAMING LOOP     │
│ (_run_streaming_loop)            │  │ (_run_nonstreaming_loop)         │
│                                  │  │                                  │
│ Initialize local state:          │  │ Initialize local state:          │
│ - assistant_message = ""         │  │ - assistant_message = ""         │
│ - total_usage = {}               │  │ - total_usage = {}               │
│ - ordinal_by_url = {}            │  │ - reasoning_map = {}             │
│ - emitted_citations = []         │  │                                  │
│ - status_indicator               │  │ - status_indicator               │
│                                  │  │                                  │
│ For loop_idx in range(           │  │ For loop_idx in range(           │
│   MAX_FUNCTION_CALL_LOOPS):      │  │   MAX_FUNCTION_CALL_LOOPS):      │
│                                  │  │                                  │
│ ┌──────────────────────────────┐ │  │ ┌──────────────────────────────┐ │
│ │ Send aiohttp POST request    │ │  │ │ Send aiohttp POST request    │ │
│ │ to /responses with SSE       │ │  │ │ to /responses (JSON)         │ │
│ │                              │ │  │ │                              │ │
│ │ async for event in stream:   │ │  │ │ response = await post()      │ │
│ │                              │ │  │ │                              │ │
│ │ Event types handled:         │ │  │ │ Parse response.output:       │ │
│ │ ┌──────────────────────────┐ │ │  │ │ ┌──────────────────────────┐ │ │
│ │ │ response.output_text     │ │ │  │ │ │ message items → append   │ │ │
│ │ │   .delta                 │ │ │  │ │ │   text to assistant_msg  │ │ │
│ │ │ - Emit delta to UI       │ │ │  │ │ │                          │ │ │
│ │ │ - Append to assistant_msg│ │ │  │ │ │ reasoning_summary_text   │ │ │
│ │ ├──────────────────────────┤ │ │  │ │ │ - Extract title/content  │ │ │
│ │ │ response.reasoning       │ │ │  │ │ │ - Add to status block    │ │ │
│ │ │   _summary_text.done     │ │ │  │ │ ├──────────────────────────┤ │ │
│ │ │ - Extract title from **  │ │ │  │ │ │ function_call items      │ │ │
│ │ │ - Add to status block    │ │ │  │ │ │ - Persist if enabled     │ │ │
│ │ ├──────────────────────────┤ │ │  │ │ │ - Add to status block    │ │ │
│ │ │ response.output_text     │ │ │  │ │ ├──────────────────────────┤ │ │
│ │ │   .annotation.added      │ │ │  │ │ │ web_search_call, etc.    │ │ │
│ │ │ - Extract URL, title     │ │ │  │ │ │ - Persist if enabled     │ │ │
│ │ │ - Dedupe by URL          │ │ │  │ │ │ - Add to status block    │ │ │
│ │ │ - Emit citation event    │ │ │  │ │ └──────────────────────────┘ │ │
│ │ │ - Insert [N] in text     │ │ │  │ │                              │ │
│ │ ├──────────────────────────┤ │ │  │ │ Extend body.input with       │ │
│ │ │ response.output_item     │ │ │  │ │   all items                  │ │
│ │ │   .added                 │ │ │  │ └──────────────────────────────┘ │
│ │ │ - message in_progress    │ │ │  │                                  │
│ │ │  → "Responding..." status│ │ │  │ If function_call items exist:    │
│ │ ├──────────────────────────┤ │ │  │ ┌──────────────────────────────┐ │
│ │ │ response.output_item     │ │ │  │ │ Execute function calls       │ │
│ │ │   .done                  │ │ │  │ │ (_execute_function_calls)    │ │
│ │ │ - function_call: show    │ │ │  │ │ - Lookup tool in __tools__   │ │
│ │ │   arguments, persist     │ │ │  │ │ - Parse JSON args            │ │
│ │ │ - web_search_call: show  │ │ │  │ │ - Execute async/sync         │ │
│ │ │   query, persist         │ │ │  │ │ - Return outputs list        │ │
│ │ │ - mcp_call: show server, │ │ │  │ │                              │ │
│ │ │   persist                │ │ │  │ │ Persist outputs if enabled   │ │
│ │ │ - reasoning: only persist│ │ │  │ │ Add to status block          │ │
│ │ │   if PERSIST="conversation"│││  │ │ Extend body.input            │ │
│ │ ├──────────────────────────┤ │ │  │ └──────────────────────────────┘ │
│ │ │ response.completed       │ │ │  │ Loop again with tool outputs     │
│ │ │ - Extend body.input with │ │ │  │ (or break if no tools)           │
│ │ │   all output items       │ │ │  │                                  │
│ │ │ - Capture usage stats    │ │ │  │ Return assembled text            │
│ │ │ - Break event loop       │ │ │  │                                  │
│ │ └──────────────────────────┘ │ │  └──────────────────────────────────┘
│ └──────────────────────────────┘ │
│                                  │
│ If function_call items exist:    │
│ ┌──────────────────────────────┐ │
│ │ Execute function calls       │ │
│ │ (_execute_function_calls)    │ │
│ │ - Lookup tool in __tools__   │ │
│ │ - Parse JSON args            │ │
│ │ - Execute async/sync         │ │
│ │ - Return outputs list        │ │
│ │                              │ │
│ │ Persist outputs if enabled   │ │
│ │ Add to status block          │ │
│ │ Extend body.input            │ │
│ └──────────────────────────────┘ │
│ Loop again with tool outputs     │
│ (or break if no tools)           │
│                                  │
│ Return assembled text            │
└──────────────────────────────────┘
```

## Component Descriptions

### Local State Variables (Instead of RequestContext)

**Current Implementation:**
The manifold pipe does NOT use a RequestContext dataclass. Instead, it uses local variables in `_run_streaming_loop()` and `_run_nonstreaming_loop()`:

**Streaming Loop State:**
- `assistant_message: str` - Accumulated response text
- `total_usage: dict` - Aggregated token usage across turns
- `ordinal_by_url: dict[str, int]` - URL → citation number mapping
- `emitted_citations: list[dict]` - Citations already sent to UI
- `status_indicator: ExpandableStatusIndicator` - Manages <details> status blocks

**Non-Streaming Loop State:**
- `assistant_message: str` - Accumulated response text
- `total_usage: dict` - Aggregated token usage
- `reasoning_map: dict[int, str]` - reasoning summary index → text mapping
- `status_indicator: ExpandableStatusIndicator` - Status block manager

**Potential Concurrency Issue:**
These local variables are safe within a single request, but state isolation relies on function scope. Multiple concurrent requests to the same `Pipe` instance are isolated by Python's async execution model (each `pipe()` call gets its own stack frame).

### Pydantic Models

#### CompletionsBody
Validates incoming Open WebUI-style requests (Chat Completions API format).

**Key features:**
- `model_validator` normalizes model IDs and applies aliases
- `extra="allow"` passes through unknown OpenAI parameters

#### ResponsesBody
Represents the OpenAI Responses API request format.

**Key features:**
- `transform_tools()` - Converts __tools__ to Responses API format
- `transform_messages_to_input()` - Converts messages array to input array
- `from_completions()` - Transforms CompletionsBody → ResponsesBody
- `_build_mcp_tools()` - Parses REMOTE_MCP_SERVERS_JSON

### Tool Handling

#### Tool Types Supported
1. **Function tools** - Custom Python functions from __tools__
2. **Web search tool** - OpenAI's built-in web_search_preview
3. **MCP tools** - Remote Model Context Protocol servers
4. **Built-in tools** - file_search, code_interpreter (server-side only)

#### Tool Execution Flow
1. Model requests function_call in output
2. `_execute_function_calls()` called with calls list and __tools__ dict
3. For each call:
   - Lookup tool by name in __tools__
   - Parse arguments JSON
   - Execute async (if coroutine) or sync (via asyncio.to_thread)
   - Return function_call_output with call_id and stringified result
4. Outputs appended to body.input for next turn

**Security Note:** Tools are executed without validation - trusts __tools__ from Open WebUI.

### Persistence System

#### Item Persistence
Stores non-visible response items (reasoning tokens, tool calls) in chat database for reconstruction across turns.

**Storage location:** `chat.openai_responses_pipe.items[item_id]`

**Marker format:** `[openai_responses:v2:{type}:{ulid}]: #`
- Invisible markdown reference-style link
- Embedded in assistant message text
- Parsed on next turn to reconstruct input array

**Item types persisted:**
- `reasoning` - Encrypted reasoning tokens (if PERSIST_REASONING_TOKENS="conversation")
- `function_call` - Tool call details (if PERSIST_TOOL_RESULTS=true)
- `web_search_call` - Web search metadata
- `mcp_call` - MCP tool invocations

#### Model Filtering
Items are only restored if they match the current `openwebui_model_id`. This prevents:
- Reasoning tokens from o4-mini bleeding into gpt-4o context
- Cross-model item contamination

### Session Logging

**SessionLogger class:**
- Uses ContextVars for thread-safe session tracking
- `session_id` - Current session identifier
- `log_level` - Dynamic log level per session
- `logs` - In-memory deque (max 2000 items) per session

**Log levels:**
- Set via valve: LOG_LEVEL (DEBUG/INFO/WARNING/ERROR/CRITICAL)
- User-level override via UserValves
- Logs emitted as citation block on errors if enabled

### Status Indicators

**ExpandableStatusIndicator:**
- Manages a single `<details type="status">` block at message start
- Methods:
  - `add()` - Append new status bullet or sub-bullet
  - `update_last_status()` - Modify most recent bullet
  - `finish()` - Add "Finished in X s" and freeze
- Auto-emits to event_emitter on each update

### HTTP Session Management

**aiohttp.ClientSession:**
- Single shared session for the lifetime of the Pipe instance
- Created lazily in `_get_or_init_http_session()`
- Connection pooling (50 total, 10 per host, 75s keepalive)
- DNS cache (300s TTL)
- Timeout: 30s connect, 3600s read

**Endpoints:**
- `POST /responses` - OpenAI Responses API
- Streaming via SSE (Server-Sent Events)
- Non-streaming via JSON

## Feature Toggles (Valves)

### Connection & Auth
- `BASE_URL` - OpenAI API base URL (supports proxies)
- `API_KEY` - OpenAI API key
- `SERVICE_TIER` - auto/default/flex/priority
- `VERIFY_SSL` - ❌ Not implemented (always True)

### Models
- `MODEL_ID` - Comma-separated model IDs (manifold pattern)

### Reasoning & Summaries
- `REASONING_SUMMARY` - auto/concise/detailed/disabled (requires verified org)
- `PERSIST_REASONING_TOKENS` - disabled/response/conversation

### Tool Execution
- `PARALLEL_TOOL_CALLS` - Allow parallel tool execution
- `MAX_TOOL_CALLS` - Limit total tool calls per response
- `MAX_FUNCTION_CALL_LOOPS` - Limit agent loops (default 10)
- `PERSIST_TOOL_RESULTS` - Store tool calls in chat history

### Web Search
- `ENABLE_WEB_SEARCH_TOOL` - Enable web_search_preview
- `WEB_SEARCH_CONTEXT_SIZE` - low/medium/high
- `WEB_SEARCH_USER_LOCATION` - JSON location object

### Integrations
- `REMOTE_MCP_SERVERS_JSON` - JSON array/object of MCP servers
- `TRUNCATION` - auto/disabled (context window overflow handling)

### Privacy & Caching
- `PROMPT_CACHE_KEY` - id/email (user identifier for caching)

### Logging
- `LOG_LEVEL` - DEBUG/INFO/WARNING/ERROR/CRITICAL

### User Valves
- `LOG_LEVEL` - User-level override (includes INHERIT option)

## Security Considerations

### ⚠️ Missing Security Features
1. **No credential redaction** - API keys not scrubbed from logs
2. **No tool output limits** - Could cause memory exhaustion
3. **No input validation** - Tool arguments parsed without checks
4. **No SSL verify valve** - Cannot disable for enterprise proxies
5. **No request timeout** - Relies on httpx default
6. **No stream timeout** - Hanging streams not detected

### ✅ Security Positives
1. **No code execution** - No eval/exec/subprocess
2. **Pydantic validation** - Request bodies validated
3. **Tool isolation** - Tools from trusted __tools__ only
4. **Model-specific persistence** - Cross-model item filtering
5. **Session isolation** - ContextVars for thread safety

## Error Handling

### Connection Errors
- ❌ **No retry logic** - Failures are fatal
- ❌ **No backoff** - Immediate failure on connection errors
- ✅ **Error logging** - Logged via SessionLogger

### API Errors
- ✅ **Logged with redaction** - Errors logged via self.logger
- ⚠️ **Raw errors to user** - No sanitization for user display
- ✅ **Optional log citation** - Can emit logs as citation block

### Tool Execution Errors
- ✅ **Try/catch per tool** - Exceptions caught and stringified
- ✅ **Continue on failure** - Other tools still execute
- ⚠️ **No timeout** - Tools can hang indefinitely

## Async Architecture

**Key Patterns:**
- `aiohttp.ClientSession` for HTTP requests
- `async for event in stream` for SSE parsing
- `asyncio.gather()` for parallel tool execution
- `asyncio.to_thread()` for sync tool wrapping
- `inspect.iscoroutinefunction()` to detect async tools

**Not Used:**
- ❌ `AsyncOpenAI` client (uses raw aiohttp instead)
- ❌ `httpx.AsyncClient` (uses aiohttp)

## Model Support

### GPT-5 Series
- `gpt-5`, `gpt-5-mini`, `gpt-5-nano`
- `gpt-5-chat-latest`, `gpt-5-auto` (router)
- `gpt-5-thinking`, `gpt-5-thinking-minimal`, `gpt-5-thinking-high`
- ❌ `gpt-5.1`, `gpt-5-codex` not yet listed in FEATURE_SUPPORT

### GPT-4.1 Series
- `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`

### GPT-4o Series
- `gpt-4o`, `gpt-4o-mini`
- `chatgpt-4o-latest`

### o-series (Reasoning Models)
- `o3`, `o3-mini`, `o3-pro`
- `o4-mini`, `o4-mini-high` (alias)
- `o3-deep-research`, `o4-mini-deep-research` (WIP)

### Model Aliasing
- `o3-mini-high` → `o3-mini` + reasoning_effort="high"
- `o4-mini-high` → `o4-mini` + reasoning_effort="high"
- `gpt-5-thinking-high` → `gpt-5` + reasoning_effort="high"
- etc.

## Maintenance Notes

**When updating this file:**
1. Review after changes to streaming loop logic
2. Update data flow if new event types added
3. Verify state variable list matches implementation
4. Check that valve descriptions are current
5. Update model support list for new OpenAI releases
6. Document new persistence item types
7. Review security considerations section

**Related Files:**
- [openai_responses_manifold.py](openai_responses_manifold.py) - Main implementation
- [../../CLAUDE.md](../../CLAUDE.md) - Project-wide developer guide (if exists)

---

**Generated:** 2025-11-16
**Pipeline Version:** 0.8.28
**Responses API:** OpenAI GPT-5, o-series, GPT-4.1, GPT-4o
**Author:** Justin Kropp (github.com/jrkropp)
