# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Open WebUI Developer Toolkit** - Reusable extensions (pipes, filters, tools) for Open WebUI, a self-hosted AI interface platform.

**Tech Stack**: Python 3.11+, FastAPI, Pydantic v2, httpx/aiohttp

**Repository Purpose**: Provides production-ready components including OpenAI Responses API integration, advanced function calling, web search tools, visible reasoning traces, and citation support.

## Essential Commands

### Testing & Quality Assurance

```bash
# Run all checks (recommended - runs lint + tests)
nox

# Run tests with coverage
pytest -vv --cov=functions --cov-report=term-missing

# Lint and auto-fix issues
ruff check --fix functions tools .tests .scripts

# Run pre-commit hooks manually
pre-commit run --all-files
```

### Deployment

```bash
# Upload/update a pipe, filter, or tool to Open WebUI instance
python .scripts/publish_to_webui.py <file.py> \
  --type {pipe|filter|tool} \
  --url http://localhost:8080 \
  --key YOUR_API_KEY
```

## Architecture Overview

### Extension Types

**Pipes** (`functions/pipes/`):
- Transform or generate chat messages
- Call external APIs (e.g., OpenAI Responses API)
- Stream responses to UI in real-time
- Example: `openai_responses_manifold.py` (2,116 lines, main featured pipe)

**Filters** (`functions/filters/`):
- Pre-process requests (`inlet`) or post-process responses (`outlet`)
- **Critical**: Inlet body structure differs from outlet body structure!
- Can modify messages, inject tools, route to different models
- Examples: `reason_toggle_filter`, `web_search_toggle_filter`

**Tools** (`tools/`):
- Provide new abilities to the assistant (function plugins)
- Invoked by models during conversations

### Critical Architectural Concepts

#### 1. Persistence via Invisible Markdown Markers

The manifold pipe uses invisible markdown reference links to store metadata in assistant messages:

```markdown
[openai_responses:v2:<type>:<ulid>?model=<model>]: #
```

These markers are embedded in responses but don't render in the UI. Full payloads are stored in the chat database at `chat.openai_responses_pipe.items[item_id]`. Types include: `function_call`, `web_search_call`, `mcp_call`, `reasoning`.

#### 2. Event System

Two event helpers available in pipe/filter functions:

- **`__event_emitter__`**: Fire-and-forget broadcast to all user sessions
- **`__event_call__`**: Request/response pattern (waits for user interaction)

Supported event types:
```python
# Status updates
await __event_emitter__({"type": "status", "data": {"description": "Processing...", "done": False}})

# Streaming text
await __event_emitter__({"type": "chat:message:delta", "data": {"content": "chunk"}})

# Citations
await __event_emitter__({"type": "source", "data": {"source": {"name": "NASA"}, ...}})

# User confirmation (awaitable)
confirmed = await __event_call__({"type": "confirmation", "data": {"title": "Confirm", "message": "Proceed?"}})
```

#### 3. Responses API vs Chat Completions API

**Key Difference**: OpenAI's Responses API has a different structure than Chat Completions API.

```python
# Chat Completions (Open WebUI default)
{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "hi"}],
    "tools": [...]
}

# Responses API (what manifold uses)
{
    "model": "gpt-4o",
    "instructions": "System prompt here",
    "input": [
        {"role": "user", "content": [{"type": "input_text", "text": "hi"}]}
    ],
    "tools": [...]  # Different format!
}
```

The manifold pipe performs this transformation in `ResponsesBody.from_completions()`.

### OpenAI Responses Manifold Pipeline Flow

```
1. ENTRY POINT: pipe()
   ↓
2. REQUEST TRANSFORMATION (CompletionsBody → ResponsesBody)
   - Normalize model IDs, handle aliases
   - Convert messages to Responses API format
   - Extract system prompt → instructions
   ↓
3. FEATURE DETECTION
   - Check model capabilities (FEATURE_SUPPORT dict)
   - Detect task model (title generation)
   - Map verbosity directives ("Add Details" → text.verbosity)
   ↓
4. TOOL ASSEMBLY
   - Transform __tools__ to Responses API format
   - Deduplicate tools (later wins)
   - Add web_search_preview if enabled
   - Append remote MCP servers
   ↓
5. REASONING & PERSISTENCE CONFIG
   - Enable reasoning summary (auto/concise/detailed)
   - Request encrypted reasoning tokens
   - Set service_tier, max_tool_calls
   ↓
6. STREAMING/NON-STREAMING LOOP
   - Send aiohttp POST to /responses
   - Parse SSE events or JSON response
   - Handle: output_text.delta, reasoning_summary_text.done, annotation.added (citations), output_item.done (tool calls)
   - Execute function calls
   - Emit events to frontend
   - Loop until complete
```

**State Management**: Currently uses local variables in loop methods. **Future enhancement**: Migrate to RequestContext dataclass for thread-safe per-request state isolation (see `proposed_feature_ports.md`).

**Detailed Architecture**: See [PIPELINE_ARCHITECTURE.md](functions/pipes/openai_responses_manifold/PIPELINE_ARCHITECTURE.md)

## Development Patterns

### Pipe Function Signature

```python
async def pipe(
    self,
    body: dict[str, Any],           # Request payload (stream, model, messages, tools)
    __user__: dict[str, Any],       # User info (id, email, name, role, valves)
    __request__: Request,           # FastAPI Request object
    __event_emitter__: Callable,    # Event broadcaster
    __event_call__: Callable,       # Event request/response
    __files__: list[dict],          # Uploaded file metadata
    __metadata__: dict[str, Any],   # chat_id, message_id, session_id, features, variables
    __tools__: dict[str, Any],      # Tool definitions keyed by name
) -> AsyncIterator[str]:
```

**Key body fields**:
- `body.stream` - Whether to stream response
- `body.model` - Model ID (e.g., `"openai_responses.gpt-4.1"`)
- `body.messages` - Chat history `[{role, content}, ...]`
- `body.tools` - Tool definitions (only present if native function calling enabled)

**Metadata features**:
- `__metadata__.task` - Task name if background task (e.g., `"title_generation"`)
- `__metadata__.features` - Toggles: `image_generation`, `web_search`, `code_interpreter`
- `__metadata__.variables` - Placeholders: `{{CURRENT_DATE}}`, `{{USER_NAME}}`, etc.

### Versioning & Changelog

**From [AGENTS.md](AGENTS.md)**:

- Use semantic versioning: `MAJOR.MINOR.PATCH`
- Update `CHANGELOG.md` when modifying pipes
- **Only bump version once per day** (group same-day changes)
- Documentation-only edits don't require version bump
- Update feature tables in README when adding capabilities (include `Last updated` date)

### Testing Patterns

**Common test patterns** (from `.tests/test_openai_responses_manifold.py`):

1. **Marker roundtrip tests** - Validate persistence system:
```python
def test_marker_roundtrip():
    marker = mod.create_marker("function_call", ulid="...", model_id="...")
    wrapped = mod.wrap_marker(marker)
    assert mod.contains_marker(wrapped)
    parsed = mod.parse_marker(marker)
    assert parsed["metadata"]["model"] == "gpt-4o"
```

2. **Dummy fixtures** - In-memory storage for test isolation:
```python
@pytest.fixture()
def dummy_chats(monkeypatch):
    storage: dict[str, dict] = {}
    # ... mock Chats class ...
    monkeypatch.setattr(mod, "Chats", DummyChats)
```

3. **Pydantic validation tests** - Schema transformation:
```python
def test_transform_tools_and_mcp():
    tools = [...]
    out = mod.ResponsesBody.transform_tools(tools, strict=True)
    assert {t.get("name") for t in out} == {"add", "web_search"}
```

## Active Development Context

### Feature Porting Project

**Current Branch**: `nf-feature-port`

**Goal**: Port production-ready features from `temp/nightforge_agent_pipe.py` into `openai_responses_manifold.py`

**Roadmap**: See [proposed_feature_ports.md](functions/pipes/openai_responses_manifold/proposed_feature_ports.md)

**Priority Features**:
1. **RequestContext dataclass** - Centralized per-request state management (prevents concurrency issues)
2. **AsyncOpenAI client** - Use official SDK instead of raw aiohttp (type-safe events, built-in retry)
3. **Connection retry logic** - Exponential backoff for transient errors (connection reset, incomplete reads, HTTP 429/503)
4. **Stream timeout protection** - Detect stalled streams via activity tracking
5. **Credential redaction** - PII/secrets hygiene in logs (regex patterns for API keys, tokens, passwords)
6. **MCP tool execution** - Local MCP tool invocation via Open WebUI's MCPClient
7. **Tool output limits** - Prevent token overflow (MAX_TOOL_OUTPUT_CHARS = 50000)

**Comparison**: See `temp/nightforge_vs_manifold_comparison_report.md` for detailed feature differences

### Branching Model

Three-branch strategy:
- **`development`** → Active development (unstable, may be broken)
- **`alpha-preview`** → Release candidate (2-3 week QA period)
- **`main`** → Stable, production-ready

### CI/CD

**GitHub Actions**:
- **Weekly sync**: Updates `external/open-webui/` with upstream (Mondays 07:00 UTC)
- **Plugin deployment**: Auto-deploys changed pipes/filters/tools on push to tracked branches

## Model Support (Manifold Pipe)

**GPT-5 Family**:
- `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-5-pro`, `gpt-5.1`, `gpt-5.1-codex`
- `gpt-5-chat-latest` (auto-routing)

**GPT-4.1 Series**:
- `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`

**GPT-4o Series**:
- `gpt-4o`, `gpt-4o-mini`, `chatgpt-4o-latest`

**O-series**:
- `o3`, `o3-mini`, `o3-pro`, `o4-mini`

**Pseudo-Aliases** (map to base models with reasoning effort):
- `gpt-5-thinking`, `gpt-5-thinking-minimal`, `gpt-5-thinking-high`
- `gpt-5.1-thinking`, `gpt-5.1-thinking-minimal`, `gpt-5.1-thinking-high`
- `o3-mini-low`, `o3-mini-medium`, `o3-mini-high`
- `o4-mini-low`, `o4-mini-medium`, `o4-mini-high`
- `codex` (alias for `gpt-5.1-codex`)

Aliases map `(model_id, reasoning_effort)` to pseudo-model names for UI convenience.

## Integration with Open WebUI

**Imports from `external/open-webui/backend`**:
```python
from open_webui.models.chats import Chats          # Chat persistence
from open_webui.models.models import Models        # Model config
from open_webui.socket.main import get_event_emitter  # Event system
from open_webui.utils.mcp.client import MCPClient  # MCP integration (experimental)
```

**External directory**: Read-only copy of upstream Open WebUI source, auto-synced weekly.

## Key Files Reference

**Must-Read Documentation**:
- [README.md](README.md) - Project overview
- [docs/pipe_input.md](docs/pipe_input.md) - Pipe input structure reference
- [docs/events.md](docs/events.md) - Event system guide
- [docs/citations.md](docs/citations.md) - Citation system patterns
- [functions/pipes/openai_responses_manifold/PIPELINE_ARCHITECTURE.md](functions/pipes/openai_responses_manifold/PIPELINE_ARCHITECTURE.md) - Detailed architecture
- [functions/pipes/openai_responses_manifold/proposed_feature_ports.md](functions/pipes/openai_responses_manifold/proposed_feature_ports.md) - Feature porting roadmap

**Critical Implementation Files**:
- [functions/pipes/openai_responses_manifold/openai_responses_manifold.py](functions/pipes/openai_responses_manifold/openai_responses_manifold.py) - Main pipe (2,116 lines)
- [.tests/test_openai_responses_manifold.py](.tests/test_openai_responses_manifold.py) - Main test suite
- [temp/nightforge_agent_pipe.py](temp/nightforge_agent_pipe.py) - Reference implementation for porting features

**Tooling**:
- [.scripts/publish_to_webui.py](.scripts/publish_to_webui.py) - Deployment script
- [pyproject.toml](pyproject.toml) - Project config (dependencies, test settings)
- [noxfile.py](noxfile.py) - Task runner config

## Common Development Workflows

### Creating a New Pipe

1. Create directory: `functions/pipes/my_pipe/`
2. Create file: `my_pipe.py` with class name `Pipe`
3. Implement required methods: `__init__()`, `pipe()`
4. Add valves for user configuration (optional)
5. Write tests in `.tests/test_my_pipe.py`
6. Run `nox` to verify
7. Deploy: `python .scripts/publish_to_webui.py functions/pipes/my_pipe/my_pipe.py --type pipe --url $URL --key $KEY`

### Updating the Manifold Pipe

1. Make changes to `openai_responses_manifold.py`
2. Update version number (semantic versioning)
3. Update `CHANGELOG.md` with changes
4. Run tests: `pytest -vv`
5. Run linter: `ruff check --fix`
6. Commit with descriptive message
7. Deploy to test instance for validation

### Running a Single Test

```bash
# Run specific test function
pytest .tests/test_openai_responses_manifold.py::test_marker_roundtrip -vv

# Run specific test class
pytest .tests/test_openai_responses_manifold.py::TestResponsesBody -vv

# Run with keyword match
pytest -k "marker" -vv
```

## Important Notes

- **Filter inlet vs outlet**: Body structure differs! Inlet receives request body, outlet receives different response structure. See `functions/filters/README.md` for examples.

- **Persistence markers**: Always use helper functions (`create_marker`, `wrap_marker`, `parse_marker`) rather than manual string construction.

- **Event auto-persistence**: Events of type `status`, `message`, and `replace` are automatically saved to DB to prevent data loss on disconnect.

- **MCP integration**: Currently experimental. Production-ready MCP execution is in development (porting from nightforge).

- **Reasoning tokens**: When `PERSIST_REASONING_TOKENS="conversation"`, reasoning is persisted across turns for caching (50-75% cost reduction on follow-up queries).

- **Tool output limits**: Always validate tool outputs don't exceed token limits. Truncate if necessary (MAX_TOOL_OUTPUT_CHARS pattern from nightforge).
