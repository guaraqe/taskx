"""Interfaces shared by Taskwarrior adapters and command handlers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from taskx.model import Task


@dataclass(frozen=True, slots=True)
class TaskwarriorCommandResult:
    """Captured shell-free subprocess output."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class Taskwarrior(Protocol):
    """Task operations available to command handlers.

    Implementations own UUID-prefix resolution and must scope every operation
    to the exact project supplied by the caller.
    """

    def ready(self, project: str) -> list[Task]: ...

    def list_pending(self, project: str) -> list[Task]: ...

    def get(self, project: str, reference: str) -> Task: ...

    def add(
        self,
        project: str,
        description: str,
        actor: str,
        dependencies: Sequence[str] = (),
    ) -> Task: ...

    def start(self, project: str, reference: str, actor: str) -> Task: ...

    def release(
        self, project: str, reference: str, reason: str | None = None
    ) -> Task: ...

    def done(self, project: str, reference: str, actor: str) -> Task: ...

    def note(self, project: str, reference: str, text: str) -> Task: ...

    def set_dependency(
        self,
        project: str,
        reference: str,
        dependency: str,
        *,
        add: bool,
    ) -> Task: ...
