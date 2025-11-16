> **Note:** Keep this workpackage current. Check off tasks as they’re completed and add subtasks when new work appears.

## Checklist
- [x] Audit current logging coverage to identify missing context (router, HTTP client, tools, adapters, persistence)
- [x] Define consistent logging levels and metadata payload (session id, chat id, model id)
- [x] Add structured/contextual logging across modules (INFO for milestones, DEBUG for detailed payloads, WARN/ERROR for failures)
- [x] Enhance error logging with OpenAI HTTP details and internal failure causes
- [x] Surface tool execution/logging (inputs/outputs with masking) and router decisions
- [x] Add tests asserting log content for success and failure scenarios
- [x] Document logging behavior, configuration knobs (LOG_LEVEL), and expected output

---

# Workpackage: Enhance Logging for OpenAI Responses Manifold

## 0. Background

Current logging is minimal: the runner emits a “Starting/Completed” INFO pair, and errors often result in a generic “Uh-oh!” message with a sparse Logs citation (e.g., HTTP 400 without context). Developers and users need richer diagnostics to understand why a request failed (routing issues, OpenAI errors, tool misfires, valve misconfiguration).

The goal is to provide contextual, consistent logging across all phases (request build, routing, OpenAI I/O, tool execution, persistence) so that setting a valve’s `LOG_LEVEL` to INFO/DEBUG produces actionable Logs citations.

## 1. Requirements

1. **Consistent logging style**
   - Use standard Python logging via the existing `SessionLogger` infrastructure; no bespoke print statements.
   - Every log record should include session-aware metadata: session_id (already injected), plus structured fields (model_id, chat_id) when relevant.

2. **Coverage across components**
   - `pipe.py`: log merged valves (without secrets), router decisions, request dispatch, and final status (success/failure).
   - `router.py`: log when routing is attempted, what decision came back, errors parsing router output.
   - `client.py`: log outgoing requests (masked payloads), HTTP status codes, response timings, and error bodies when exceptions occur.
   - `runner.py`: log state transitions (thinking phases, tool loops, persistence hits), tool execution results, and reasons for early termination.
   - `tools.py` / `adapters.py` / `persistence.py`: log warnings when inputs are malformed, fields dropped, or persistence fails.

3. **Actionable error logs**
   - When an HTTP call fails, capture: status code, endpoint, request id (if provided), and OpenAI error payload.
   - When a `response.error` frame arrives, log the error type, code, and message.
   - When local tool execution raises, log the exception + call args (mask sensitive data).

4. **Configurable detail**
   - INFO level: key milestones and failures (high signal, low volume).
   - DEBUG level: structured payloads (request/response snippets, tool args/results), optional toggles for subsystems if needed.
   - Consider valve extensions (e.g., `LOG_DETAIL`) if finer-grained control is required.

5. **Mask sensitive data**
   - Ensure API keys, user identifiers, and large payloads are redacted/truncated in logs.

6. **Testing**
   - Add tests that simulate success, OpenAI 4xx/5xx, router failure, and tool failure; assert the buffered Logs citation contains the expected context lines.
   - Tests should respect masking behavior.

7. **Documentation**
   - README/workpackage should explain how logging works, how to adjust `LOG_LEVEL`, and provide sample outputs for INFO vs DEBUG to guide users.

## 2. Deliverables

1. **Logging enhancements across modules** per requirements above, using consistent helper functions where appropriate (e.g., `log_request_summary`, `log_openai_error`).
2. **Updated tests** in `tests/test_runner.py` (and/or new files) covering log output for typical failure modes.
3. **Documentation updates**: README section describing logging configuration, sample Logs citation, and best practices (e.g., set LOG_LEVEL=DEBUG when debugging).
4. **Verified build**: `cd functions/pipes/openai_responses_manifold && source .venv/bin/activate && make build`.

## 3. Suggested Plan

1. **Survey current logging** to identify lacking areas and decide on log message templates.
2. **Implement helper utilities** (e.g., maskers, structured message builders) to keep logs consistent.
3. **Instrument modules** incrementally:
   - pipe → router → client → runner → adapters/tools/persistence.
4. **Add tests** verifying log contents/citations under INFO/DEBUG levels and failure scenarios.
5. **Update docs** and workpackage checklist; run full build/tests to confirm.

## 4. Acceptance Criteria

- Logs include both start/end milestones and contextual details for router decisions, OpenAI responses, tool execution, and errors.
- Setting LOG_LEVEL=INFO yields concise but informative Logs citations; LOG_LEVEL=DEBUG provides deeper diagnostics.
- Tests confirm log output for representative success/failure flows, ensuring secrets are masked.
- Documentation describes how to enable/interpret the enhanced logs.
