from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from io import StringIO

import pytest

from taskx.commands.contracts import CommandContext, CommandHandler
from taskx.commands.creation import run
from taskx.errors import TaskNotFoundError, TaskxError, UsageError
from taskx.model import Task
from taskx.taskwarrior import Taskwarrior

UUID = "80b65cb1-5fd2-4efa-b4a8-ebe17346b69c"
DEPENDENCY = "352fc723-4178-4775-a05a-cb7c6f28ac51"


def sample_task() -> Task:
    return Task(
        uuid=UUID,
        description="Implement evaluator",
        project="demo",
        status="pending",
    )


class RecordingTaskwarrior:
    """Protocol-conforming stub recording creation and context calls."""

    def __init__(self, task: Task, error: TaskxError | None = None) -> None:
        self.task = task
        self.error = error
        self.add_calls: list[tuple[str, str, str, tuple[str, ...]]] = []
        self.note_calls: list[tuple[str, str, str]] = []
        self.dependency_calls: list[tuple[str, str, str, bool]] = []

    def _fail(self) -> None:
        if self.error is not None:
            raise self.error

    def add(
        self,
        project: str,
        description: str,
        actor: str,
        dependencies: Sequence[str] = (),
    ) -> Task:
        self._fail()
        self.add_calls.append((project, description, actor, tuple(dependencies)))
        return self.task

    def note(self, project: str, reference: str, text: str) -> Task:
        self._fail()
        self.note_calls.append((project, reference, text))
        return self.task

    def set_dependency(
        self,
        project: str,
        reference: str,
        dependency: str,
        *,
        add: bool,
    ) -> Task:
        self._fail()
        self.dependency_calls.append((project, reference, dependency, add))
        return self.task

    def ready(self, project: str) -> list[Task]:
        raise NotImplementedError

    def list_pending(self, project: str) -> list[Task]:
        raise NotImplementedError

    def get(self, project: str, reference: str) -> Task:
        raise NotImplementedError

    def start(self, project: str, reference: str, actor: str) -> Task:
        raise NotImplementedError

    def release(self, project: str, reference: str, reason: str | None = None) -> Task:
        raise NotImplementedError

    def done(self, project: str, reference: str, actor: str) -> Task:
        raise NotImplementedError


def make_setup(
    args: argparse.Namespace, adapter: Taskwarrior
) -> tuple[argparse.Namespace, CommandContext, StringIO]:
    stream = StringIO()
    context = CommandContext(
        project="demo",
        actor="human:juan",
        taskwarrior=adapter,
        stdout=stream,
    )
    return args, context, stream


def command_args(command: str, **values: object) -> argparse.Namespace:
    return argparse.Namespace(command=command, **({"json_output": False} | values))


def test_run_satisfies_command_handler_protocol() -> None:
    handler: CommandHandler = run

    assert handler is run


def test_add_maps_arguments_and_prints_created_uuid() -> None:
    adapter = RecordingTaskwarrior(sample_task())
    args, context, stream = make_setup(
        command_args("add", description="Implement evaluator", depends=[DEPENDENCY]),
        adapter,
    )

    assert run(args, context) == 0
    assert adapter.add_calls == [
        ("demo", "Implement evaluator", "human:juan", (DEPENDENCY,))
    ]
    assert stream.getvalue() == f"created {UUID}\n"


def test_add_without_dependencies_passes_empty_collection() -> None:
    adapter = RecordingTaskwarrior(sample_task())
    args, context, stream = make_setup(
        command_args("add", description="Implement parser", depends=[]), adapter
    )

    assert run(args, context) == 0
    assert adapter.add_calls == [("demo", "Implement parser", "human:juan", ())]
    assert stream.getvalue() == f"created {UUID}\n"


def test_add_json_prints_normalized_task() -> None:
    adapter = RecordingTaskwarrior(sample_task())
    args, context, stream = make_setup(
        command_args(
            "add", description="Implement evaluator", depends=[], json_output=True
        ),
        adapter,
    )

    assert run(args, context) == 0
    assert json.loads(stream.getvalue()) == sample_task().to_dict()


def test_note_maps_arguments_and_prints_noted_uuid() -> None:
    adapter = RecordingTaskwarrior(sample_task())
    args, context, stream = make_setup(
        command_args("note", uuid=UUID, text="Design: docs/parser.md"), adapter
    )

    assert run(args, context) == 0
    assert adapter.note_calls == [("demo", UUID, "Design: docs/parser.md")]
    assert stream.getvalue() == f"noted {UUID}\n"


def test_note_json_prints_normalized_task() -> None:
    adapter = RecordingTaskwarrior(sample_task())
    args, context, stream = make_setup(
        command_args("note", uuid=UUID, text="context", json_output=True), adapter
    )

    assert run(args, context) == 0
    assert json.loads(stream.getvalue()) == sample_task().to_dict()


def test_depends_add_maps_arguments_and_prints_updated_uuid() -> None:
    adapter = RecordingTaskwarrior(sample_task())
    args, context, stream = make_setup(
        command_args("depends", uuid=UUID, action="add", dependency_uuid=DEPENDENCY),
        adapter,
    )

    assert run(args, context) == 0
    assert adapter.dependency_calls == [("demo", UUID, DEPENDENCY, True)]
    assert stream.getvalue() == f"updated {UUID}\n"


def test_depends_remove_passes_add_false() -> None:
    adapter = RecordingTaskwarrior(sample_task())
    args, context, stream = make_setup(
        command_args("depends", uuid=UUID, action="remove", dependency_uuid=DEPENDENCY),
        adapter,
    )

    assert run(args, context) == 0
    assert adapter.dependency_calls == [("demo", UUID, DEPENDENCY, False)]
    assert stream.getvalue() == f"updated {UUID}\n"


def test_depends_json_prints_normalized_task() -> None:
    adapter = RecordingTaskwarrior(sample_task())
    args, context, stream = make_setup(
        command_args(
            "depends",
            uuid=UUID,
            action="add",
            dependency_uuid=DEPENDENCY,
            json_output=True,
        ),
        adapter,
    )

    assert run(args, context) == 0
    assert json.loads(stream.getvalue()) == sample_task().to_dict()


def test_adapter_exceptions_propagate_unchanged() -> None:
    adapter = RecordingTaskwarrior(sample_task(), error=TaskNotFoundError("no task"))
    note_args, note_context, _ = make_setup(
        command_args("note", uuid=UUID, text="text"), adapter
    )

    with pytest.raises(TaskNotFoundError):
        run(note_args, note_context)

    conflict_adapter = RecordingTaskwarrior(
        sample_task(), error=UsageError("ambiguous prefix")
    )
    add_args, add_context, _ = make_setup(
        command_args("add", description="description", depends=[]), conflict_adapter
    )

    with pytest.raises(UsageError):
        run(add_args, add_context)


def test_unexpected_command_is_rejected_with_usage_error() -> None:
    adapter = RecordingTaskwarrior(sample_task())
    args = argparse.Namespace(command="start")
    stream = StringIO()
    context = CommandContext(
        project="demo",
        actor="human:juan",
        taskwarrior=adapter,
        stdout=stream,
    )

    with pytest.raises(UsageError, match="start"):
        run(args, context)

    assert stream.getvalue() == ""
