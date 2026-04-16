# Server Guide

This directory contains the HTTP terminal server, session state, the debug UI, and terminal implementations.

## Scope

- `app.py`: FastAPI entry point
- `sessions.py`: in-memory session and nested logs
- `terminals/`: terminal packages, docs, and terminal-specific tests
- `index.html`: manual debug UI served by the server root
- `tests/`: server-level tests and integration tests

## Runtime Notes

- Start with `uvicorn server.app:app --port 8000`
- Open the manual UI at `/`
- HTTP API details live in `../specs/http-terminals.md`
- Keep `POST /start` available for the manual viewer, but hidden from OpenAPI with `include_in_schema=False`
