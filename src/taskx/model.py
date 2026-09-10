"""Taskwarrior-independent data returned by taskx."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Annotation:
    """A normalized Taskwarrior annotation."""

    entry: str | None
    description: str


@dataclass(frozen=True, slots=True)
class Task:
    """The stable task representation used by commands and JSON output."""

    uuid: str
    description: str
    project: str
    status: str
    active: bool = False
    blocked: bool = False
    waiting: bool = False
    depends: tuple[str, ...] = ()
    annotations: tuple[Annotation, ...] = ()
    entry: str | None = None
    start: str | None = None
    end: str | None = None
    wait: str | None = None
    scheduled: str | None = None
    created_by: str | None = None
    started_by: str | None = None
    closed_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical JSON-compatible representation."""

        value = asdict(self)
        value["depends"] = list(self.depends)
        value["annotations"] = [asdict(item) for item in self.annotations]
        return value


@dataclass(frozen=True, slots=True)
class MutationResult:
    """Successful mutation output before CLI presentation."""

    task: Task
    message: str
    details: dict[str, Any] = field(default_factory=dict)
