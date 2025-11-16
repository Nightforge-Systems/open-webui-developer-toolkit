> **Note:** Keep this workpackage up to date. Check off items as you finish them and add subtasks if new work appears.

## Checklist
- [ ] Understand current logging flow (SessionLogger, runner `_log`, emitters)
- [ ] Design session-scoped logging plan aligned with standard Python logging
- [ ] Configure root logger once via SessionLogger (modules just call `logging.getLogger`)
- [ ] Implement buffer handler + minimal filter (injects session id only)
- [ ] Update modules to rely on standard logging (drop `_log`, adhoc guards)
- [ ] Ensure `_flush_logs` always emits/clears logs even on failure (best-effort)
- [ ] Verify valves/user valves correctly control log level (explicit resolution order)
- [ ] Add/Update tests covering log emission behavior + concurrent sessions

---

# Workpackage: Harden Session-Scoped Logging for OpenAI Responses Manifold

## 0. Background

The manifold currently uses `SessionLogger` to attach `session_id` context and buffer log lines that are later emitted as a “Logs” citation. Over time, pieces of logging logic have drifted:

- Some modules call `SessionLogger.get_logger`, others use plain `logging.getLogger`.
- `ResponseRunner` introduced an ad-hoc `_log()` helper to gate INFO-level statements.
- Logs sometimes show up even when the user or global valves set `LOG_LEVEL` to WARN/ERROR.
- `_flush_logs()` may be skipped or run too late when failures occur, meaning logs are not surfaced even if they exist.

We want a clean, standard logging pipeline that:

1. Uses conventional Python logging APIs everywhere (`logging.getLogger(__name__)` and standard `logger.info/debug/...` calls).
2. Configures per-session context & buffering in one place (inside `SessionLogger`), so no bespoke helpers are needed.
3. Honors the merged valve/user valve `LOG_LEVEL` for every run.
4. Always delivers the buffered logs via citation, even when the run fails midway.
5. Avoids cross-session leakage by keying everything off contextvars (already available).

## 1. Goals and Requirements

- **Per-run isolation:** All log records must be tagged with the current chat session ID and never leak to other chats.
- **Valve-controlled verbosity:** `Valves.LOG_LEVEL`, overridden by `UserValves.LOG_LEVEL`, determines which records are buffered/emitted. `INHERIT` from user valves means “use whatever the global setting is”.
- **Always emit logs:** Whether the run succeeds or fails, `_flush_logs()` (or equivalent) must run and produce a “Logs” citation if records exist. This includes exceptions raised anywhere in the orchestration loop.
- **Standard logging usage:** Modules (router, adapters, tools, runner, etc.) should not need custom helper methods to check log levels—they should just call the logger once and let the filter decide.
- **Single buffering mechanism:** `SessionLogger` should be the canonical place that attaches filters/handlers. It can use a simple in-memory handler (e.g., custom `logging.Handler` or `logging.handlers.MemoryHandler`) keyed by `session_id`.

## 2. Deliverables

1. **SessionLogger redesign (if needed):**
   - Provide a `configure_logging()` entry point (call once, guard against duplicate setup) that attaches:
     * A filter that injects `record.session_id` (level enforcement handled via `logger.setLevel`).
     * A dedicated `SessionBufferHandler` that captures formatted log strings into `SessionLogger.logs[session_id]`.
   - Ensure configuration happens once (e.g., on import) and modules just call `logging.getLogger(__name__)`.

2. **Pipe entry (`pipe.py`):**
   - After merging valves, resolve LOG_LEVEL using this order: `UserValves.LOG_LEVEL` (unless `INHERIT`) → `Valves.LOG_LEVEL` → `GLOBAL_LOG_LEVEL` env override → default INFO.
   - Set `SessionLogger.session_id` and apply the resulting level via `logger.setLevel(...)`.
   - Consider providing a simple context manager if needed to ensure cleanup.

3. **Runner / orchestration changes:**
   - Remove bespoke `_log()` guard if the logger already handles level gating.
   - Guarantee `_flush_logs()` executes in every exit path (success, error, cancellation).
   - `_flush_logs()` should emit logs even if earlier emitters failed (maybe wrap in try/except).

4. **Module logging changes:**
   - Swap `SessionLogger.get_logger(__name__)` usages for `logging.getLogger(__name__)`.
   - Remove runner `_log()` helper once level enforcement is centralized.

5. **Tests & validation:**
   - Unit/integration tests demonstrating:
     * Setting LOG_LEVEL to `ERROR` suppresses INFO log citations.
     * Setting LOG_LEVEL to `DEBUG` causes debug entries to appear.
     * Logs still emit when an exception occurs during streaming/batch.

6. **Docs / README:**
   - Update README or developer notes to describe how logging + valves interact (if not already documented).

## 3. Suggested Plan

1. **Recon current state:** Trace logging flow from `Pipe.pipe` through `SessionLogger`, `runner`, and emitted events.
2. **Redesign SessionLogger:** Simplify to standard logging filter + handler pattern.
3. **Normalize module loggers:** Ensure every module just requests `logging.getLogger(__name__)`.
4. **Wire valve level once per request:** Possibly through a helper function (e.g., `configure_session_logging(session_id, valves)`).
5. **Harden `_flush_logs`:** Guarantee it runs and does not throw.
6. **Add tests:** Extend `tests/test_runner.py` or similar to cover the scenarios above.
7. **Manual validation:** Run `make build`, maybe simulate logs manually to confirm citations render correctly in Open WebUI.

## 4. Acceptance Criteria

- Logs respect the merged valve/user valve level.
- No cross-session leakage; concurrent runs can’t see each other’s logs.
- Logs are always emitted after a run if any were recorded (even when it fails).
- Tests prove the behavior; `make build` continues to pass.
- Documentation and code comments clarify how to enable/disable logging via valves.
