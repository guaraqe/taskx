"""Concrete composition of Taskwarrior read and mutation operations."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from taskx.model import Task
from taskx.taskwarrior.mutate import TaskwarriorMutator
from taskx.taskwarrior.process import TaskwarriorProcess
from taskx.taskwarrior.read import TaskwarriorReader


class TaskwarriorAdapter:
    """The complete project-scoped Taskwarrior boundary used by the CLI."""

    def __init__(
        self,
        process: TaskwarriorProcess,
        *,
        env: Mapping[str, str],
        lock_timeout: float = 10.0,
    ) -> None:
        self._reader = TaskwarriorReader(process)
        self._mutator = TaskwarriorMutator(
            process,
            self._reader,
            env=env,
            lock_timeout=lock_timeout,
        )

    @classmethod
    def from_environment(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        cwd: Path | None = None,
        lock_timeout: float = 10.0,
    ) -> TaskwarriorAdapter:
        environment = dict(os.environ if env is None else env)
        process = TaskwarriorProcess(env=environment, cwd=cwd)
        return cls(process, env=environment, lock_timeout=lock_timeout)

    def ready(self, project: str) -> list[Task]:
        return self._reader.ready(project)

    def list_pending(self, project: str) -> list[Task]:
        return self._reader.list_pending(project)

    def get(self, project: str, reference: str) -> Task:
        return self._reader.get(project, reference)

    def add(
        self,
        project: str,
        description: str,
        actor: str,
        dependencies: Sequence[str] = (),
    ) -> Task:
        return self._mutator.add(project, description, actor, dependencies)

    def start(self, project: str, reference: str, actor: str) -> Task:
        return self._mutator.start(project, reference, actor)

    def release(self, project: str, reference: str, reason: str | None = None) -> Task:
        return self._mutator.release(project, reference, reason)

    def done(self, project: str, reference: str, actor: str) -> Task:
        return self._mutator.done(project, reference, actor)

    def note(self, project: str, reference: str, text: str) -> Task:
        return self._mutator.note(project, reference, text)

    def set_dependency(
        self,
        project: str,
        reference: str,
        dependency: str,
        *,
        add: bool,
    ) -> Task:
        return self._mutator.set_dependency(project, reference, dependency, add=add)
