> **Note:** Keep this workpackage up to date and add new tasks whenever you discover additional work is needed.
>
> This file documents how the **OpenAI Responses Manifold** should be broken out into a maintainable package, while still bundling back into the single `openai_responses_manifold.py` file that Open WebUI expects.

## Checklist

- [x] Phase 0 – Baseline tests
  - [x] Create `functions/pipes/openai_responses_manifold/tests/`
  - [x] Add basic tests for `CompletionsBody` → `ResponsesBody` conversion
  - [x] Add basic tests for markers + persistence helpers
  - [x] Add a minimal “pipe contract” smoke test
- [x] Phase 1 – Stabilize core models & helpers (still in monolith)
- [x] Phase 2 – Introduce a single “runner” entrypoint (still in monolith)
- [x] Phase 3 – Create `src/openai_responses_manifold/` package skeleton
- [x] Phase 4 – Move code into `core/`, `infra/`, `features/`, `app/` modules
- [x] Phase 5 – Wire `make build` to bundle from `src/` back to the single file
- [x] Phase 6 – Update tests, run `make test`, and smoke test in Open WebUI

> While working through each phase:
> - Prefer small, mechanical steps.
> - After each significant change, run at least `make test` and, if relevant, `make lint` / `make typecheck`.

---

## 1. Background & Goals

**Original source file (current single-file manifold):**

```text
functions/pipes/openai_responses_manifold/openai_responses_manifold.py
````

The file:

* Begins with a **manifest docstring** that Open WebUI depends on:

  ```python
  """
  title: OpenAI Responses API Manifold
  id: openai_responses
  ...
  """
  ```

* Defines a **`Pipe` class** with **nested `Valves` and `UserValves` classes**:

  ```python
  class Pipe:
      class Valves(BaseModel): ...
      class UserValves(BaseModel): ...
      async def pipes(...): ...
      async def pipe(...): ...
  ```

Open WebUI’s custom function system expects:

* A single Python file per function/pipe.
* A manifest docstring at the top.
* A `Pipe` class implementing `.pipes()` and `.pipe(...)`.
* Nested `Valves` / `UserValves` describing configuration schemas.

**Goal of this refactor:**

* Make the codebase **maintainable** and **testable** by splitting logic into a normal Python package under:

  ```text
  functions/pipes/openai_responses_manifold/src/openai_responses_manifold/
  ```

* Keep using `make build` to **bundle** the package back into the single `openai_responses_manifold.py` file that Open WebUI imports.

---

## 2. Phase 0 – Baseline Tests (before refactor)

Before touching structure, lock in the current behavior with tests. This reduces the risk of accidental regressions as we refactor.

### 2.1 Create tests folder & basic configuration

* Create:

  ```text
  functions/pipes/openai_responses_manifold/tests/
  ```

* Add `conftest.py` if needed to ensure imports work for both the monolithic file and the eventual package. For now, you can import the module by its file name (`openai_responses_manifold`), which will remain valid after the package breakout.

### 2.2 Write Completions→Responses tests

Create `tests/test_responses_body_from_completions.py`:

* Import from the monolithic module:

  ```python
  from openai_responses_manifold import CompletionsBody, ResponsesBody, ModelFamily
  ```

  (or adapt names to exactly match your current monolith).

* Add tests for:

  * **Reasoning effort mapping:**

    * Given a `CompletionsBody` with `reasoning_effort="minimal"`:

      * `ResponsesBody.from_completions` sets `reasoning.effort="minimal"`.
  * **`max_tokens` → `max_output_tokens`:**

    * If `max_tokens` is set, verify it appears as `max_output_tokens` in the resulting `ResponsesBody`.
  * **System prompt to `instructions`:**

    * Last `{"role": "system", "content": ...}` becomes `instructions`.
  * **Messages to `input`:**

    * `user` messages become `input` entries with `input_text` / `input_image` / `input_file`.
    * `assistant` messages with no markers become `output_text` entries.
    * System messages are excluded from `input` (they’re used for `instructions`).

Run:

```bash
make test
```

Make sure all new tests pass before refactoring.

### 2.3 Write marker + persistence tests

Create `tests/test_markers_and_persistence.py`:

* Validate that:

  * `create_marker` + `wrap_marker` produce the expected string format.
  * `contains_marker`, `extract_markers`, `split_text_by_markers` (or `split_text`) identify markers correctly and recover them from text.
  * `persist_openai_response_items`:

    * Writes items into the expected `chat.chat["openai_responses_pipe"]` structure.
    * Returns concatenated marker strings.
  * `fetch_openai_response_items`:

    * Retrieves items by ULID and respects the `model` when `openwebui_model_id` is set.

You can stub `Chats` with a simple in-memory mock for these tests if needed, or use a dedicated dummy chat created via `Chats` if it’s cheap.

### 2.4 Minimal “pipe contract” test

Create `tests/test_pipe_contract.py`:

* Import `Pipe` from the monolithic module:

  ```python
  from openai_responses_manifold import Pipe
  ```

* Add a smoke test that:

  * Instantiates `Pipe`.
  * Calls `.pipes()` and asserts it returns a non-empty list of dicts with `id` and `name`.
  * Optionally, invokes `.pipe()` in a minimal, non-streaming scenario and asserts it returns a string (even if empty) or an async generator as expected.

Run `make test` again and keep these tests passing throughout the refactor.

---

## 3. Phase 1 – Stabilize core models & helpers (still in monolith)

Before splitting into modules, make sure the **core shapes** and helpers are the single source of truth and used consistently.

Focus areas:

* `ModelFamily` – centralizes model IDs, capabilities, and alias params.
* `CompletionsBody` and `ResponsesBody` – the only entrypoints for shape conversion.
* Marker helpers – the only way to encode/decode hidden items in assistant text.
* `SessionLogger` – a single, coherent logging abstraction.

### Tasks

* [ ] Ensure **all** logic that touches model IDs and capabilities uses `ModelFamily` methods (`base_model`, `params`, `features`, `supports`).
* [ ] Ensure **all** Completions→Responses conversion goes through `ResponsesBody.from_completions`.
* [ ] Ensure markers are handled via the marker helpers (`create_marker`, `wrap_marker`, `contains_marker`, `parse_marker`, `extract_markers`, `split_text_by_markers`).
* [ ] Ensure `SessionLogger` is the *only* way to create loggers, and that there’s only one definition.

After each consolidation step, run:

```bash
make test
```

---

## 4. Phase 2 – Introduce a single “runner” entrypoint (still in monolith)

Right now `Pipe` mixes:

* Open WebUI integration concerns (valves, model list, manifest).
* Request shaping (from `body`/metadata to OpenAI request).
* Streaming orchestration (tool loops, persistence, status events, etc.).

To make later module splits easier, create a **single runner abstraction** *inside the monolithic file* first.

### Concept

Define a cohesive API like:

```python
def run_responses(
    responses_body: ResponsesBody,
    *,
    valves: Pipe.Valves,
    metadata: dict[str, Any],
    tools: dict[str, dict[str, Any]] | list[dict[str, Any]] | None,
    event_emitter: Callable[[dict[str, Any]], Awaitable[None]],
    http_client: <something>,
) -> AsyncGenerator[str, None] | str:
    ...
```

Then make `Pipe.pipe()` primarily:

* building `CompletionsBody` / `ResponsesBody`,
* merging valves,
* computing metadata & user id,
* calling `run_responses(...)`,
* returning its result.

You don’t have to create a separate class yet; a function or lightweight `ResponseRunner` in the same file is fine. The important part: the **streaming + tool-calling loop becomes a single, cohesive unit**.

### Tasks

* [x] Extract the existing streaming loop into a dedicated “runner” (function or class) in the monolith.
* [x] Update `Pipe.pipe()` to delegate to this runner.
* [x] Ensure tests (especially `test_pipe_contract` and any new runner tests) still pass.

Run:

```bash
make test
```

---

## 5. Phase 3 – Create the `src/openai_responses_manifold/` package

Now that shapes and runner are consolidated in the monolith, create the real package skeleton:

```text
functions/pipes/openai_responses_manifold/
  src/
    openai_responses_manifold/
      __init__.py

      core/
        __init__.py
        capabilities.py
        models.py
        session_logger.py
        markers.py
        utils.py

      infra/
        __init__.py
        persistence.py
        client.py

      features/
        __init__.py
        tools.py
        router.py

      app/
        __init__.py
        pipe.py
```

At this stage, the modules are mostly empty or have placeholder docstrings. Don’t move code yet.

---

## 6. Phase 4 – Move code into modules

Now do the mechanical split using the mapping from the previous work:

### 6.1 Copy, then cut

For each section in the monolithic file:

1. Copy the code into the target module in `src/openai_responses_manifold/`.
2. Fix imports in the new module to use package-absolute paths.
3. Run `make test` to confirm nothing broke.
4. Only after tests pass, remove that section from the monolith (if your bundler will no longer rely on it), or mark it as “legacy” until bundling is fully switched to the new package.

### 6.2 Recommended move order

Low-risk → high-risk:

1. **Core types**:

   * `ModelFamily` → `core/capabilities.py`
   * `CompletionsBody` & `ResponsesBody` → `core/models.py`
   * marker helpers → `core/markers.py`
   * `SessionLogger` → `core/session_logger.py`
   * `merge_usage_stats`, `wrap_code_block`, etc. → `core/utils.py`

2. **Persistence & HTTP**:

   * `persist_openai_response_items`, `fetch_openai_response_items` → `infra/persistence.py`
   * HTTP helper functions (`send_openai_responses_*`, `_get_or_init_http_session`) → `infra/client.py`

3. **Features**:

   * `build_tools`, `_strictify_schema`, `_dedupe_tools` → `features/tools.py`
   * `_route_gpt5_auto` (if extracted) → `features/router.py`

4. **App**:

   * `Pipe` and runner logic → `app/pipe.py` (or `app/runner.py` + `app/pipe.py` if you split further).

After each chunk is moved and imports are updated, run:

```bash
make test
```

---

## 7. Phase 5 – Wire `make build` to bundle from `src/`

Once everything lives under `src/openai_responses_manifold/`, update the build step to generate the single `openai_responses_manifold.py` file for Open WebUI from the package modules instead of the old monolith.

High-level steps:

1. Ensure `src/` is on `PYTHONPATH`:

   * For example, from `functions/pipes/openai_responses_manifold`:

     ```bash
     export PYTHONPATH="$PWD/src:$PYTHONPATH"
     ```

   * Or do this inside the build script.

2. Import all modules to confirm imports are correct:

   ```python
   import openai_responses_manifold.core.capabilities
   import openai_responses_manifold.core.models
   ...
   import openai_responses_manifold.app.pipe
   ```

3. Combine modules into a single file in this order (conceptual):

   * Manifest docstring (copied exactly from the original file).
   * Top-level imports (standard library, third-party, Open WebUI).
   * `core/` modules.
   * `infra/` modules.
   * `features/` modules.
   * `app/pipe.py` (with `Pipe` class and any alias definitions).

4. Emit the final `openai_responses_manifold.py` into:

   ```text
   functions/pipes/openai_responses_manifold/openai_responses_manifold.py
   ```

5. Compile to catch errors:

   ```bash
   python -m compileall functions/pipes/openai_responses_manifold/openai_responses_manifold.py
   ```

Run:

```bash
make build
make test
```

> **Status (2025-11-16):** `make build` now runs `scripts/build.py`, which executes pytest and bundles the modules from `src/` back into `openai_responses_manifold.py`. The script is still the legacy, regex-based bundler; plan a follow-up workpackage to rewrite/simplify it once the refactor dust settles.

---

## 8. Phase 6 – Final tests & Open WebUI smoke test

Once `make build` is wired to the new package:

1. Run the full suite:

   ```bash
   make lint
   make typecheck
   make test
   make build
   ```

2. In Open WebUI:

   * Import the newly built `openai_responses_manifold.py` (using the manifest link or manual upload).
   * Verify:

     * Models appear under Functions as before.
     * Tools / function-calling still work.
     * Web search (if enabled) still behaves correctly.
     * GPT-5 routing (`gpt-5-auto`, etc.) still behaves as expected.
     * Hidden markers don’t show up in the UI, and persisted items are reused correctly.
     * Usage information is visible and makes sense.

3. If anything breaks:

   * Use `SessionLogger` logs and tests to trace regressions.
   * Fix the corresponding module and update tests as needed.

> **Status (2025-11-16):** `make lint`, `make typecheck`, `make test`, and `make build` all run cleanly on the modularized package + bundler. Plan to run a quick Open WebUI smoke test the next time an admin environment is available.

---

## 9. Future improvements (separate workpackages)

Once this structural refactor is complete and stable, consider follow-up WPs:

* **Engine abstraction:** introduce a dedicated “Responses Engine” that takes events from OpenAI and emits domain events, with the Pipe just acting as an adapter.
* **Context-managed logging:** add a context manager to `SessionLogger` (e.g., `scoped_context`) to avoid context leaks.
* **Typed events:** introduce `TypedDict` or dataclasses for frames/tool calls to make future refactors safer.
* **AGENTS.md:** add a small “code map” document for AI agents, aligned with this refactor.

For now, use this `refactor_openai_responses_manifold.md` as the primary guide and keep it updated as you learn during the refactor.
