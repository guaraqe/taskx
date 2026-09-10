"""Locked, project-scoped Taskwarrior mutation operations."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from taskx.errors import (
    ConflictError,
    PostconditionError,
    TaskNotFoundError,
    TaskwarriorError,
    UsageError,
)
from taskx.identifiers import resolve_uuid_prefix
from taskx.locking import DEFAULT_TIMEOUT_SECONDS, mutation_lock
from taskx.model import Task
from taskx.project import project_filter
from taskx.taskwarrior.normalize import normalize_task
from taskx.taskwarrior.process import TaskwarriorProcess
from taskx.taskwarrior.read import TaskwarriorReader

_NEW_TASK_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)

_TASKX_TIMESTAMP = "%Y%m%dT%H%M%SZ"


class TaskwarriorMutator:
    """Serialized task mutations with enforced pre- and postconditions.

    Every operation holds the taskx mutation lock for its whole duration,
    so validation, the Taskwarrior write, and postcondition verification
    cannot interleave with another taskx process. References are resolved
    through the project-scoped reader, so tasks from other projects are
    never visible and can never be mutated.
    """

    def __init__(
        self,
        process: TaskwarriorProcess,
        reader: TaskwarriorReader,
        *,
        env: Mapping[str, str] | None = None,
        lock_timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._process = process
        self._reader = reader
        self._env = env
        self._lock_timeout = lock_timeout

    def add(
        self,
        project: str,
        description: str,
        actor: str,
        dependencies: Sequence[str] = (),
    ) -> Task:
        """Create a project task attributed to *actor* and return it."""

        def operation() -> Task:
            _require_text(description, "description")
            resolved = tuple(
                self._reader.get(project, reference).uuid for reference in dependencies
            )
            result = self._process.run(
                (
                    "rc.verbose=new-uuid",
                    project_filter(project),
                    "add",
                    f"project:{project}",
                    f"taskx_created_by:{actor}",
                    *(f"depends:{uuid}" for uuid in resolved),
                    "--",
                    description,
                )
            )
            uuid = _new_task_uuid(result.stdout)
            created = self._reader.get(project, uuid)
            if (
                created.project != project
                or created.description != description
                or created.created_by != actor
                or set(created.depends) != set(resolved)
            ):
                raise PostconditionError(
                    f"created task {uuid} does not match the requested task"
                )
            return created

        return self._run_locked(operation)

    def start(self, project: str, reference: str, actor: str) -> Task:
        """Claim a ready task for *actor* and verify the active state."""

        def operation() -> Task:
            uuid = self._startable_uuid(project, reference)
            self._process.run(
                (
                    project_filter(project),
                    uuid,
                    "start",
                    f"taskx_started_by:{actor}",
                )
            )
            task = self._reader.get(project, uuid)
            if not task.active or task.started_by != actor:
                raise PostconditionError(
                    f"start did not activate {uuid} for actor {actor}"
                )
            return task

        return self._run_locked(operation)

    def release(self, project: str, reference: str, reason: str | None = None) -> Task:
        """Stop an active task, optionally recording *reason* as annotation."""

        def operation() -> Task:
            task = self._require_active(project, reference)
            if reason is not None:
                _require_text(reason, "reason")
            self._process.run((project_filter(project), task.uuid, "stop"))
            if reason is not None:
                self._process.run(
                    (
                        project_filter(project),
                        task.uuid,
                        "annotate",
                        "--",
                        reason,
                    )
                )
            released = self._reader.get(project, task.uuid)
            if released.active:
                raise PostconditionError(f"release left {task.uuid} active")
            if task.started_by is not None and (released.started_by != task.started_by):
                raise PostconditionError(
                    f"release lost taskx_started_by on {task.uuid}"
                )
            if reason is not None and not _annotated(released, reason):
                raise PostconditionError(
                    f"release did not record the reason on {task.uuid}"
                )
            return released

        return self._run_locked(operation)

    def done(self, project: str, reference: str, actor: str) -> Task:
        """Complete an active taskx-started task attributed to *actor*."""

        def operation() -> Task:
            task = self._require_active(project, reference)
            if task.started_by is None:
                raise ConflictError(f"task {task.uuid} was not started through taskx")
            self._process.run(
                (
                    project_filter(project),
                    task.uuid,
                    "done",
                    f"taskx_closed_by:{actor}",
                )
            )
            completed = self._export_one(project, task.uuid)
            if completed.status != "completed" or completed.closed_by != actor:
                raise PostconditionError(
                    f"done did not complete {task.uuid} for actor {actor}"
                )
            return completed

        return self._run_locked(operation)

    def note(self, project: str, reference: str, text: str) -> Task:
        """Attach *text* as a literal Taskwarrior annotation."""

        def operation() -> Task:
            _require_text(text, "note text")
            task = self._reader.get(project, reference)
            self._process.run(
                (project_filter(project), task.uuid, "annotate", "--", text)
            )
            annotated = self._reader.get(project, task.uuid)
            if not _annotated(annotated, text):
                raise PostconditionError(f"annotation was not recorded on {task.uuid}")
            return annotated

        return self._run_locked(operation)

    def set_dependency(
        self,
        project: str,
        reference: str,
        dependency: str,
        *,
        add: bool,
    ) -> Task:
        """Add or remove one dependency between two project tasks."""

        def operation() -> Task:
            task = self._reader.get(project, reference)
            blocker = self._reader.get(project, dependency)
            if task.uuid == blocker.uuid:
                raise UsageError(f"task {task.uuid} cannot depend on itself")
            value = blocker.uuid if add else f"-{blocker.uuid}"
            self._process.run(
                (
                    project_filter(project),
                    task.uuid,
                    "modify",
                    f"depends:{value}",
                )
            )
            updated = self._reader.get(project, task.uuid)
            if add != (blocker.uuid in updated.depends):
                change = "record" if add else "remove"
                raise PostconditionError(
                    f"dependency update did not {change} {blocker.uuid} on {task.uuid}"
                )
            return updated

        return self._run_locked(operation)

    def _run_locked(self, operation: Callable[[], Task]) -> Task:
        with mutation_lock(self._env, timeout=self._lock_timeout):
            return operation()

    def _startable_uuid(self, project: str, reference: str) -> str:
        ready = self._reader.ready(project)
        try:
            uuid = resolve_uuid_prefix(reference, [task.uuid for task in ready])
        except TaskNotFoundError:
            task = self._reader.get(project, reference)
            raise ConflictError(_unavailable_reason(task)) from None
        task = next(item for item in ready if item.uuid == uuid)
        _require_actionable(task)
        return uuid

    def _require_active(self, project: str, reference: str) -> Task:
        task = self._reader.get(project, reference)
        if not task.active:
            raise ConflictError(f"task {task.uuid} is not active")
        return task

    def _export_one(self, project: str, uuid: str) -> Task:
        """Export exactly one full-UUID project task, including history.

        The normal visible-set reader excludes completed tasks, so the
        completed postcondition of ``done`` must be verified through this
        exact-project, full-UUID export instead.
        """

        result = self._process.run(
            (project_filter(project), uuid, "rc.json.array=off", "export")
        )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if len(lines) != 1:
            raise PostconditionError(
                f"expected exactly one exported task for {uuid}, found {len(lines)}"
            )
        try:
            raw = json.loads(lines[0])
        except json.JSONDecodeError as error:
            raise TaskwarriorError(
                f"invalid Taskwarrior export output: {error}"
            ) from error
        if not isinstance(raw, dict):
            raise TaskwarriorError(
                "invalid Taskwarrior export output: expected a JSON object"
            )
        return normalize_task(raw)


def _unavailable_reason(task: Task) -> str:
    if task.active:
        owner = f" (started_by: {task.started_by})" if task.started_by else ""
        return f"task is already active{owner}"
    if task.blocked:
        return "task is blocked by incomplete dependencies"
    if task.waiting:
        return "task is waiting"
    if _scheduled_in_future(task):
        return f"task is scheduled for the future ({task.scheduled})"
    return f"task is not ready (status: {task.status})"


def _require_actionable(task: Task) -> None:
    """Defensively re-check readiness even when the ready set contains it."""

    if task.status != "pending":
        raise ConflictError(f"task is not pending (status: {task.status})")
    if task.active:
        raise ConflictError(_unavailable_reason(task))
    if task.blocked:
        raise ConflictError("task is blocked by incomplete dependencies")
    if task.waiting:
        raise ConflictError("task is waiting")
    if _scheduled_in_future(task):
        raise ConflictError(f"task is scheduled for the future ({task.scheduled})")


def _scheduled_in_future(task: Task) -> bool:
    if task.scheduled is None:
        return False
    try:
        scheduled = datetime.strptime(task.scheduled, _TASKX_TIMESTAMP)
    except ValueError:
        return False
    return scheduled.replace(tzinfo=UTC) > datetime.now(UTC)


def _new_task_uuid(stdout: str) -> str:
    match = _NEW_TASK_UUID.search(stdout)
    if match is None:
        raise TaskwarriorError(
            f"could not determine the new task UUID from Taskwarrior output: {stdout!r}"
        )
    return match.group(0)


def _annotated(task: Task, text: str) -> bool:
    return any(item.description == text for item in task.annotations)


def _require_text(value: str, label: str) -> None:
    if not value.strip():
        raise UsageError(f"{label} must not be empty")
