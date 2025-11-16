> **Note:** Keep this workpackage current. Check off tasks as they’re completed and add subtasks when new work is discovered.

## Checklist
- [ ] Introduce `SessionLogger.scoped_context` and `SessionLogger.get_logger`, update call sites to prevent leaked context
- [ ] Require `RequestContext` in `build_responses_request`, remove loose kwargs, add regression tests
- [ ] Consolidate duplicated HTTP request code inside `ResponsesClient` and retain structured logging
- [ ] Add TypedDicts/constants for tool calls, markers, and stream frames; update modules to use them
- [ ] Tidy miscellaneous quality issues (magic strings, dead TYPE_CHECKING blocks, redundant helpers)
- [ ] Document the refactors and run `make test` / `make build`

---

# Workpackage: Code Quality Refinements for OpenAI Responses Manifold

## 0. Background

The bundled manifold code is functionally solid but several internals create long-term maintenance hazards:

- `SessionLogger.bind_context` is used without ever resetting, so metadata can leak between requests in a persistent worker.
- `build_responses_request` accepts both a `RequestContext` object *and* loose keyword arguments; only the `RequestContext` path is actually exercised, which increases the chance of drift or misuse.
- `ResponsesClient.stream` and `.invoke` duplicate nearly identical HTTP setup, logging, and error handling code.
- Tool calls, marker segments, and SSE frames are treated as loose `dict` objects everywhere, making refactors risky and hiding typos.
- Magic strings (event types), dead `TYPE_CHECKING` blocks, and trivial pass-through helpers add noise.

Addressing these issues yields better correctness (no logger context bleed), readability (clearer APIs), and future refactor safety.

## 1. Requirements

1. **Scoped session logging with shared logger helper**
   - Add a context manager (e.g., `SessionLogger.scoped_context`) that binds metadata and automatically resets it.
   - Provide a `SessionLogger.get_logger(name: str | None = None)` helper so modules stop calling `logging.getLogger(__name__)` directly; this keeps logging configuration centralized.
   - Update `pipe.pipe` (and other places that manipulate context) to use the scoped helper to avoid leakage.

2. **Simplified Responses request builder**
   - Change `build_responses_request` to require a `RequestContext` parameter; remove the optional `chat_id`, `model_id`, `truncation`, and `user_identifier` kwargs plus the “if context is None” branch.
   - Ensure the API is harder to misuse by having a single path; update all call sites.
   - Add focused unit tests exercising:
     - Unsupported fields removal (e.g., `max_tokens`, `reasoning_effort`),
     - System prompt → `instructions`,
     - Marker-driven assistant message reconstruction,
     - Alias defaults merging (if applicable).

3. **DRY HTTP client**
   - Introduce a private helper (e.g., `_post`) inside `ResponsesClient` that handles session creation, headers, payload serialization, request summaries, and error logging scaffolding.
   - Refactor both `stream` and `invoke` to call that helper while preserving existing logging, timers, and error cases.
   - Confirm that exception handling (including request-id extraction and error body logging) remains instrumented.

4. **Typed shapes for tools, markers, and frames**
   - Define `TypedDict`s for function call payloads (`FunctionCall`, `FunctionCallOutput`), marker/text segments, and streaming frames to codify the expected keys.
   - Update `tools.py`, `markers.py`, `adapters.py`, and `runner.py` signatures to reference these types. This should remain backward-compatible (still accept dicts) but improves editor/mypy help.
   - Add constants for repeated event type strings (e.g., `RESPONSE_OUTPUT_DELTA = "response.output_text.delta"`) to reduce typo risk.

5. **Cleanups & docs**
   - Remove unused `TYPE_CHECKING` blocks and redundant helpers (e.g., `split_assistant_segments` if it simply calls `split_text`).
   - Ensure sensitive data masking helpers are used consistently in any new/updated logs.
   - Capture these refactors in README / docs sections as appropriate so future contributors understand the conventions.

## 2. Deliverables

1. Updated `session.py`, `pipe.py`, and related modules using the scoped logging helpers and shared logger creation.
2. Refactored `build_responses_request` API plus associated unit tests (likely in `tests/test_adapters.py` or a new dedicated test file).
3. `ResponsesClient` implementation that reuses a private `_post` helper (or equivalent) without behavior regressions.
4. TypedDict definitions and constant modules applied across tools/adapters/runner/markers.
5. Documentation update within `README.md` (or `docs/CHANGELOG.md`) summarizing the internal API changes and developer impact.
6. Passing `make test` and `make build`, recorded in the PR description or CI logs.

## 3. Suggested Plan

1. **Session logging scope**
   - Implement `SessionLogger.scoped_context` and `get_logger`.
   - Update modules to import and use `SessionLogger.get_logger` instead of `logging.getLogger`.
   - Apply the scoped context around `pipe.pipe` (and other long-lived context bindings). Add regression coverage if feasible.

2. **Request builder API**
   - Refactor `build_responses_request`; update `pipe.py` and any tests/fixtures.
   - Augment unit tests to capture expected transformations.

3. **Responses client cleanup**
   - Introduce `_post` helper; refactor `stream` and `invoke`.
   - Verify behavior manually (diff logs, ensure SSE parsing unaffected).

4. **Typed shapes**
   - Create a small `typing.py` (or similar) module housing the new TypedDicts/constants.
   - Update `tools.py`, `adapters.py`, `runner.py`, etc., to import and use these definitions.
   - Run mypy/ruff (if enabled) to ensure no regressions.

5. **Polish & validation**
   - Remove redundant helpers and dead code blocks.
   - Update documentation to mention the scoped logger + typed shapes.
   - Run `make test` and `make build`, ensuring bundle regeneration succeeds.

## 4. Acceptance Criteria

- Logger context is scoped per request; no metadata leakage occurs when running multiple requests sequentially.
- `build_responses_request` exposes a single, `RequestContext`-driven API and passes the new tests.
- `ResponsesClient` no longer duplicates HTTP setup code, yet still logs request summaries, timings, and error bodies.
- Tool execution, marker parsing, and streaming frame handling rely on the new TypedDicts/constants without introducing runtime regressions.
- Documentation reflects the new internal conventions, and CI commands (`make test`, `make build`) pass locally.
