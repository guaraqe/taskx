from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from io import StringIO
from typing import Any

import pytest

from taskx.cli import build_parser
from taskx.commands.contracts import CommandContext, CommandHandler
from taskx.commands.lifecycle import run
from taskx.errors import ConflictError, TaskNotFoundError, TaskxError, UsageError
from taskx.model import Task
from taskx.taskwarrior import Taskwarrior

UUID = "80b65cb1-5fd2-4efa-b4a8-ebe17346b69c"


def sample_task(**overrides: Any) -> Task:
    values: dict[str, Any] = {
        "uuid": UUID,
        "description": "Implement evaluator",
        "project": "demo",
        "status": "pending",
    }
    values.update(overrides)
    return Task(**values)


class RecordingTaskwarrior:
    """Protocol-conforming stub recording lifecycle calls."""

    def __init__(self, task: Task, error: TaskxError | None = None) -> None:
        self.task = task
        self.error = error
        self.start_calls: list[tuple[str, str, str]] = []
        self.release_calls: list[tuple[str, str, str | None]] = []
        self.done_calls: list[tuple[str, str, str]] = []

    def _fail(self) -> None:
        if self.error is not None:
            raise self.error

    def start(self, project: str, reference: str, actor: str) -> Task:
        self._fail()
        self.start_calls.append((project, reference, actor))
        return self.task

    def release(self, project: str, reference: str, reason: str | None = None) -> Task:
        self._fail()
        self.release_calls.append((project, reference, reason))
        return self.task

    def done(self, project: str, reference: str, actor: str) -> Task:
        self._fail()
        self.done_calls.append((project, reference, actor))
        return self.task

    def ready(self, project: str) -> list[Task]:
        raise NotImplementedError

    def list_pending(self, project: str) -> list[Task]:
        raise NotImplementedError

    def get(self, project: str, reference: str) -> Task:
        raise NotImplementedError

    def add(
        self,
        project: str,
        description: str,
        actor: str,
        dependencies: Sequence[str] = (),
    ) -> Task:
        raise NotImplementedError

    def note(self, project: str, reference: str, text: str) -> Task:
        raise NotImplementedError

    def set_dependency(
        self,
        project: str,
        reference: str,
        dependency: str,
        *,
        add: bool,
    ) -> Task:
        raise NotImplementedError


def make_setup(
    argv: Sequence[str], adapter: Taskwarrior
) -> tuple[argparse.Namespace, CommandContext, StringIO]:
    args = build_parser().parse_args(argv)
    stream = StringIO()
    context = CommandContext(
        project="demo",
        actor="human:juan",
        taskwarrior=adapter,
        stdout=stream,
    )
    return args, context, stream


def test_run_satisfies_command_handler_protocol() -> None:
    handler: CommandHandler = run

    assert handler is run


def test_start_maps_project_uuid_and_actor() -> None:
    task = sample_task(active=True, started_by="human:juan")
    adapter = RecordingTaskwarrior(task)
    args, context, stream = make_setup(["start", UUID], adapter)

    assert run(args, context) == 0
    assert adapter.start_calls == [("demo", UUID, "human:juan")]
    assert stream.getvalue() == f"started {UUID}\n"


def test_start_json_prints_normalized_task() -> None:
    task = sample_task(active=True, started_by="codex:abc")
    adapter = RecordingTaskwarrior(task)
    args, context, stream = make_setup(["start", UUID, "--json"], adapter)

    assert run(args, context) == 0
    value = json.loads(stream.getvalue())
    assert value == task.to_dict()
    assert value["started_by"] == "codex:abc"
    assert "id" not in value


def test_release_maps_reason_and_prints_released_uuid() -> None:
    adapter = RecordingTaskwarrior(sample_task())
    args, context, stream = make_setup(
        ["release", UUID, "--reason", "Waiting for API decision"], adapter
    )

    assert run(args, context) == 0
    assert adapter.release_calls == [("demo", UUID, "Waiting for API decision")]
    assert stream.getvalue() == f"released {UUID}\n"


def test_release_without_reason_passes_none() -> None:
    adapter = RecordingTaskwarrior(sample_task())
    args, context, stream = make_setup(["release", UUID], adapter)

    assert run(args, context) == 0
    assert adapter.release_calls == [("demo", UUID, None)]
    assert stream.getvalue() == f"released {UUID}\n"


def test_release_json_prints_normalized_task() -> None:
    task = sample_task(started_by="human:juan")
    adapter = RecordingTaskwarrior(task)
    args, context, stream = make_setup(["release", UUID, "--json"], adapter)

    assert run(args, context) == 0
    value = json.loads(stream.getvalue())
    assert value == task.to_dict()
    assert value["started_by"] == "human:juan"
    assert "id" not in value


def test_done_maps_project_uuid_and_actor() -> None:
    task = sample_task(
        status="completed",
        end="20260910T010000Z",
        closed_by="human:juan",
    )
    adapter = RecordingTaskwarrior(task)
    args, context, stream = make_setup(["done", UUID], adapter)

    assert run(args, context) == 0
    assert adapter.done_calls == [("demo", UUID, "human:juan")]
    assert stream.getvalue() == f"completed {UUID}\n"


def test_done_json_prints_normalized_task_with_attribution() -> None:
    task = sample_task(
        status="completed",
        end="20260910T010000Z",
        started_by="codex:abc",
        closed_by="human:juan",
    )
    adapter = RecordingTaskwarrior(task)
    args, context, stream = make_setup(["done", UUID, "--json"], adapter)

    assert run(args, context) == 0
    value = json.loads(stream.getvalue())
    assert value == task.to_dict()
    assert value["closed_by"] == "human:juan"
    assert "id" not in value


def test_adapter_exceptions_propagate_unchanged() -> None:
    conflict = RecordingTaskwarrior(
        sample_task(), error=ConflictError("task is already active")
    )
    start_args, start_context, start_stream = make_setup(["start", UUID], conflict)

    with pytest.raises(ConflictError, match="already active"):
        run(start_args, start_context)
    assert start_stream.getvalue() == ""

    missing = RecordingTaskwarrior(sample_task(), error=TaskNotFoundError("no task"))
    done_args, done_context, done_stream = make_setup(["done", UUID], missing)

    with pytest.raises(TaskNotFoundError):
        run(done_args, done_context)
    assert done_stream.getvalue() == ""


def test_unexpected_command_is_rejected_with_usage_error() -> None:
    adapter = RecordingTaskwarrior(sample_task())
    args = argparse.Namespace(command="ready")
    stream = StringIO()
    context = CommandContext(
        project="demo",
        actor="human:juan",
        taskwarrior=adapter,
        stdout=stream,
    )

    with pytest.raises(UsageError, match="ready"):
        run(args, context)

    assert stream.getvalue() == ""
