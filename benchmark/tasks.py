import asyncio
import contextlib
import random
import socket
import threading
import time

import kaggle_benchmarks as kbench
import requests
import uvicorn
from kaggle_benchmarks import envs, LLMChat

import server.app as app_module
from benchmark.infrastructure import VirtualFileSystem, run_agent_loop, get_run_logger, emit_event, _get_status
from benchmark.persistent_folder import PersistentFolder
from benchmark.task_generator import TaskGenerator, TaskSpecGenerator, CompositeTaskGenerator
from server.base_terminal import BaseTerminal
from server.sessions import Session
from server.terminal_spec import TerminalBySpecBuilder
from server.terminals import MainTerminal, DummyTerminal, Sys32Terminal, BitMixerTerminal, HashTerminal, CipherTerminal, \
    MazeTerminal

TERMINAL_BUILDER = TerminalBySpecBuilder()


class TaskEnvironment:
    server_host = "127.0.0.1"

    def __init__(self, outer_terminal: BaseTerminal | None = None):
        if outer_terminal is None:
            outer_terminal = MainTerminal("SYS1", seed=42)

        session = Session(outer_terminal=outer_terminal, run_logger=get_run_logger())
        app_module.session = session

        self.srv = self._start_server_on_free_port()
        self.vfs = VirtualFileSystem()

        self.port = self.srv.config.port
        self.server_url = f"http://127.0.0.1:{self.port}"
        self.server_url_for_model = f"http://{TaskEnvironment.server_host}:{self.port}"
        self.persistent_folder = PersistentFolder(self.vfs.root)

    @classmethod
    def override_server_host(cls, host: str):
        cls.server_host = host

    def exit(self):
        self.srv.should_exit = True
        app_module.session = None

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.exit()

    @staticmethod
    def _find_free_port() -> int:
        with socket.socket() as s:
            s.bind(("0.0.0.0", 0))
            return s.getsockname()[1]

    def _start_server_on_free_port(self) -> uvicorn.Server:
        port = self._find_free_port()

        config = uvicorn.Config(app_module.app, host="0.0.0.0", port=port, log_level="error")
        srv = uvicorn.Server(config)
        thread = threading.Thread(
            target=lambda: asyncio.run(srv.serve()),
            daemon=True,
        )
        thread.start()

        url = f"http://127.0.0.1:{port}/status"
        for _ in range(50):
            try:
                requests.get(url, timeout=0.5)
                break
            except Exception:
                time.sleep(0.1)

        return srv

    @staticmethod
    def replace_outer_terminal_on_server_and_reset(outer_terminal: BaseTerminal):
        outer_terminal.reset()
        app_module.session.replace_outer_terminal(outer_terminal)

    @staticmethod
    @contextlib.contextmanager
    def disable_logging_on_server():
        with app_module.session.disable_logging():
            yield

    @staticmethod
    @contextlib.contextmanager
    def use_separate_logger_on_server():
        with app_module.session.with_logger() as logger:
            yield logger


def _find_easiest_unsolved_task(env: TaskEnvironment, tasks_by_generator: list[list[BaseTerminal]]) -> tuple[int, int] | tuple[None, None]:
    checkpoint_id = env.persistent_folder.save_checkpoint()

    number_of_passed_terminals = 0
    for generator_index, generator_tasks in enumerate(tasks_by_generator):
        for task_index, task in enumerate(generator_tasks):
            env.persistent_folder.restore(checkpoint_id)
            env.replace_outer_terminal_on_server_and_reset(task)

            # emit_event(event_type="validation", actor="benchmark", iteration=None,
            #            terminal_spec=str(task), main_py=env.vfs.read("main.py"))

            with env.use_separate_logger_on_server() as logger:
                start_time = time.time()
                try:
                    run_result = envs.current.run("python main.py", input=None)
                except Exception as e:
                    run_result = envs.RunResult(exit_code=-1, stdout="", stderr=str(e))
                elapsed_time = time.time() - start_time

            status = _get_status(env.server_url)

            if not status.get("done", False):
                # Log terminal events for the failed task
                for entry in logger.entries:
                    d = entry.to_dict()
                    d.update(actor="terminal", payload=d["message"])
                    del d["message"]
                    emit_event(**d, force_emit_to_console=True)

                env.persistent_folder.restore(checkpoint_id)

                emit_event(event_type="validation_result", actor="benchmark",
                           iteration=None,
                           terminal_spec=str(task),
                           exit_code=run_result.exit_code,
                           elapsed_time=elapsed_time,
                           stdout=run_result.stdout,
                           stderr=run_result.stderr,
                           status=status)

                emit_event(event_type="validation_summary", actor="benchmark",
                           iteration=None,
                           number_of_passed_validating_terminals=number_of_passed_terminals,
                           total=sum(len(generator_tasks) for generator_tasks in tasks_by_generator),
                           failed_on_generator=generator_index,
                           failed_on_task=task_index)

                return generator_index, task_index

            number_of_passed_terminals += 1

    env.persistent_folder.restore(checkpoint_id)
    emit_event(event_type="validation_summary", actor="benchmark",
               iteration=None,
               number_of_passed_validating_terminals=number_of_passed_terminals,
               total=sum(len(generator_tasks) for generator_tasks in tasks_by_generator))
    return None, None


@kbench.task(
    name="Adaptive Learning",
    description="Assesses the model’s capacity for cross-run learning and progress retention "
                "by presenting increasingly complex versions of a task.",
)
def adaptive_learning(
    llm,
    generators: list[TaskGenerator] | None = None,
    max_attempts_per_generator: int = 5,
    advanced: bool = False,
) -> float:
    if generators is None:
        terminal_classes = {"T0": DummyTerminal}
        rnd = random.Random(42)
        generators = [
            TaskSpecGenerator("T0", terminal_classes, base_seed=rnd.randint(0, 1000000)),
        ]

    tasks_by_generator = [list(generator.get_tasks()) for generator in generators]
    attempts_by_generator = [0] * len(generators)

    best_score = 0.0
    total_iterations_spent = 0

    with TaskEnvironment() as env:
        while True:
            generator_index, task_index = _find_easiest_unsolved_task(env, tasks_by_generator)

            fully_passed_generators = generator_index if generator_index is not None else len(generators)
            if fully_passed_generators > 0:
                fine = min(99, total_iterations_spent / fully_passed_generators)
                score = 100 * fully_passed_generators - fine
            else:
                score = 0.0
            if score > best_score:
                best_score = score
            emit_event(event_type="benchmark_current_score", actor="benchmark",
                       score=score, best_score=best_score, attempts=attempts_by_generator)

            # Success!                 or Fail - too many attempts!
            if generator_index is None or attempts_by_generator[generator_index] >= max_attempts_per_generator:
                return float(best_score)

            terminal = tasks_by_generator[generator_index][task_index]
            attempts_by_generator[generator_index] += 1

            env.replace_outer_terminal_on_server_and_reset(terminal)

            total_iterations_spent += run_agent_loop(
                llm,
                env.server_url,
                env.server_url_for_model,
                env.vfs,
                outer_welcome_message=terminal.get_welcome_message(),
                max_steps=100,
                terminal_spec=str(terminal),
                advanced=advanced,
            )


@kbench.task(
    name="Advanced Adaptive Learning",
    description="Assesses the model’s capacity for cross-run learning and progress retention "
                "by presenting increasingly complex versions of a task.",
)
def advanced_adaptive_learning(
    llm,
    generators: list[TaskGenerator] | None = None,
    max_attempts_per_generator: int = 5,
) -> float:
    return adaptive_learning(llm, generators, max_attempts_per_generator, advanced=True)


def run_adaptive_learning(llm: LLMChat, advanced: bool = False):
    """
    A wrapper for running adaptive_learning task with our desired configuration.
    """
    terminal_classes = {
        "T1": Sys32Terminal,
        "T2": BitMixerTerminal,
        "T3": CipherTerminal,
        "T4": HashTerminal,
        "T5": MazeTerminal,
    }
    rnd = random.Random(42)  # Deterministic for all models

    def _generator_factory(spec: str):
        return TaskSpecGenerator(spec, terminal_classes, base_seed=rnd.randint(0, 1000000))

    generators = [
        _generator_factory("T1"),
        _generator_factory("T1 - T1"),
        _generator_factory("T1 - T1 - T1"),
        _generator_factory("T2 - T1 - T1"),
        _generator_factory("T1|T2 - T1|T2 - T1|T2"),
        _generator_factory("T1|T2 - T1|T2 - T1|T2 - T1|T2"),
        _generator_factory("T1|T2 - T3 - T1|T2 - T1|T2"),
        _generator_factory("T1|T2|T3 - T1|T2|T3 - T4 - T1|T2|T3"),
        _generator_factory("T1|T2|T3|T4 - T1|T2|T3|T4 - T1|T2|T3|T4 - T5"),
        CompositeTaskGenerator([
            _generator_factory(" - ".join(["T1|T2|T3|T4|T5"] * count))
            for count in range(1, 5)
        ])
    ]
    if not advanced:
        adaptive_learning.run(llm, generators=generators)
    else:
        advanced_adaptive_learning.run(llm, generators=generators)
