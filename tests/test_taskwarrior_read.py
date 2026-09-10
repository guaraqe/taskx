from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pytest

from taskx.errors import TaskNotFoundError, TaskwarriorError, UsageError
from taskx.model import Task
from taskx.taskwarrior.contracts import TaskwarriorCommandResult
from taskx.taskwarrior.process import TaskwarriorProcess
from taskx.taskwarrior.read import TaskwarriorReader

ONE = "a6b27bd9-24d0-4695-afc9-fe1c9c53f437"
TWO = "025cb316-ddbc-42d0-a29f-3d31c6a858d9"
THREE = "a6b2aaaa-3333-3333-3333-333333333333"


class RecordingProcess(TaskwarriorProcess):
    """Fake process runner that records queries and replays responses."""

    def __init__(self, responses: Sequence[TaskwarriorCommandResult]) -> None:
        super().__init__()
        self.calls: list[tuple[str, ...]] = []
        self._responses = iter(responses)

    def run(
        self,
        arguments: Sequence[str],
        *,
        check: bool = True,
        input_text: str | None = None,
    ) -> TaskwarriorCommandResult:
        self.calls.append(tuple(arguments))
        return next(self._responses)


def result(stdout: str) -> TaskwarriorCommandResult:
    return TaskwarriorCommandResult(argv=(), returncode=0, stdout=stdout, stderr="")


def raw_task(uuid: str, **overrides: object) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "uuid": uuid,
        "description": f"task {uuid[:4]}",
        "project": "demo",
        "status": "pending",
        "entry": "20260910T000000Z",
    }
    raw.update(overrides)
    return raw


def jsonl(*items: dict[str, Any]) -> str:
    return "".join(json.dumps(item) + "\n" for item in items)


def test_ready_uses_readiness_filters_and_marks_unblocked() -> None:
    process = RecordingProcess([result(jsonl(raw_task(ONE, start="20260910T010000Z")))])
    reader = TaskwarriorReader(process)

    tasks = reader.ready("demo")

    assert process.calls == [
        ("project.is:demo", "+READY", "-ACTIVE", "rc.json.array=off", "export")
    ]
    assert [task.uuid for task in tasks] == [ONE]
    assert tasks[0].blocked is False
    assert tasks[0].active is True


def test_list_pending_merges_blocked_state_and_preserves_order() -> None:
    process = RecordingProcess(
        [
            result(jsonl(raw_task(ONE), raw_task(TWO))),
            result(jsonl(raw_task(TWO))),
        ]
    )
    reader = TaskwarriorReader(process)

    tasks = reader.list_pending("demo")

    assert [task.uuid for task in tasks] == [ONE, TWO]
    assert [task.blocked for task in tasks] == [False, True]
    assert process.calls[1] == (
        "project.is:demo",
        "status.not:completed",
        "status.not:deleted",
        "+BLOCKED",
        "rc.json.array=off",
        "export",
    )


def test_list_pending_handles_empty_output() -> None:
    process = RecordingProcess([result(""), result("")])

    assert TaskwarriorReader(process).list_pending("demo") == []


def test_get_resolves_unique_prefix_and_reports_blocked() -> None:
    process = RecordingProcess(
        [
            result(jsonl(raw_task(ONE), raw_task(TWO))),
            result(jsonl(raw_task(TWO))),
        ]
    )

    task = TaskwarriorReader(process).get("demo", "025c")

    assert task.uuid == TWO
    assert task.blocked is True


def test_get_missing_reference_raises_not_found() -> None:
    process = RecordingProcess([result(jsonl(raw_task(ONE)))])

    with pytest.raises(TaskNotFoundError, match="ffffffff"):
        TaskwarriorReader(process).get("demo", "ffffffff")


def test_get_completed_or_foreign_tasks_are_not_exposed() -> None:
    process = RecordingProcess([result(jsonl(raw_task(ONE)))])

    with pytest.raises(TaskNotFoundError):
        TaskwarriorReader(process).get("demo", TWO)


def test_get_ambiguous_prefix_raises_usage_error() -> None:
    process = RecordingProcess([result(jsonl(raw_task(ONE), raw_task(THREE)))])

    with pytest.raises(UsageError, match="ambiguous"):
        TaskwarriorReader(process).get("demo", "a6b2")


def test_malformed_export_output_raises_expected_error() -> None:
    for broken in ("{not json", "7", "null", "[1, 2]"):
        process = RecordingProcess([result(broken)])

        with pytest.raises(TaskwarriorError, match="invalid Taskwarrior export"):
            TaskwarriorReader(process).ready("demo")


def reader(taskwarrior_env: Mapping[str, str]) -> TaskwarriorReader:
    process = TaskwarriorProcess.from_environment(env=taskwarrior_env)
    return TaskwarriorReader(process)


def by_description(tasks: list[Task]) -> dict[str, Task]:
    return {task.description: task for task in tasks}


def test_ready_integration_scopes_and_excludes_claims(
    taskwarrior_env: Mapping[str, str],
    run_task: Callable[[Sequence[str]], Any],
) -> None:
    run_task(["add", "open", "project:demo"])
    run_task(["add", "blocked", "project:demo", "depends:1"])
    run_task(["add", "claimed", "project:demo"])
    run_task(["add", "waiter", "project:demo", "wait:1day"])
    run_task(["add", "outside", "project:other"])
    tasks = by_description(reader(taskwarrior_env).list_pending("demo"))
    run_task([tasks["claimed"].uuid, "start"])

    ready = reader(taskwarrior_env).ready("demo")

    assert [task.description for task in ready] == ["open"]
    assert all(task.blocked is False for task in ready)
    assert all(task.active is False for task in ready)


def test_list_pending_integration_lifecycle_and_flags(
    taskwarrior_env: Mapping[str, str],
    run_task: Callable[[Sequence[str]], Any],
) -> None:
    run_task(["add", "open", "project:demo"])
    run_task(["add", "blocked", "project:demo", "depends:1"])
    run_task(["add", "waiter", "project:demo", "wait:1day"])
    run_task(["add", "foreign", "project:other"])
    task_reader = reader(taskwarrior_env)

    tasks = by_description(task_reader.list_pending("demo"))

    assert set(tasks) == {"open", "blocked", "waiter"}
    assert {name: task.blocked for name, task in tasks.items()} == {
        "open": False,
        "blocked": True,
        "waiter": False,
    }
    assert tasks["waiter"].waiting is True

    run_task([tasks["open"].uuid, "done"])

    tasks = by_description(task_reader.list_pending("demo"))
    assert "open" not in tasks
    assert tasks["blocked"].blocked is False

    run_task([tasks["blocked"].uuid, "delete"])

    assert set(by_description(task_reader.list_pending("demo"))) == {"waiter"}


def test_get_integration_prefixes_and_isolation(
    taskwarrior_env: Mapping[str, str],
    run_task: Callable[[Sequence[str]], Any],
) -> None:
    run_task(["add", "open", "project:demo"])
    run_task(["add", "blocked", "project:demo", "depends:1"])
    run_task(["add", "doomed", "project:demo"])
    run_task(["add", "foreign", "project:other"])
    task_reader = reader(taskwarrior_env)
    tasks = by_description(task_reader.list_pending("demo"))
    foreign = by_description(task_reader.list_pending("other"))["foreign"]
    run_task([tasks["doomed"].uuid, "done"])

    full = task_reader.get("demo", tasks["blocked"].uuid)
    prefix = task_reader.get("demo", tasks["blocked"].uuid[:8])

    assert full.uuid == prefix.uuid == tasks["blocked"].uuid
    assert full.blocked is True
    assert prefix.blocked is True

    with pytest.raises(TaskNotFoundError):
        task_reader.get("demo", tasks["doomed"].uuid)
    with pytest.raises(TaskNotFoundError):
        task_reader.get("demo", foreign.uuid)
