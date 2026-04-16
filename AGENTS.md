# AGENTS.md

Russian Doll is a benchmark prototype for measuring executive-function behavior in language models through nested terminal environments that require planning, adaptation, and reusable tool-building.

This file provides guidance to AI Agents when working with code in this repository.

The goal of this file is to document common rules and workflows, reduce avoidable mistakes and friction, and help agents complete work with fewer feedback cycles.
If you (AI Agent) struggle with a task, or encounter something surprising in this repo, alert the developer and suggest a change in this file to prevent future agents from hitting the same issue.

## Documentation Layout

- Competition and organizational context: `docs/hackathon.md`
- Server-specific guidance: `server/AGENTS.md`
- Terminal mechanics: markdown files next to terminal implementations in `server/terminals/`
- Terminal implementation guidelines: `server/terminals/AGENTS.md`
- HTTP API and server behavior: `specs/http-terminals.md`

## Architecture

The project has three runtime parts:

1. `benchmark/`: the benchmark task layer and agent loop.
2. `server/`: the HTTP terminal server subtree. See `server/AGENTS.md`.
3. `server/index.html`: the manual browser UI for debugging terminal chains through the same server API.

## Repository Map

Keep this section minimal. Do not let it grow into a file-by-file inventory. Only list top-level paths that are necessary to navigate the system.

- `benchmark/`: benchmark tasks and agent runtime integration
- `server/`: terminals, HTTP server, sessions, and mounted debug viewer
- `logs_viewer/`: standalone structured-log viewer app and static assets
- `specs/`: short implementation notes
- `docs/`: competition and project-context notes
- `run_benchmark.py`: benchmark entry point for local runs and debugging.
- `measure_terminals.py`: compare per-terminal iterations and token usage for one model and write a CSV report.
- `analyze_logs.py`: analyze benchmark JSONL logs, export hypothesis-oriented CSVs, and build SVG charts with `uv run python analyze_logs.py` from the repo root.
- `analyze_run_outputs.py`: analyze `run`-style tool stdout sizes across `logs/` and `logs/archive/`, and write CSV summaries with `uv run python analyze_run_outputs.py` from the repo root.
- `build_kaggle_notebook.py`: print a self-contained Kaggle notebook cell with `uv run python build_kaggle_notebook.py` from the repo root, or `build.bat` on Windows.
- `diagnose_docker_server_hang.py`: run the Docker server hang diagnostic with `uv run python diagnose_docker_server_hang.py` from the repo root.
- `build_dataset.sh`: package benchmark/server inputs for dataset use with `bash build_dataset.sh` from the repo root.

## Key Runtime Notes

- See `server/AGENTS.md` for server runtime notes
- Default test command: `uv run python -m pytest`
- Measure single-terminal usage with `uv run python measure_terminals.py --model <model_id>` from the repo root.
- Start the server with `uv run uvicorn server.app:app --port 8000 --reload` from the repo root, or run `m.cmd` on Windows.
- Start the log viewer with `uv run uvicorn logs_viewer.app:app --host 127.0.0.1 --port 8010 --reload` from the repo root, or run `v.cmd` on Windows.
- If you change benchmark/task behavior, also run one short live smoke benchmark, for example `uv run python run_benchmark.py --model gemini-2.0-flash --terminal sys32-maze --max-steps 2`

## Terminal Docs

See `server/terminals/`

Guidelines for creating new terminals: `server/terminals/AGENTS.md`

## Rules For Future Edits

- Keep all project docs in English.
- Keep `AGENTS.md` short and architectural.
- Keep repository structure descriptions top-level and minimal.
- Put subtree-specific guidance in local `AGENTS.md` files when that keeps the root guide shorter.
- Put terminal behavior docs next to terminal implementations, not in `AGENTS.md`.
- Put competition and organizational context in `docs/`, not in `AGENTS.md`.
- Document every new repo entry point in `AGENTS.md` when it is added. Include how to run it from the repo root, and mention any helper launcher script if one exists.
