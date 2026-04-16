from benchmark.task_generator import CompositeTaskGenerator, TaskGenerator, TaskSpecGenerator
from server.terminal_spec import TerminalBySpecBuilder
from server.terminals import MainTerminal, MazeTerminal, Sys32Terminal
from server.terminals.sys32.sys32_terminal import _make_token


class StaticTaskGenerator(TaskGenerator):
    def __init__(self, tasks):
        self._tasks = list(tasks)

    def get_tasks(self):
        return list(self._tasks)


def test_task_spec_generator_builds_requested_number_of_tasks():
    generator = TaskSpecGenerator("sys32", tasks_count=3, base_seed=10)

    tasks = list(generator.get_tasks())

    assert len(tasks) == 3
    assert [type(task) for task in tasks] == [Sys32Terminal, Sys32Terminal, Sys32Terminal]
    assert [task.terminal_id for task in tasks] == ["SYS1", "SYS1", "SYS1"]
    assert [type(task.child_terminal) for task in tasks] == [MainTerminal, MainTerminal, MainTerminal]
    assert [task.child_terminal.terminal_id for task in tasks] == ["SYS2", "SYS2", "SYS2"]
    assert [task._token for task in tasks] == [  # noqa: SLF001
        _make_token(11),
        _make_token(12),
        _make_token(13),
    ]


def test_task_spec_generator_accepts_parsed_terminal_spec():
    spec = TerminalBySpecBuilder().parse_terminal_spec("sys32|maze")
    generator = TaskSpecGenerator(spec, tasks_count=2, base_seed=0)

    tasks = list(generator.get_tasks())

    assert [type(task) for task in tasks] == [MazeTerminal, Sys32Terminal]


def test_composite_task_generator_shuffles_tasks_deterministically():
    generator = CompositeTaskGenerator(
        generators=[
            StaticTaskGenerator(["a1", "a2"]),
            StaticTaskGenerator(["b1"]),
        ],
        tasks_count=3,
        base_seed=7,
    )

    assert list(generator.get_tasks()) == ["b1", "a1", "a2"]


def test_composite_task_generator_truncates_to_requested_task_count():
    generator = CompositeTaskGenerator(
        generators=[StaticTaskGenerator(["a", "b", "c", "d"])],
        tasks_count=2,
        base_seed=0,
    )

    assert list(generator.get_tasks()) == ["c", "a"]
