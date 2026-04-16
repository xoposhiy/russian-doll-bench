"""Shared testing helpers for server and terminal tests."""

from .trace_harness import StepResult, TraceHarness, render_trace, write_solution_trace_if_changed

__all__ = [
    "StepResult",
    "TraceHarness",
    "render_trace",
    "write_solution_trace_if_changed",
]
