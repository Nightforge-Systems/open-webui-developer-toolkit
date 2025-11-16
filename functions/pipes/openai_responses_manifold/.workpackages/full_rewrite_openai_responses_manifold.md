> **Note:** Keep this workpackage up to date. When you discover new gaps, add tasks and checkboxes so future agents can continue where you left off.

## Checklist
- [ ] Phase 1 – Define Target Architecture & Dependencies
- [ ] Phase 2 – Implement the Modular Source Tree
- [ ] Phase 3 – Build Script & Artifact Verification
- [ ] Phase 4 – Comprehensive Test Suite & CI Harness
- [ ] Phase 5 – Documentation & Developer Ergonomics

---

# Workpackage: Complete Rewrite of the OpenAI Responses Manifold

## 0. Objective

Rebuild the OpenAI Responses manifold from the ground up so it reads like a familiar OpenAI SDK / Open WebUI integration. The current monolith borrows heavily from bespoke patterns (legacy shims, nested helpers, ambiguous naming) which makes the code harder to maintain and test. We want a clean, typed, modular package inside `src/` with conventional terminology, deterministic tests, and a single `build.py` that produces the checked-in artifact.

## 1. Architectural Goals

1. **SDK-like client**: A dedicated `client.py` (or `api.py`) wrapping `AsyncOpenAI` with typed request/response DTOs (`ResponsesRequest`, `ResponsesStreamEvent`). No legacy helper methods on `Pipe`. All dependencies used by this client (e.g., `aiohttp`) must be listed in `manifest.py` under the `requirements:` key so Open WebUI installs them automatically.
2. **Clear separation of concerns**:
   - Keep `valves.py` (matches Open WebUI terminology) for runtime configuration and user overrides.
   - `models.py` (rename `schemas`) for all Pydantic data structures; use `ConfigDict` instead of `Config`.
   - `adapters.py` strictly handles OWUI ↔ OpenAI payload conversions.
   - `runner.py` (rename `engine`) orchestrates streaming/batch runs; tests focus on event handling.
   - `router.py`, `tools.py`, `persistence.py`, `emitters.py`, `logging.py` each with narrow interfaces.
3. **Dependency Injection**: The `Pipe` constructor wires together the pieces (client, router, persistence, event emitters). Avoid global lookups or monkeypatch-friendly shims.
4. **No legacy compatibility**: Remove `_run_streaming_loop`, `send_openai_responses_*`, `ResponsesBody.transform_owui_tools`, and other backward compatibility hooks.
5. **Build artifact**: `build.py` concatenates modules in a deterministic order, stripping local imports. The generated `openai_responses_manifold.py` should just import from those bundled sections.

## 2. Phase Plan & Tasks

### Phase 1 – Define Target Architecture & Dependencies
- [ ] Document the desired module layout (client, config, models, adapters, router, runner, persistence, emitters, logging utilities, pipe entrypoint, build script).
- [ ] Decide on the dependency injection pattern (e.g., `ResponsesManifold` dataclass that accepts `client`, `router`, `persistence`).
- [ ] Specify third-party requirements (aiohttp, httpx for testing, pydantic v2). Capture them in `pyproject.toml` or `requirements-dev.txt`.

### Phase 2 – Implement the Modular Source Tree
- [ ] Create new modules under `src/` following the architecture (rename existing files or start clean). Write or update the relevant unit tests as you complete each module and ensure `pytest` passes before starting the next one.
- [ ] Move each responsibility into its module using standard naming:
  - `client.py`: `ResponsesClient`, `ResponsesStream`.
  - `config.py`: `ManifoldConfig`, `UserOverrides`, `merge_config`.
  - `models.py`: `CompletionsRequest`, `ResponsesRequest`, `RunEvent`, etc.
  - `adapters.py`: pure functions for converting OWUI messages to OpenAI input and SSE frames to `RunEvent`.
  - `router.py`: `GPT5Router` with a `route()` method returning `{model, reasoning_defaults}`.
  - `runner.py`: `ResponseRunner` that consumes `RunEvent` streams, persists markers, emits UI events.
  - `persistence.py`: DB interactions (marker store/fetch) with portable interfaces for testing (e.g., allow injecting a fake backend).
  - `tools.py`: `ToolRegistry`, `build_tool_specs`, `run_function_calls`.
  - `emitters.py`: typed event helpers.
  - `logging.py`: `SessionLogger`.
  - `manifold.py`: top-level `ResponsesManifold` (formerly `Pipe`) hooking everything together.
- [ ] Remove bespoke global helpers, inline CSS injection (if still required) into a dedicated method with clear documentation.

### Phase 3 – Build Script & Artifact Verification
- [ ] Update `build.py` to reflect the new module order and import names. Ensure it strips `from .` imports and `__future__` duplication.
- [ ] Run `python build.py` and ensure `openai_responses_manifold.py` matches (no local diffs).
- [ ] Consider adding a `scripts/verify-build.sh` or Make target to automate `python build.py && git diff --exit-code`.

### Phase 4 – Comprehensive Test Suite & CI Harness
- [ ] Rewrite tests to target the modular code directly:
  - `tests/test_adapters.py`: markers, system instructions, user/developer messages.
  - `tests/test_router.py`: GPT-5 routing logic with stubbed responses.
  - `tests/test_tools.py`: strict schema enforcement, web search gating, MCP merging.
  - `tests/test_runner.py`: streaming event handling (TextDelta, ReasoningSummary, tool outputs, errors).
  - `tests/test_persistence.py`: marker persistence/fetching with an in-memory fake.
  - `tests/test_pipe.py`: end-to-end smoke test using a mocked `ResponsesClient`.
- [ ] Use pytest fixtures for `ResponsesRequest`, `ManifoldConfig`, and stub clients to keep tests small and deterministic.
- [ ] Ensure tests run inside `.venv` (`.venv/bin/pytest`) with coverage support. The default command should pass without needing real OpenAI creds.

### Phase 5 – Documentation & Developer Ergonomics
- [ ] Update `AGENTS.md` to reflect the new architecture, naming, and workflow (edit `src/` only, run tests, run `build.py` last).
- [ ] Refresh `README.md` (or add a `docs/manifold.md`) describing the pipeline in developer-friendly terms: config flow, router, runner, persistence, testing instructions.
- [ ] Ensure `refactor_openai_responses_manifold.md` references point to this workpackage (or mark the old one as deprecated).

## 3. Acceptance Criteria

- The modular source tree uses standard naming and dependency injection; no legacy helper methods remain.
- `openai_responses_manifold.py` is fully generated from `src/` via `build.py`, and git shows no differences after running the build.
- The new pytest suite covers adapters, router, tools, runner, persistence, and the top-level pipe without needing to monkeypatch generated artifacts.
- Documentation (`AGENTS.md` + README or docs) explains the new architecture, build steps, and testing workflow so contributors familiar with the OpenAI SDK/Open WebUI can navigate quickly.
- CI (or local verification) runs `python -m pytest` inside the venv and `python build.py`; both must succeed.
