"""

Kaggle Benchmark's LLMChat isn't a sufficient wrapper for tool calling, unfortunately.

We had to reinvent the wheel and implement two different loops for GenAI- and OpenAI-compatible models.
We also had to duplicate all the messages by sending them to LLMChat (to be visible on the Kaggle website)
and to the model's client.

We don't like it, but it's the only way to make it work now.

Below there is the infrastructure to run agentic loops with tools.

"""
import inspect
import json
import pathlib
import time
from datetime import datetime
from typing import Callable, Any, TypeAlias

import requests
import requests.adapters
from urllib3.util import Retry

from google.genai import types
from kaggle_benchmarks import actors, chats, envs, contexts, messages as kb_messages
from kaggle_benchmarks.actors.llms import GoogleGenAI, OpenAI

from benchmark.telemetry import RunTelemetry, emit_event, get_run_logger, get_last_agent_error, set_last_run_metrics, \
    set_last_agent_error, _json_safe, _build_usage_metadata

# ---------------------------------------------------------------------------
# Virtual File System
# ---------------------------------------------------------------------------

_TEMP_BASE = pathlib.Path(__file__).parent.parent / "temp"
_RUN_TIMEOUT_SECONDS = 10


def create_timestamped_temp_folder() -> pathlib.Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    candidate = _TEMP_BASE / stamp
    suffix = 1
    while candidate.exists():
        candidate = _TEMP_BASE / f"{stamp}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def get_log_filename(run_id: str, model_name: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_model = model_name.replace("/", "-")
    safe_run_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in run_id)
    return f"{timestamp}-{safe_model}-{safe_run_id}.jsonl"


ToolCallResult: TypeAlias = dict[str, Any]
Tool: TypeAlias = Callable[..., ToolCallResult]


class VirtualFileSystem:
    """An "in-folder" filesystem with Python script execution via kaggle_benchmarks envs.

    Each benchmark/task instance gets its own isolated subdirectory under temp/ — no files leak
    between runs.
    """

    _overridden_root: pathlib.Path | None = None

    def __init__(self, env_vars: dict[str, str] | None = None):
        self.root = self._overridden_root or create_timestamped_temp_folder()
        self.root.mkdir(parents=True, exist_ok=True)
        self._env_vars: dict[str, str] = env_vars or {}
        self._run_metrics: RunTelemetry | None = None

    @classmethod
    def override_root(cls, root: pathlib.Path | None):
        cls._overridden_root = root

    def bind_run_metrics(self, metrics: RunTelemetry):
        self._run_metrics = metrics

    def _resolve(self, filename: str) -> pathlib.Path | None:
        candidate = (self.root / filename).resolve()
        try:
            candidate.relative_to(self.root.resolve())
            return candidate
        except ValueError:
            return None

    def _check(self, filename: str) -> str | None:
        if not filename:
            return "Filename must not be empty."
        if self._resolve(filename) is None:
            return f"Invalid filename '{filename}': must not escape the sandbox."
        return None

    def write(self, filename: str, content: str) -> ToolCallResult:
        if err := self._check(filename):
            return {"error": err}
        path = self._resolve(filename)
        assert path is not None
        existed = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if not existed and self._run_metrics is not None:
            self._run_metrics.created_files.add(filename)
        verb = "overwritten" if existed else "created"
        return {"file": filename, "operation": verb, "new_size": len(content)}

    def exists(self, filename: str) -> bool:
        path = self._resolve(filename)
        return path.exists() if path is not None else False

    def read(self, filename: str) -> ToolCallResult:
        if err := self._check(filename):
            return {"error": err}
        path = self._resolve(filename)
        assert path is not None
        if not path.is_file():
            return {"error": f"File '{filename}' not found."}
        return {"file_content": path.read_text(encoding="utf-8")}

    def update(self, filename: str, str_to_replace: str, replacement: str) -> ToolCallResult:
        read_result = self.read(filename)
        if "error" in read_result:
            return read_result
        content = read_result["file_content"]
        count = content.count(str_to_replace)
        if count == 0:
            return {"error": "No occurrences found."}
        new_content = content.replace(str_to_replace, replacement)
        self.write(filename, new_content)
        return {"file": filename, "operation": "updated", "replacement_count": count}


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------

# kaggle_benchmarks.tools.functions.function_to_openai_tool generates something incompatible (a bug?),
# so we built the tool schema by ourselves.
MANUAL_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file in the virtual filesystem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Return the content of a saved file.",
            "parameters": {
                "type": "object",
                "properties": {"filename": {"type": "string"}},
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_file",
            "description": "Replace all occurrences of str_to_replace with replacement in a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "str_to_replace": {"type": "string"},
                    "replacement": {"type": "string"},
                },
                "required": ["filename", "str_to_replace", "replacement"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run",
            "description": """Run a command in the regular unix shell. You can use curl, pip, ls, cat or any other available command. You can also run Python script you've created with write_file or update_file.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "A space-separated CLI command."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "give_up",
            "description": "Signal that all approaches are exhausted.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

DEFAULT_MAX_STEPS = 50
PROMPTS_DIR = pathlib.Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def make_system_prompt(server_url: str, outer_welcome_message: str, advanced: bool = False) -> str:
    return (
        (_load_prompt("system.md") if not advanced else _load_prompt("system-advanced.md"))
        .replace("{server_url}", server_url)
        .replace("{welcome_message}", outer_welcome_message)
    )


EXIT_EXPECTED_PROMPT = _load_prompt("exit.md")
NOT_A_TOOLCALL_PROMPT = _load_prompt("not-a-toolcall.md")
START_MESSAGE = "Begin. Explore the terminal system and bring all subsystems ONLINE."

# ---------------------------------------------------------------------------
# Agent Loop
# ---------------------------------------------------------------------------

_tool_actor = actors.Actor(name="Tool", role="tool", avatar="🛠️")


def _resolve_server_url(server_url: str) -> str:
    return server_url.rstrip("/")


def _get_status(server_url: str) -> dict | None:
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.1,
        status_forcelist=[502, 503, 504],
        allowed_methods={'POST'},
    )
    s.mount("http://", requests.adapters.HTTPAdapter(max_retries=retries))

    try:
        return s.get(f"{server_url}/status", timeout=15).json()
    except Exception:
        return None


def _update_run_metrics_from_status(
    metrics: RunTelemetry,
    status: dict | None,
    iteration: int,
) -> None:
    if not status:
        return

    terminal_ids = status.get("terminal_ids", [])
    online_flags = status.get("online_flags", [])
    for terminal_id in terminal_ids:
        metrics.terminal_activation_steps.setdefault(terminal_id, None)
    for terminal_id, is_online in zip(terminal_ids, online_flags, strict=False):
        if is_online and metrics.terminal_activation_steps[terminal_id] is None:
            metrics.terminal_activation_steps[terminal_id] = iteration
            emit_event(
                event_type="terminal_online",
                actor="benchmark",
                iteration=iteration,
                terminal_id=terminal_id,
                status_snapshot={
                    "terminal_ids": terminal_ids,
                    "online_flags": online_flags,
                },
            )


def _emit_run_end(
    metrics: RunTelemetry,
    *,
    iteration: int | None,
    score: int,
    max_score: int,
    done: bool,
) -> None:
    if metrics.run_end_emitted:
        return
    emit_event(
        event_type="run_end",
        actor="benchmark",
        iteration=iteration,
        score=score,
        max_score=max_score,
        done=done,
    )
    metrics.run_end_emitted = True


def _emit_run_summary(
    metrics: RunTelemetry,
    *,
    iteration: int | None,
    score: int,
    max_score: int,
    done: bool,
    run_error: str | None = None,
    agent_error: str | None = None,
) -> None:
    if metrics.run_summary_emitted:
        return
    emit_event(
        event_type="run_summary",
        actor="benchmark",
        kind="derived",
        iteration=iteration,
        score=score,
        max_score=max_score,
        iterations=metrics.iterations,
        created_files_count=len(metrics.created_files),
        created_files=sorted(metrics.created_files),
        token_metrics=_json_safe(metrics.token_metrics),
        sum_output_tokens=_json_safe(metrics.token_metrics.output_tokens),
        sum_input_tokens=_json_safe(metrics.token_metrics.input_tokens),
        terminal_activation_steps=metrics.terminal_activation_steps,
        activated_terminals_count=sum(
            1 for value in metrics.terminal_activation_steps.values() if value is not None
        ),
        total_terminals=len(metrics.terminal_activation_steps),
        done=done,
        run_error=run_error,
        agent_error=agent_error,
    )
    metrics.run_summary_emitted = True


def _make_bound_tools(
    vfs: VirtualFileSystem,
) -> dict[str, Tool]:
    def write_file(filename: str, content: str) -> ToolCallResult:
        """Create or overwrite a file in the virtual filesystem."""
        return vfs.write(filename, content)

    def read_file(filename: str) -> ToolCallResult:
        """Read a file from the virtual filesystem."""
        return vfs.read(filename)

    def update_file(filename: str, str_to_replace: str, replacement: str) -> ToolCallResult:
        """Replace all matching text inside a file."""
        return vfs.update(filename, str_to_replace, replacement)

    def run(command: str | list[str]) -> ToolCallResult:
        """
        Run a command in the regular unix shell.
        You can use curl, pip, ls, cat or any other available command.
        You can also run a Python script you've created with write_file or update_file.
        """
        try:
            run_result = envs.current.run(command, input=None)
        except Exception as e:
            run_result = envs.RunResult(exit_code=-1, stdout="", stderr=str(e))

        return {"exit_code": run_result.exit_code, "stdout": run_result.stdout, "stderr": run_result.stderr}

    def give_up(reason: str) -> ToolCallResult:
        """Signal that all approaches are exhausted."""
        return {"status": "Acknowledged."}

    return {
        "write_file": write_file,
        "read_file": read_file,
        "update_file": update_file,
        "run": run,
        "give_up": give_up,
    }


def _dispatch_tool(
    tool_name: str,
    args: dict,
    tools: dict[str, Tool],
) -> tuple[ToolCallResult, bool]:
    tool = tools.get(tool_name)
    if tool is None:
        result = {"error": f"Unknown tool: {tool_name}"}
        emit_event(
            event_type="tool_result",
            actor="tool",
            tool_name=tool_name,
            result=result,
            error_type="unknown_tool",
        )
        return result, False
    if not isinstance(args, dict):
        result = {"error": f"Invalid arguments for tool '{tool_name}': expected an object, got {type(args).__name__}."}
        emit_event(
            event_type="tool_result",
            actor="tool",
            tool_name=tool_name,
            result=result,
            error_type="invalid_tool_args",
        )
        return result, False
    signature = inspect.signature(tool)
    accepted = {
        key: value
        for key, value in args.items()
        if key in signature.parameters
    }
    dropped = sorted(set(args) - set(accepted))
    if dropped:
        emit_event(
            event_type="agent_warning",
            actor="benchmark",
            warning_type="unexpected_tool_args",
            detail=f"{tool_name}: {dropped}",
        )
    try:
        signature.bind(**accepted)
    except TypeError as exc:
        result = {"error": f"Invalid arguments for tool '{tool_name}': {exc}"}
        emit_event(
            event_type="tool_result",
            actor="tool",
            tool_name=tool_name,
            result=result,
            error_type="invalid_tool_args",
        )
        return result, False
    emit_event(
        event_type="tool_call",
        actor="tool",
        tool_name=tool_name,
        arguments=accepted,
    )

    try:
        result = tool(**accepted)

        emit_event(
            event_type="tool_result",
            actor="tool",
            tool_name=tool_name,
            result=result,
        )

        return result, tool_name == "give_up"
    except Exception as exc:
        result = {"error": f"Tool '{tool_name}' failed: {type(exc).__name__}: {exc}"}
        emit_event(
            event_type="tool_result",
            actor="tool",
            tool_name=tool_name,
            result=result,
            error_type="tool_runtime_error",
        )
        return result, False


def _is_openai_compatible_llm(llm) -> bool:
    return hasattr(llm, "client") and hasattr(llm, "model") and not isinstance(llm, GoogleGenAI)


def _append_chat_artifact_message(sender, content: str, *, is_visible_to_llm: bool = False, **meta) -> None:
    contexts.get_current().chat.append(
        kb_messages.Message(
            sender=sender,
            content=content,
            is_visible_to_llm=is_visible_to_llm,
            _meta=meta,
        )
    )


def _run_openai_compatible_manual_tool_loop(
    llm: OpenAI,
    tools: dict[str, Tool],
    server_url: str,
    metrics: RunTelemetry,
    max_steps: int,
    system_prompt: str,
    advanced: bool = False,
) -> None:
    if not _is_openai_compatible_llm(llm):
        raise TypeError(
            f"Manual tool loop requires an OpenAI-compatible client, got {type(llm).__name__}."
        )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": START_MESSAGE}
    ]
    actors.user.send(START_MESSAGE)
    pending_messages_for_log: list[dict] = [dict(message) for message in messages]

    exit_expected = False
    step = 0

    while True:
        get_run_logger().set_iteration(step + 1)

        if exit_expected:
            exit_message = {"role": "user", "content": EXIT_EXPECTED_PROMPT}
            actors.user.send(EXIT_EXPECTED_PROMPT)
            messages.append(exit_message)
            pending_messages_for_log.append(exit_message)

        metrics.iterations = step + 1
        last_messages = messages[-2:] if len(messages) > 2 else messages
        emit_event(
            event_type="model_request",
            actor="model",
            iteration=step + 1,
            mode="manual",
            last_messages=[m["content"] for m in last_messages if m["role"] == "user" or m["role"] == "tool"],
            tools=[schema["function"]["name"] for schema in MANUAL_TOOL_SCHEMAS],
            sent_messages=pending_messages_for_log,
        )
        pending_messages_for_log = []
        try:
            response = llm.client.chat.completions.create(
                model=llm.model,
                messages=messages,
                tools=[tool for tool in MANUAL_TOOL_SCHEMAS if tool["function"]["name"] in tools],
            )
        except Exception as exc:
            message = f"Model call failed: {type(exc).__name__}: {exc}"
            set_last_agent_error(message)
            emit_event(
                event_type="agent_warning",
                actor="benchmark",
                iteration=step + 1,
                warning_type="model_call_failed",
                detail=message,
                error_type=type(exc).__name__,
            )
            return

        if not response.choices:
            emit_event(
                event_type="agent_warning",
                actor="benchmark",
                iteration=step + 1,
                warning_type="no_response",
                detail=_json_safe(response),
            )
            actors.user.send("Continue")
            reminder_message = {"role": "user", "content": "Continue"}
            messages.append(reminder_message)
            pending_messages_for_log.append(reminder_message)
            step += 1
            continue

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls or []
        tool_calls_payload = [tool_call.model_dump() for tool_call in tool_calls]
        usage_metadata = _build_usage_metadata(llm, response.usage)
        emit_event(
            event_type="model_response",
            actor="model",
            iteration=step + 1,
            mode="manual",
            text=response_message.content or "",
            tool_calls=tool_calls_payload,
            usage_metadata=usage_metadata,
        )
        # Doesn't work
        # _merge_token_usage(metrics, usage_metadata)

        messages.append(
            {
                "role": "assistant",
                # Anthropic models sometimes respond with an empty message, and then says
                # BadRequestError: Error code: 400 - {'message': '{"type":"error","error":{"type":"invalid_request_error","message":"messages: text content blocks must be non-empty"}
                "content": response_message.content or ("-" if llm.name.startswith("anthropic/") else ""),
                **({"tool_calls": tool_calls_payload} if tool_calls_payload else {}),
            }
        )
        if response_message.content:
            llm.send(response_message.content)
        if tool_calls_payload:
            llm.send("Tool calls: " + json.dumps(tool_calls_payload))

        _append_chat_artifact_message(
            llm,
            response_message.content or "",
            tool_calls=tool_calls_payload,
            input_tokens=usage_metadata.get("input_tokens"),
            output_tokens=usage_metadata.get("output_tokens"),
            input_tokens_cost_nanodollars=usage_metadata.get("input_tokens_cost_nanodollars"),
            output_tokens_cost_nanodollars=usage_metadata.get("output_tokens_cost_nanodollars"),
            total_backend_latency_ms=usage_metadata.get("total_backend_latency_ms"),
        )

        if not tool_calls_payload:
            # Advanced task exits as soon as the model responds with a simple text without tool calling
            if exit_expected or advanced:
                break

            emit_event(
                event_type="agent_warning",
                actor="benchmark",
                iteration=step + 1,
                warning_type="no_tool_call",
                detail=response_message.content or "",
            )
            reminder = NOT_A_TOOLCALL_PROMPT
            reminder_message = {"role": "user", "content": reminder}
            actors.user.send(reminder)
            messages.append(reminder_message)
            pending_messages_for_log.append(reminder_message)
            step += 1
            continue

        stop = False
        for tc in tool_calls_payload:
            fn_name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            result, should_stop = _dispatch_tool(fn_name, args, tools)
            stop = stop or should_stop
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result),
                }
            )
            _tool_actor.send(json.dumps(result))
            _append_chat_artifact_message(_tool_actor, json.dumps(result), tool_call_id=tc["id"])
        if stop:
            if advanced:
                break

            exit_expected = True
            step += 1
            continue

        status = _get_status(server_url)
        _update_run_metrics_from_status(metrics, status, iteration=step + 1)
        if status and status.get("done") and not advanced:
            exit_expected = True

        if step >= max_steps:
            if advanced:
                emit_event(
                    event_type="agent_warning",
                    actor="benchmark",
                    warning_type="max_steps_reached",
                    detail=f"Max steps reached: agent didn't finish in {max_steps} steps.",
                )
                break

            exit_expected = True
        if step >= 2 * max_steps:
            emit_event(
                event_type="agent_warning",
                actor="benchmark",
                warning_type="max_steps_reached",
                detail=f"Max steps reached: agent didn't complete main.py updates in {max_steps} steps.",
            )
            break

        step += 1

    status = _get_status(server_url)
    _emit_run_end(
        metrics,
        iteration=step + 1,
        score=status["online"],
        max_score=status["total"],
        done=status["done"],
    )


# Some Gemini models send an empty part and then reject them
def _fix_genai_content(content: types.Content):
    good_parts = []
    for part in content.parts:
        if part.text or part.thought or part.thought_signature or part.function_response or part.function_call or part.executable_code or part.code_execution_result:
            good_parts.append(part)
    content.parts = good_parts


def _run_genai_tool_loop(
    llm: GoogleGenAI,
    system_prompt: str,
    tools: dict[str, Tool],
    server_url: str,
    metrics: RunTelemetry,
    max_steps: int,
    advanced: bool = False,
) -> None:
    emit_event(
        event_type="agent_warning",
        actor="benchmark",
        warning_type="tool_mode",
        detail="Using explicit genai function-call loop.",
    )
    contents: list[types.Content] = [types.Content(role="user", parts=[types.Part(text=START_MESSAGE)])]
    actors.user.send(START_MESSAGE)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=list(tools.values()),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        thinking_config=types.ThinkingConfig(
            include_thoughts=True,
        )
    )

    exit_expected = False
    step = 0

    while True:
        get_run_logger().set_iteration(step + 1)

        if exit_expected:
            actors.user.send(EXIT_EXPECTED_PROMPT)
            exit_content = types.Content(role="user", parts=[types.Part(text=EXIT_EXPECTED_PROMPT)])
            contents.append(exit_content)

        metrics.iterations = step + 1
        last_contents = contents[-2:] if len(contents) > 2 else contents
        emit_event(
            event_type="model_request",
            actor="model",
            iteration=step + 1,
            mode="genai",
            last_messages=["\n".join(p.text or json.dumps(p.function_response.response) for p in c.parts)
                           for c in last_contents if c.role == "user" or c.role == "tool"],
            tools=list(tools),
        )
        started = time.perf_counter()
        try:
            response = llm.client.models.generate_content(
                model=llm.model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            message = f"Model call failed: {type(exc).__name__}: {exc}"
            set_last_agent_error(message)
            emit_event(
                event_type="agent_warning",
                actor="benchmark",
                iteration=step + 1,
                warning_type="model_call_failed",
                detail=message,
            )
            return
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        candidate = response.candidates[0] if response.candidates else None
        if candidate and candidate.content:
            _fix_genai_content(candidate.content)
            contents.append(candidate.content)
            thought_parts = [part for part in candidate.content.parts if part.thought]
            for part in thought_parts:
                emit_event(
                    event_type="model_thought",
                    actor="model",
                    iteration=step + 1,
                    thought=part.text.strip() if part.text else "",
                )
                if part.text:
                    llm.send(part.text.strip())

        function_calls = response.function_calls or []
        usage_metadata = getattr(response, "usage_metadata", None)
        emit_event(
            event_type="model_response",
            actor="model",
            iteration=step + 1,
            mode="genai",
            text=response.text or "",
            tool_calls=[{"name": fc.name, "args": dict(fc.args or {})} for fc in function_calls],
            latency_ms=latency_ms,
            usage_metadata=_json_safe(usage_metadata),
        )
        # Doesn't work
        # _merge_token_usage(metrics, _json_safe(usage_metadata))
        if not function_calls:
            # Advanced task exits as soon as the model responds with a simple text without tool calling
            if exit_expected or advanced:
                break

            text = response.text or ""
            if text:
                llm.send(text)
            emit_event(
                event_type="agent_warning",
                actor="benchmark",
                iteration=step + 1,
                warning_type="no_function_call",
                detail=text,
            )
            contents.append(types.Content(role="user", parts=[types.Part(text=NOT_A_TOOLCALL_PROMPT)]))
            actors.user.send(NOT_A_TOOLCALL_PROMPT)
            step += 1
            continue

        stop = False
        response_parts: list[types.Part] = []
        for fc in function_calls:
            args = dict(fc.args or {})
            llm.send(f"Tool {fc.name} called with args: {args}")
            result, should_stop = _dispatch_tool(fc.name, args, tools)
            stop = stop or should_stop
            response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        id=getattr(fc, "id", None),
                        name=fc.name,
                        response=result,
                    )
                )
            )
            _tool_actor.send(json.dumps(result))

        contents.append(types.Content(role="user", parts=response_parts))
        if stop:
            if advanced:
                break

            exit_expected = True
            step += 1
            continue

        status = _get_status(server_url)
        _update_run_metrics_from_status(metrics, status, iteration=step + 1)
        if status and status.get("done") and not advanced:
            exit_expected = True

        if step >= max_steps:
            if advanced:
                emit_event(
                    event_type="agent_warning",
                    actor="benchmark",
                    warning_type="max_steps_reached",
                    detail=f"Max steps reached: agent didn't finish in {max_steps} steps.",
                )
                break

            exit_expected = True
        if step >= 2 * max_steps:
            emit_event(
                event_type="agent_warning",
                actor="benchmark",
                warning_type="max_steps_reached",
                detail=f"Max steps reached: agent didn't complete main.py updates in {max_steps} steps.",
            )
            break

        step += 1

    status = _get_status(server_url)
    _emit_run_end(
        metrics,
        iteration=step + 1,
        score=status["online"],
        max_score=status["total"],
        done=status["done"],
    )


def run_agent_loop(
    llm,
    server_url: str,
    server_url_for_model: str,
    vfs: VirtualFileSystem,
    outer_welcome_message: str,
    max_steps: int = DEFAULT_MAX_STEPS,
    terminal_spec: str | None = None,
    seed: int | None = None,
    advanced: bool = False,
) -> int:
    """Execute the agentic loop against the terminal server at server_url.

    Returns number of iterations.
    """
    set_last_agent_error(None)
    metrics = RunTelemetry()
    metrics.started_at = datetime.now().isoformat()
    set_last_run_metrics(metrics)
    vfs.bind_run_metrics(metrics)
    resolved_server_url = _resolve_server_url(server_url)
    resolved_server_url_for_model = _resolve_server_url(server_url_for_model)
    get_run_logger().set_iteration(None)
    _update_run_metrics_from_status(metrics, _get_status(resolved_server_url), iteration=0)
    system_prompt = make_system_prompt(resolved_server_url_for_model, outer_welcome_message, advanced)
    tools = _make_bound_tools(vfs)
    emit_event(
        event_type="run_start",
        actor="benchmark",
        model=getattr(llm, "model", type(llm).__name__),
        terminal_spec=terminal_spec,
        seed=seed,
        server_url=resolved_server_url,
        max_steps=max_steps,
        system_prompt=system_prompt,
        tool_definitions=MANUAL_TOOL_SCHEMAS,
        vfs_root=vfs.root.as_posix(),
    )

    with chats.new(name=terminal_spec, system_instructions=system_prompt):
        if isinstance(llm, GoogleGenAI):
            _run_genai_tool_loop(
                llm,
                system_prompt,
                tools,
                resolved_server_url,
                metrics,
                max_steps,
                advanced,
            )
        else:
            _run_openai_compatible_manual_tool_loop(
                llm, tools, resolved_server_url, metrics, max_steps, system_prompt, advanced,
            )

    status = _get_status(resolved_server_url)
    if status is None:
        _emit_run_end(
            metrics,
            iteration=metrics.iterations,
            score=0,
            max_score=1,
            done=False,
        )
        _emit_run_summary(
            metrics,
            iteration=metrics.iterations,
            score=0,
            max_score=1,
            done=False,
            agent_error=get_last_agent_error(),
        )
        get_run_logger().set_iteration(None)
        return metrics.iterations
    _update_run_metrics_from_status(metrics, status, iteration=metrics.iterations)
    _emit_run_end(
        metrics,
        iteration=metrics.iterations,
        score=status["online"],
        max_score=status["total"],
        done=status.get("done", False),
    )
    _emit_run_summary(
        metrics,
        iteration=metrics.iterations,
        score=status["online"],
        max_score=status["total"],
        done=status.get("done", False),
        agent_error=get_last_agent_error(),
    )
    get_run_logger().set_iteration(None)
    return metrics.iterations
