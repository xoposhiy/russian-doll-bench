import contextlib
from types import SimpleNamespace

from benchmark import tasks as tasks_module


class _DummyGenerator:
    def __init__(self, tasks):
        self._tasks = tasks

    def get_tasks(self):
        return list(self._tasks)


def test_find_easiest_unsolved_task_emits_final_validation_summary_on_success(monkeypatch):
    terminal = object()
    events = []
    statuses = iter([{"done": True}])

    class _DummyPersistentFolder:
        def save_checkpoint(self):
            return "checkpoint"

        def restore(self, checkpoint_id):
            return None

    class _DummyEnvironment:
        server_url = "http://127.0.0.1:1"
        persistent_folder = _DummyPersistentFolder()

        @staticmethod
        def replace_outer_terminal_on_server_and_reset(outer_terminal):
            return None

        @staticmethod
        @contextlib.contextmanager
        def use_separate_logger_on_server():
            yield SimpleNamespace(entries=[])

    monkeypatch.setattr(tasks_module.envs, "current", SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(exit_code=0, stdout="", stderr="")))
    monkeypatch.setattr(tasks_module.requests, "post", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(tasks_module, "_get_status", lambda *args, **kwargs: next(statuses))
    monkeypatch.setattr(tasks_module, "emit_event", lambda **kwargs: events.append(kwargs))

    result = tasks_module._find_easiest_unsolved_task(_DummyEnvironment(), [[terminal]])

    assert result == (None, None)
    assert events == [
        {
            "event_type": "validation_summary",
            "actor": "benchmark",
            "iteration": None,
            "number_of_passed_validating_terminals": 1,
            "total": 1,
        }
    ]
