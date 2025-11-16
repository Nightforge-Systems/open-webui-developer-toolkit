# Project Agents.md Guide for OpenAI Codex

This file tells OpenAI Codex (and other AI agents) how to navigate and work in this repo. The project provides **extensions (pipes, filters, tools)** for
[Open WebUI](https://github.com/open-webui/open-webui).

## Project Structure

- `/functions/pipes`   – Open WebUI self-contained pipelines.
- `/functions/filters` – Open WebUI self-contained filters.
- `/tools`             – Open WebUI self-contained tools.
- `/docs`              – Internal documentation for this repo.

Each top-level folder has a `README.md` explaining what's inside. **Keep these brief** and update them when behavior or usage changes.

## Working on OpenAI Responses Manifold

When a task mentions **“responses manifold”** or **`openai_responses_manifold`**, assume it refers to `functions/pipes/openai_responses_manifold`.

From the user’s home directory or repo root, use:

- `cd open-webui-developer-toolkit/functions/pipes/openai_responses_manifold`

Typical local dev workflow for this pipe:

- Create / activate virtualenv (once per checkout):
  - `python -m venv .venv`
  - `source .venv/bin/activate`  (Windows: `.\.venv\Scripts\activate`)
- Install dependencies for development:
  - `make install-dev`
- Common Make targets:
  - `make test`      – run pytest
  - `make lint`      – run Ruff checks
  - `make format`    – apply Ruff formatting
  - `make typecheck` – run mypy on `src/`
  - `make build`     – run tests and regenerate `openai_responses_manifold.py` (single-file bundle for Open WebUI)
  - `make clean`     – remove build artefacts and caches

When modifying code under `src/openai_responses_manifold/`, **always run `make build` before telling the user to import the pipe into Open WebUI**, so the single-file `openai_responses_manifold.py` stays in sync.


## Upstream Mirror (Read‑Only)

- The `external/open-webui/` folder mirrors the upstream Open WebUI project.
- Treat this directory as **read‑only**: do not modify or commit changes here.

## Pull Request Guidelines

When Codex helps create or update a PR:

1. Include a clear description of the change, referencing relevant sections of this `AGENTS.md` where helpful.
2. Reference any related GitHub issues being addressed.
3. Ensure tests pass for all generated/modified code (at least `make test` for the affected extension).
4. Include screenshots or short notes for any UI-facing changes.
5. Keep each PR focused on a single, coherent concern.
