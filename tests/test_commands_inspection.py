from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from io import StringIO
from typing import Any

import pytest

from taskx.cli import build_parser
from taskx.commands.contracts import CommandContext, CommandHandler
from taskx.commands.inspection import run
from taskx.errors import UsageError
from taskx.model import Annotation, Task

UUID = "12345678-1111-1111-1111-111111111111"
OTHER = "abcdef00-2222-2222-2222-222222222222"
DEPENDENCY = "352fc723-4178-4775-a05a-cb7c6f28ac51"


class RecordingTaskwarrior:
    """Protocol stub that records read calls and returns canned tasks."""

    def __init__(
        self,
        *,
        ready: Sequence[Task] = (),
        pending: Sequence[Task] = (),
        get: Task | None = None,
    ) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._ready = list(ready)
        self._pending = list(pending)
        self._get = get

    def ready(self, project: str) -> list[Task]:
        self.calls.append(("ready", project))
        return list(self._ready)

    def list_pending(self, project: str) -> list[Task]:
        self.calls.append(("list_pending", project))
        return list(self._pending)

    def get(self, project: str, reference: str) -> Task:
        self.calls.append(("get", project, reference))
        if self._get is None:
            raise AssertionError("unexpected get call")
        return self._get

    def add(
        self,
        project: str,
        description: str,
        actor: str,
        dependencies: Sequence[str] = (),
    ) -> Task:
        raise NotImplementedError

    def start(self, project: str, reference: str, actor: str) -> Task:
        raise NotImplementedError

    def release(self, project: str, reference: str, reason: str | None = None) -> Task:
        raise NotImplementedError

    def done(self, project: str, reference: str, actor: str) -> Task:
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


def sample_task(**overrides: Any) -> Task:
    values: dict[str, Any] = {
        "uuid": UUID,
        "description": "Implement parser",
        "project": "demo",
        "status": "pending",
        "entry": "20260910T000000Z",
    }
    values.update(overrides)
    return Task(**values)


def make_context(
    taskwarrior: RecordingTaskwarrior | None = None,
) -> tuple[CommandContext, StringIO]:
    stream = StringIO()
    context = CommandContext(
        project="demo",
        actor="test:fixture",
        taskwarrior=taskwarrior if taskwarrior is not None else RecordingTaskwarrior(),
        stdout=stream,
    )
    return context, stream


def test_run_satisfies_command_handler_protocol() -> None:
    handler: CommandHandler = run

    assert handler is run


def test_actor_prints_context_actor_and_no_taskwarrior_calls() -> None:
    taskwarrior = RecordingTaskwarrior()
    context, stream = make_context(taskwarrior)

    assert run(build_parser().parse_args(["actor"]), context) == 0

    assert stream.getvalue() == "test:fixture\n"
    assert taskwarrior.calls == []


def test_project_prints_context_project_and_no_taskwarrior_calls() -> None:
    taskwarrior = RecordingTaskwarrior()
    context, stream = make_context(taskwarrior)

    assert run(build_parser().parse_args(["project"]), context) == 0

    assert stream.getvalue() == "demo\n"
    assert taskwarrior.calls == []


def test_ready_prints_concise_lines_for_human_output() -> None:
    tasks = [
        sample_task(),
        sample_task(uuid=OTHER, description="Write docs"),
    ]
    taskwarrior = RecordingTaskwarrior(ready=tasks)
    context, stream = make_context(taskwarrior)

    assert run(build_parser().parse_args(["ready"]), context) == 0

    assert taskwarrior.calls == [("ready", "demo")]
    assert stream.getvalue() == (f"{UUID} Implement parser\n{OTHER} Write docs\n")


def test_list_prints_state_suffixes_for_human_output() -> None:
    tasks = [
        sample_task(active=True, blocked=True),
        sample_task(uuid=OTHER, description="Write docs", waiting=True),
    ]
    taskwarrior = RecordingTaskwarrior(pending=tasks)
    context, stream = make_context(taskwarrior)

    assert run(build_parser().parse_args(["list"]), context) == 0

    assert taskwarrior.calls == [("list_pending", "demo")]
    assert stream.getvalue() == (
        f"{UUID} Implement parser [active, blocked]\n{OTHER} Write docs [waiting]\n"
    )


def test_ready_json_is_the_normalized_model() -> None:
    taskwarrior = RecordingTaskwarrior(ready=[sample_task()])
    context, stream = make_context(taskwarrior)

    assert run(build_parser().parse_args(["ready", "--json"]), context) == 0

    value = json.loads(stream.getvalue())
    assert value == [sample_task().to_dict()]
    assert value[0]["uuid"] == UUID
    assert value[0]["project"] == "demo"
    assert "id" not in value[0]
    assert "urgency" not in value[0]


def test_list_json_is_a_normalized_array() -> None:
    tasks = [
        sample_task(),
        sample_task(uuid=OTHER, description="Write docs", waiting=True),
    ]
    taskwarrior = RecordingTaskwarrior(pending=tasks)
    context, stream = make_context(taskwarrior)

    assert run(build_parser().parse_args(["list", "--json"]), context) == 0

    value = json.loads(stream.getvalue())
    assert value == [task.to_dict() for task in tasks]
    assert all("id" not in item for item in value)


def test_show_passes_project_and_reference_and_prints_details() -> None:
    task = sample_task(
        depends=(DEPENDENCY,),
        created_by="test:fixture",
        annotations=(Annotation(entry=None, description="context"),),
    )
    taskwarrior = RecordingTaskwarrior(get=task)
    context, stream = make_context(taskwarrior)

    assert run(build_parser().parse_args(["show", "12345678"]), context) == 0

    assert taskwarrior.calls == [("get", "demo", "12345678")]
    assert stream.getvalue() == (
        f"uuid: {UUID}\n"
        "description: Implement parser\n"
        "project: demo\n"
        "status: pending\n"
        "active: false\n"
        "blocked: false\n"
        "waiting: false\n"
        f"depends: {DEPENDENCY}\n"
        "created: 20260910T000000Z\n"
        "created_by: test:fixture\n"
        "note: context\n"
    )


def test_show_json_is_the_normalized_model() -> None:
    task = sample_task(started_by="codex:abc")
    taskwarrior = RecordingTaskwarrior(get=task)
    context, stream = make_context(taskwarrior)

    assert run(build_parser().parse_args(["show", UUID, "--json"]), context) == 0

    value = json.loads(stream.getvalue())
    assert value == task.to_dict()
    assert value["started_by"] == "codex:abc"
    assert "id" not in value


def test_unexpected_command_raises_usage_error() -> None:
    context, _ = make_context()

    with pytest.raises(UsageError, match="unexpected inspection command"):
        run(argparse.Namespace(command="bogus"), context)
