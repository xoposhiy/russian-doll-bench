"""
Russian Doll Terminal Server — FastAPI HTTP API.

The session is created once at server startup from environment variables:
  TERMINAL_SPEC (default: sys32)
  TERMINAL_SEED (default: 42)

Endpoints:
  POST /terminal   — send a message to the outer terminal, returns response
  GET  /logs       — retrieve full interaction log
  GET  /status     — check online status of all terminals in the chain

Launch:
  TERMINAL_SPEC=sys32-maze-sys32 TERMINAL_SEED=7 uvicorn server.app:app --port 8000
"""

import os
import pathlib
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from server.sessions import Session
from server.terminal_spec import TerminalBySpecBuilder

# Single global session — initialised in lifespan (or directly in tests).
session: Session | None = None


def _build_terminal_spec_chain(terminal_spec: str, seed: int = 42):
    return TerminalBySpecBuilder().build(terminal_spec, default_seed=seed)


# ---------------------------------------------------------------------------
# App + lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global session
    if session is None:
        seed = int(os.environ.get("TERMINAL_SEED", "42"))
        raw_spec = os.environ.get("TERMINAL_SPEC", "sys32")
        outer = _build_terminal_spec_chain(raw_spec, seed=seed)
        session = Session(outer_terminal=outer)
    yield


app = FastAPI(title="Russian Doll Terminal Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_INDEX_FILE = pathlib.Path(__file__).parent / "index.html"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class LogsResponse(BaseModel):
    entries: list[dict]


class StatusResponse(BaseModel):
    terminal_ids: list[str]
    online_flags: list[bool]
    online: int
    total: int
    done: bool


class StartRequest(BaseModel):
    terminal_spec: str


class StartResponse(BaseModel):
    session_id: str
    welcome: str
    terminal_ids: list[str]
    terminal_spec: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def index():
    if not _INDEX_FILE.is_file():
        return PlainTextResponse("Viewer not found.", status_code=404)
    return FileResponse(_INDEX_FILE)


@app.post("/terminal", response_class=PlainTextResponse)
async def terminal(request: Request):
    """Send a message to the outer terminal."""
    message = (await request.body()).decode("utf-8", errors="replace")
    return session.send(message)


@app.post("/start", response_model=StartResponse, include_in_schema=False)
async def start(req: StartRequest):
    global session
    try:
        normalized_spec = TerminalBySpecBuilder().normalize_terminal_spec(req.terminal_spec)
        outer = _build_terminal_spec_chain(normalized_spec)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session = Session(outer_terminal=outer, run_logger=session.run_logger)
    return StartResponse(
        session_id=uuid.uuid4().hex,
        welcome=outer.get_welcome_message(),
        terminal_ids=[t.terminal_id for t in outer.all_terminals()],
        terminal_spec=normalized_spec,
    )


@app.get("/logs", response_model=LogsResponse, include_in_schema=False)
async def logs():
    """Return the full interaction log."""
    return LogsResponse(entries=[e.to_dict() for e in session.snapshot_log()])


@app.get("/status", response_model=StatusResponse, include_in_schema=False)
async def status():
    """Return the online status of all terminals in the chain."""
    return StatusResponse(**session.status())
