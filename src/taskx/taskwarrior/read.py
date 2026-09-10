"""Read-only, project-scoped Taskwarrior adapter operations."""

from __future__ import annotations

import json
from typing import Any

from taskx.errors import TaskwarriorError
from taskx.identifiers import resolve_uuid_prefix
from taskx.model import Task
from taskx.project import project_filter
from taskx.taskwarrior.normalize import normalize_task
from taskx.taskwarrior.process import TaskwarriorProcess

_VISIBLE_FILTER = ("status.not:completed", "status.not:deleted")
_READY_FILTER = ("+READY", "-ACTIVE")


class TaskwarriorReader:
    """Read operations scoped to one exact Taskwarrior project.

    Every query includes the exact ``project.is:<project>`` filter and runs
    shell-free through the injected process runner, whose runtime arguments
    already disable Taskwarrior contexts.
    """

    def __init__(self, process: TaskwarriorProcess) -> None:
        self._process = process

    def ready(self, project: str) -> list[Task]:
        """Return unclaimed, actionable pending tasks for *project*.

        Uses Taskwarrior's ``+READY`` semantics (pending, not blocked, not
        waiting, not scheduled for the future) and explicitly excludes
        active tasks, which are treated as claimed by another actor.
        """

        raw_tasks = self._export(project, *_READY_FILTER)
        return [normalize_task(raw, blocked=False) for raw in raw_tasks]

    def list_pending(self, project: str) -> list[Task]:
        """Return the visible pending and waiting tasks for *project*.

        Completed and deleted tasks are always excluded. Each task carries
        the blocked state calculated by Taskwarrior.
        """

        raw_tasks = self._export(project, *_VISIBLE_FILTER)
        blocked = self._blocked_uuids(project)
        return [
            normalize_task(raw, blocked=raw["uuid"] in blocked) for raw in raw_tasks
        ]

    def get(self, project: str, reference: str) -> Task:
        """Return one visible project task by full or unique UUID prefix.

        Only the normal pending/waiting project set is searchable, so
        references resolving to completed, deleted, or foreign-project
        tasks raise ``TaskNotFoundError``.
        """

        raw_tasks = self._export(project, *_VISIBLE_FILTER)
        uuid = resolve_uuid_prefix(reference, [raw["uuid"] for raw in raw_tasks])
        blocked = self._blocked_uuids(project)
        raw = next(item for item in raw_tasks if item["uuid"] == uuid)
        return normalize_task(raw, blocked=uuid in blocked)

    def _blocked_uuids(self, project: str) -> frozenset[str]:
        raw_tasks = self._export(project, *_VISIBLE_FILTER, "+BLOCKED")
        return frozenset(raw["uuid"] for raw in raw_tasks)

    def _export(self, project: str, *filter_terms: str) -> list[dict[str, Any]]:
        result = self._process.run(
            (project_filter(project), *filter_terms, "rc.json.array=off", "export")
        )
        return _parse_export(result.stdout)


def _parse_export(stdout: str) -> list[dict[str, Any]]:
    """Parse one JSON object per line, rejecting any malformed output."""

    tasks: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError as error:
            raise TaskwarriorError(
                f"invalid Taskwarrior export output: {error}"
            ) from error
        if not isinstance(item, dict):
            raise TaskwarriorError(
                "invalid Taskwarrior export output: expected one JSON object per line"
            )
        tasks.append(item)
    return tasks
