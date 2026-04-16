import abc
import random
from typing import Mapping, Iterable

from server.base_terminal import BaseTerminal
from server.terminal_spec import TerminalBySpecBuilder, TerminalChainSpec


class TaskGenerator(abc.ABC):
    @abc.abstractmethod
    def get_tasks(self) -> list[BaseTerminal]:
        ...


class TaskSpecGenerator(TaskGenerator):
    def __init__(
        self,
        spec: str | TerminalChainSpec,
        terminal_classes: Mapping[str, type[BaseTerminal]] | None = None,
        tasks_count: int = 50,
        base_seed: int = 42,
    ):
        self._spec = spec
        self._builder = TerminalBySpecBuilder(terminal_classes)
        self._tasks_count = tasks_count
        self._base_seed = base_seed

    def get_tasks(self) -> Iterable[BaseTerminal]:
        for iteration in range(self._tasks_count):
            yield self._builder.build(self._spec, default_seed=self._base_seed + iteration)


class CompositeTaskGenerator(TaskGenerator):
    def __init__(
        self,
        generators: Iterable[TaskGenerator],
        tasks_count: int = 50,
        base_seed: int = 42,
    ):
        self._tasks_count = tasks_count

        self._tasks = [task for generator in generators for task in generator.get_tasks() ]
        self._random = random.Random(base_seed)
        self._random.shuffle(self._tasks)

    def get_tasks(self) -> Iterable[BaseTerminal]:
        return self._tasks[:self._tasks_count]
