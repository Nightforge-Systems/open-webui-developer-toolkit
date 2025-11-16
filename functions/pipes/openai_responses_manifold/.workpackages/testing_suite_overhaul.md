> **Note:** Keep this workpackage updated. Check off tasks as they finish and add subtasks when new work surfaces.

## Checklist
- [x] Capture the manifold’s behavioral contract before writing tests
- [x] Build reusable test fixtures (fake Responses client, spy emitter, in-memory Chats stub)
- [x] Add scenario/integration tests covering streaming, routing, tools, persistence, errors
- [x] Expand module/unit coverage (request shaping, tool builder, valves, persistence, logging)
- [x] Document the new testing infrastructure and how to extend it
- [x] Ensure `make test`/`make build` run the revamped suite

---

# Workpackage: Rebuild the OpenAI Responses Manifold Test Suite

## 0. Background

The current tests focus on a few helpers (Completions→Responses conversion, markers/persistence, and a thin pipe smoke test). As the manifold has grown—routing decisions, streaming orchestration, tool execution, persistence, and logging guarantees—the suite no longer reflects the actual behavior we rely on. Bugs that slip through usually involve orchestrator logic or valve-controlled side effects that existing tests never exercise.

We need a comprehensive, behavior-driven test suite that validates the entire manifold pipeline, not just isolated helpers. This requires reusable fakes and fixtures so tests can simulate Responses API streams, router outputs, persistence, and log flushing without hitting the network or real databases.

## 1. Goals

1. **Scenario coverage:** End-to-end tests that drive `ResponseRunner`/`Pipe` with scripted events to assert real Open WebUI event flows (status → chat messages → completion, tool loops, cancellations, errors).
2. **Feature validation:** Tests proving router decisions, web search toggles, remote MCP tool injection, verbosity directives, and valve merge logic work across representative inputs.
3. **Persistence & logging guarantees:** Ensure tool outputs persist via markers and are fetched in subsequent requests, and that SessionLogger flushes per-session logs even on failures.
4. **Extensible infrastructure:** Provide fixtures (fake Responses client, spy event emitter, in-memory `Chats` stub) documented for future contributors, keeping tests fast and deterministic.
5. **CI-ready:** `make test`/`make build` must execute the new suite reliably; prefer asyncio-friendly patterns and avoid real network calls.

## 2. Deliverables

1. **Testing infrastructure**
   - `tests/fakes.py` (or similar) with `FakeResponsesClient`, `SpyEventEmitter`, `InMemoryChats`.
   - Pytest fixtures in `tests/conftest.py` wiring the fakes, default valves, metadata factories, and ensuring `SessionLogger` context resets per test.

2. **Scenario tests**
   - `tests/test_runner_scenarios.py` (name tbd) containing:
     * Happy-path streaming: status updates, deltas, completion, usage.
     * Function-call loop: model emits tool call, local tool executes, outputs fed back.
     * Router success/failure: verifying status messages, model mutation, reasoning effort updates.
     * Web search + remote MCP toggles via valves/features.
     * Error/cancel flows ensuring `_emit_error`, log citations, single completion emission.
     * Task-mode request returning aggregated output.

3. **Module/unit tests**
   - Expanded coverage for:
     * `ResponsesBody.from_completions` (developer role, multimodal user content, markers round-trip).
     * `build_tools` (strict schema conversion, JSON validation, dedupe, remote MCP).
     * Valve merge logic + LOG_LEVEL resolution order.
     * Persistence helpers (markers created/fetched, reasoning token include toggles).
     * Session logging (log level inheritance, per-session flush).

4. **Documentation updates**
   - README or `/docs` note describing the new testing approach, available fixtures, and how to add scenario tests.
   - Mention in AGENTS/workpackage progress if relevant.

5. **CI confirmation**
   - Demonstrate `make test` and `make build` succeeding locally with the new suite.

## 3. Suggested Plan

1. **Map behaviors**: Write down the manifold contract (inputs → outputs, valve effects, event expectations). Use it to prioritize scenario tests.
2. **Build fakes/fixtures**: Implement fake client/emitter/Chats stubs and pytest fixtures. Ensure they’re well-documented.
3. **Write scenario tests**: Start with the happy path, then add loops, router, web search, errors, and task-mode cases.
4. **Augment module tests**: Cover remaining helpers/valve logic, persistence, and logging.
5. **Document + polish**: Update README/docs, adjust workpackages, and keep fixtures easy to extend.
6. **Run CI commands**: `make test`, `make build`, and iterate until green.

## 4. Acceptance Criteria

- Scenario tests capture the primary behaviors of the manifold.
- Module-level tests cover remaining helpers and edge cases.
- Fixtures/fakes keep tests fast and deterministic; docs explain their usage.
- Session logging/persistence guarantees are validated.
- CI commands (`make test`, `make build`) pass with the new suite.

---

**Status: Completed (tests/fakes.py + new scenario/unit suites, README updates, `make test`/`make build` verification).**
