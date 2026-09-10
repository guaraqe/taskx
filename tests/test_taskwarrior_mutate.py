"""Tests for TaskwarriorMutator: fake-runner behavior and real integration."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from taskx.errors import (
    ConflictError,
    LockTimeoutError,
    PostconditionError,
    TaskNotFoundError,
    TaskwarriorError,
    UsageError,
)
from taskx.locking import DEFAULT_TIMEOUT_SECONDS, MutationLock, lock_path
from taskx.taskwarrior.contracts import TaskwarriorCommandResult
from taskx.taskwarrior.mutate import TaskwarriorMutator
from taskx.taskwarrior.process import TaskwarriorProcess
from taskx.taskwarrior.read import TaskwarriorReader

PROJECT = "demo"
DEP = "3f6ba832-1c2d-4e1f-9a0b-5c6d7e8f9a0b"
MAIN = "b21f4c60-8d3e-4f5a-8c1b-2d3e4f5a6b7c"
FOREIGN = "c9d8e7f6-5a4b-3c2d-1e0f-a9b8c7d6e5f4"

_FLAGS = ("+READY", "-ACTIVE", "+BLOCKED")
_HIDDEN = ("status.not:completed", "status.not:deleted")


def raw_task(uuid: str, **overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "uuid": uuid,
        "description": f"task {uuid[:4]}",
        "project": PROJECT,
        "status": "pending",
        "entry": "20260910T000000Z",
    }
    raw.update(overrides)
    return raw


def future_timestamp() -> str:
    moment = datetime.now(UTC) + timedelta(days=1)
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _split_literal(argv: tuple[str, ...]) -> tuple[Sequence[str], list[str]]:
    if "--" in argv:
        split = argv.index("--")
        return argv[:split], list(argv[split + 1 :])
    return argv, []


def _mod_value(mods: Sequence[str], key: str) -> str | None:
    for mod in mods:
        name, separator, value = mod.partition(":")
        if separator and name == key:
            return value
    return None


def _depends_values(mods: Sequence[str]) -> list[str]:
    values: list[str] = []
    for mod in mods:
        name, separator, value = mod.partition(":")
        if separator and name == "depends":
            values.extend(part for part in value.split(",") if part)
    return values


def _is_blocked(tasks: Mapping[str, dict[str, Any]], raw: Mapping[str, Any]) -> bool:
    return any(
        dependency in tasks
        and tasks[dependency]["status"] not in ("completed", "deleted")
        for dependency in raw.get("depends", ())
    )


def _future_scheduled(raw: Mapping[str, Any]) -> bool:
    scheduled = raw.get("scheduled")
    if not scheduled:
        return False
    moment = datetime.strptime(scheduled, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    return moment > datetime.now(UTC)


def _is_ready(
    tasks: Mapping[str, dict[str, Any]],
    raw: Mapping[str, Any],
    blocked: frozenset[str],
    active: bool,
) -> bool:
    if raw["status"] != "pending" or active or raw["uuid"] in blocked:
        return False
    if raw.get("wait"):
        return False
    return not _future_scheduled(raw)


def _export_json(tasks: Mapping[str, dict[str, Any]], terms: Sequence[str]) -> str:
    project = next(
        term[len("project.is:") :] for term in terms if term.startswith("project.is:")
    )
    rest = [term for term in terms if not term.startswith("project.is:")]
    flags = {term for term in rest if term in _FLAGS}
    hidden = {term for term in rest if term in _HIDDEN}
    references = [term for term in rest if term not in flags and term not in hidden]
    blocked = frozenset(uuid for uuid, raw in tasks.items() if _is_blocked(tasks, raw))
    selected: list[dict[str, Any]] = []
    for raw in tasks.values():
        if raw["project"] != project:
            continue
        if references and not any(raw["uuid"].startswith(item) for item in references):
            continue
        if "status.not:completed" in hidden and raw["status"] == "completed":
            continue
        if "status.not:deleted" in hidden and raw["status"] == "deleted":
            continue
        active = raw["status"] == "pending" and bool(raw.get("start"))
        if "-ACTIVE" in flags and active:
            continue
        if "+BLOCKED" in flags and raw["uuid"] not in blocked:
            continue
        if "+READY" in flags and not _is_ready(tasks, raw, blocked, active):
            continue
        selected.append(raw)
    return "".join(json.dumps(raw) + "\n" for raw in selected)


class FakeTaskwarrior(TaskwarriorProcess):
    """In-memory Taskwarrior that records argv and applies state changes."""

    commands = frozenset(("add", "start", "stop", "done", "annotate", "modify"))

    def __init__(
        self,
        env: Mapping[str, str],
        tasks: Sequence[dict[str, Any]] = (),
        *,
        ignore_writes: bool = False,
    ) -> None:
        super().__init__()
        self._lock_env = env
        self.tasks: dict[str, dict[str, Any]] = {
            raw["uuid"]: dict(raw) for raw in tasks
        }
        self.calls: list[tuple[str, ...]] = []
        self.ignore_writes = ignore_writes

    def run(
        self,
        arguments: Sequence[str],
        *,
        check: bool = True,
        input_text: str | None = None,
    ) -> TaskwarriorCommandResult:
        argv = tuple(arguments)
        self.calls.append(argv)
        assert_lock_held(self._lock_env)
        result = self._dispatch(argv)
        if check and result.returncode != 0:
            raise TaskwarriorError(
                result.stderr.strip() or result.stdout.strip() or "Taskwarrior failed"
            )
        return result

    def _dispatch(self, argv: tuple[str, ...]) -> TaskwarriorCommandResult:
        head, literal = _split_literal(argv)
        args = [item for item in head if not item.startswith("rc.")]
        if args and args[-1] == "export":
            return self._result(_export_json(self.tasks, args[:-1]))
        command = next(item for item in args if item in self.commands)
        index = args.index(command)
        mods = args[index + 1 :]
        if command == "add":
            return self._do_add(mods, literal)
        target = self._target(args[:index])
        if target is None:
            return self._result("", returncode=1, stderr="No tasks matched.\n")
        if self.ignore_writes:
            return self._result("")
        if command == "start":
            target["start"] = "20260910T010000Z"
        elif command == "stop":
            target.pop("start", None)
        elif command == "done":
            target["status"] = "completed"
            target["end"] = "20260910T020000Z"
            target.pop("start", None)
        elif command == "annotate":
            annotations = target.setdefault("annotations", [])
            annotations.append(
                {"entry": "20260910T030000Z", "description": " ".join(literal)}
            )
        self._apply_mods(target, mods)
        return self._result("")

    def _do_add(
        self, mods: Sequence[str], literal: Sequence[str]
    ) -> TaskwarriorCommandResult:
        if self.ignore_writes:
            return self._result("")
        uuid = str(uuid4())
        raw: dict[str, Any] = {
            "uuid": uuid,
            "description": " ".join(literal),
            "project": _mod_value(mods, "project"),
            "status": "pending",
            "entry": "20260910T000000Z",
        }
        dependencies = _depends_values(mods)
        if dependencies:
            raw["depends"] = dependencies
        for key in ("taskx_created_by", "taskx_started_by", "taskx_closed_by"):
            value = _mod_value(mods, key)
            if value is not None:
                raw[key] = value
        self.tasks[uuid] = raw
        return self._result(f"Created task {uuid}.\n")

    def _apply_mods(self, target: dict[str, Any], mods: Sequence[str]) -> None:
        for mod in mods:
            name, separator, value = mod.partition(":")
            if not separator:
                continue
            if name == "depends":
                self._change_dependency(target, value)
            else:
                target[name] = value

    def _change_dependency(self, target: dict[str, Any], value: str) -> None:
        remove = value.startswith("-")
        dependency = value[1:] if remove else value
        depends = list(target.get("depends", ()))
        if remove:
            if dependency in depends:
                depends.remove(dependency)
        else:
            blocker = self.tasks.get(dependency)
            if blocker is not None and target["uuid"] in blocker.get("depends", ()):
                raise TaskwarriorError("circular dependency detected")
            if dependency not in depends:
                depends.append(dependency)
        if depends:
            target["depends"] = depends
        else:
            target.pop("depends", None)

    def _target(self, filters: Sequence[str]) -> dict[str, Any] | None:
        project = next(
            item[len("project.is:") :]
            for item in filters
            if item.startswith("project.is:")
        )
        references = [item for item in filters if not item.startswith("project.is:")]
        reference = references[0] if references else ""
        for raw in self.tasks.values():
            if raw["project"] == project and raw["uuid"].startswith(reference):
                return raw
        return None

    def _result(
        self, stdout: str, *, returncode: int = 0, stderr: str = ""
    ) -> TaskwarriorCommandResult:
        return TaskwarriorCommandResult(
            argv=(), returncode=returncode, stdout=stdout, stderr=stderr
        )


def assert_lock_held(env: Mapping[str, str]) -> None:
    path = lock_path(env)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        raise AssertionError(f"mutation ran outside the mutation lock: {path}")
    finally:
        os.close(descriptor)


def assert_lock_free(env: Mapping[str, str]) -> None:
    path = lock_path(env)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def fake_env(tmp_path: Path) -> dict[str, str]:
    return {"TASKDATA": str(tmp_path / "task-data")}


def build(
    tmp_path: Path,
    tasks: Sequence[dict[str, Any]] = (),
    *,
    ignore_writes: bool = False,
) -> tuple[TaskwarriorMutator, FakeTaskwarrior]:
    env = fake_env(tmp_path)
    process = FakeTaskwarrior(env, tasks, ignore_writes=ignore_writes)
    mutator = TaskwarriorMutator(process, TaskwarriorReader(process), env=env)
    return mutator, process


def active_task() -> dict[str, Any]:
    return raw_task(MAIN, start="20260910T010000Z", taskx_started_by="codex:s0")


def test_add_passes_literal_description_and_attribution(tmp_path: Path) -> None:
    mutator, process = build(tmp_path, [raw_task(DEP)])

    task = mutator.add(
        PROJECT,
        "Ship +urgent project:fake due:tomorrow",
        "codex:s1",
        dependencies=[DEP[:8]],
    )

    assert task.description == "Ship +urgent project:fake due:tomorrow"
    assert task.project == PROJECT
    assert task.created_by == "codex:s1"
    assert task.depends == (DEP,)
    add_call = next(call for call in process.calls if "add" in call)
    assert add_call[-2:] == ("--", "Ship +urgent project:fake due:tomorrow")
    assert "rc.verbose=new-uuid" in add_call
    assert f"project:{PROJECT}" in add_call
    assert "taskx_created_by:codex:s1" in add_call
    assert f"depends:{DEP}" in add_call


def test_add_rejects_blank_description(tmp_path: Path) -> None:
    mutator, process = build(tmp_path)

    with pytest.raises(UsageError):
        mutator.add(PROJECT, "   ", "codex:s1")

    assert process.calls == []


def test_add_rejects_foreign_dependency(tmp_path: Path) -> None:
    mutator, _ = build(tmp_path, [raw_task(FOREIGN, project="other")])

    with pytest.raises(TaskNotFoundError):
        mutator.add(PROJECT, "needs foreign", "codex:s1", dependencies=[FOREIGN])


def test_start_sets_attribution(tmp_path: Path) -> None:
    mutator, process = build(tmp_path, [raw_task(MAIN)])

    task = mutator.start(PROJECT, MAIN[:8], "codex:s1")

    assert task.active is True
    assert task.started_by == "codex:s1"
    start_call = next(call for call in process.calls if call[-2] == "start")
    assert start_call == (
        f"project.is:{PROJECT}",
        MAIN,
        "start",
        "taskx_started_by:codex:s1",
    )


@pytest.mark.parametrize(
    ("overrides", "expected_error", "fragment"),
    [
        (
            {"start": "20260910T010000Z", "taskx_started_by": "codex:s0"},
            ConflictError,
            "already active",
        ),
        ({"depends": [DEP]}, ConflictError, "blocked"),
        ({"status": "waiting"}, ConflictError, "waiting"),
        ({"scheduled": future_timestamp()}, ConflictError, "scheduled"),
        ({"status": "completed"}, TaskNotFoundError, "not found"),
    ],
)
def test_start_refuses_unavailable_tasks(
    tmp_path: Path,
    overrides: dict[str, Any],
    expected_error: type[Exception],
    fragment: str,
) -> None:
    mutator, _ = build(tmp_path, [raw_task(MAIN, **overrides), raw_task(DEP)])

    with pytest.raises(expected_error, match=fragment):
        mutator.start(PROJECT, MAIN, "codex:s1")


def test_start_missing_task_raises_not_found(tmp_path: Path) -> None:
    mutator, _ = build(tmp_path)

    with pytest.raises(TaskNotFoundError):
        mutator.start(PROJECT, MAIN, "codex:s1")


def test_start_detects_failed_activation(tmp_path: Path) -> None:
    mutator, _ = build(tmp_path, [raw_task(MAIN)], ignore_writes=True)

    with pytest.raises(PostconditionError):
        mutator.start(PROJECT, MAIN, "codex:s1")


def test_release_stops_retains_started_by_and_annotates(
    tmp_path: Path,
) -> None:
    mutator, process = build(tmp_path, [active_task()])

    task = mutator.release(PROJECT, MAIN, reason="blocked on upstream +review")

    assert task.active is False
    assert task.started_by == "codex:s0"
    assert task.annotations[-1].description == "blocked on upstream +review"
    assert (f"project.is:{PROJECT}", MAIN, "stop") in process.calls
    assert (
        f"project.is:{PROJECT}",
        MAIN,
        "annotate",
        "--",
        "blocked on upstream +review",
    ) in process.calls


def test_release_without_reason_only_stops(tmp_path: Path) -> None:
    mutator, process = build(tmp_path, [active_task()])

    task = mutator.release(PROJECT, MAIN)

    assert task.active is False
    assert task.started_by == "codex:s0"
    assert not any("annotate" in call for call in process.calls)


def test_release_refuses_inactive_task(tmp_path: Path) -> None:
    mutator, _ = build(tmp_path, [raw_task(MAIN)])

    with pytest.raises(ConflictError, match="not active"):
        mutator.release(PROJECT, MAIN)


def test_done_completes_with_closed_by_via_history_export(
    tmp_path: Path,
) -> None:
    mutator, process = build(tmp_path, [active_task()])
    reader = TaskwarriorReader(process)

    task = mutator.done(PROJECT, MAIN, "codex:s1")

    assert task.status == "completed"
    assert task.closed_by == "codex:s1"
    assert task.started_by == "codex:s0"
    assert process.calls[-1] == (
        f"project.is:{PROJECT}",
        MAIN,
        "rc.json.array=off",
        "export",
    )
    with MutationLock(lock_path(fake_env(tmp_path))), pytest.raises(TaskNotFoundError):
        reader.get(PROJECT, MAIN)


def test_done_refuses_task_not_started_through_taskx(tmp_path: Path) -> None:
    mutator, _ = build(tmp_path, [raw_task(MAIN, start="20260910T010000Z")])

    with pytest.raises(ConflictError, match="not started through taskx"):
        mutator.done(PROJECT, MAIN, "codex:s1")


def test_done_refuses_inactive_task(tmp_path: Path) -> None:
    mutator, _ = build(tmp_path, [raw_task(MAIN)])

    with pytest.raises(ConflictError, match="not active"):
        mutator.done(PROJECT, MAIN, "codex:s1")


def test_done_detects_failed_completion(tmp_path: Path) -> None:
    mutator, _ = build(tmp_path, [active_task()], ignore_writes=True)

    with pytest.raises(PostconditionError):
        mutator.done(PROJECT, MAIN, "codex:s1")


def test_note_records_literal_annotation(tmp_path: Path) -> None:
    mutator, process = build(tmp_path, [raw_task(MAIN)])
    text = "Design: docs/parser.md +followup project:none"

    task = mutator.note(PROJECT, MAIN, text)

    assert any(item.description == text for item in task.annotations)
    assert (f"project.is:{PROJECT}", MAIN, "annotate", "--", text) in (process.calls)


def test_note_detects_failed_annotation(tmp_path: Path) -> None:
    mutator, _ = build(tmp_path, [raw_task(MAIN)], ignore_writes=True)

    with pytest.raises(PostconditionError):
        mutator.note(PROJECT, MAIN, "note")


def test_note_rejects_blank_text(tmp_path: Path) -> None:
    mutator, process = build(tmp_path, [raw_task(MAIN)])

    with pytest.raises(UsageError):
        mutator.note(PROJECT, MAIN, "   ")

    assert process.calls == []


def test_set_dependency_adds_and_removes(tmp_path: Path) -> None:
    mutator, process = build(tmp_path, [raw_task(MAIN), raw_task(DEP)])

    task = mutator.set_dependency(PROJECT, MAIN, DEP[:8], add=True)
    assert task.depends == (DEP,)
    assert (
        f"project.is:{PROJECT}",
        MAIN,
        "modify",
        f"depends:{DEP}",
    ) in process.calls

    task = mutator.set_dependency(PROJECT, MAIN, DEP, add=False)
    assert task.depends == ()
    assert (
        f"project.is:{PROJECT}",
        MAIN,
        "modify",
        f"depends:-{DEP}",
    ) in process.calls


def test_set_dependency_rejects_self(tmp_path: Path) -> None:
    mutator, _ = build(tmp_path, [raw_task(MAIN)])

    with pytest.raises(UsageError, match="itself"):
        mutator.set_dependency(PROJECT, MAIN, MAIN[:8], add=True)


def test_set_dependency_rejects_foreign_task(tmp_path: Path) -> None:
    mutator, _ = build(tmp_path, [raw_task(MAIN), raw_task(FOREIGN, project="other")])

    with pytest.raises(TaskNotFoundError):
        mutator.set_dependency(PROJECT, MAIN, FOREIGN, add=True)


def test_set_dependency_reports_cycles_as_taskwarrior_errors(
    tmp_path: Path,
) -> None:
    mutator, _ = build(tmp_path, [raw_task(MAIN, depends=[DEP]), raw_task(DEP)])

    with pytest.raises(TaskwarriorError):
        mutator.set_dependency(PROJECT, DEP, MAIN, add=True)


def test_set_dependency_detects_failed_update(tmp_path: Path) -> None:
    mutator, _ = build(tmp_path, [raw_task(MAIN), raw_task(DEP)], ignore_writes=True)

    with pytest.raises(PostconditionError):
        mutator.set_dependency(PROJECT, MAIN, DEP, add=True)


def test_lock_released_after_conflict(tmp_path: Path) -> None:
    mutator, _ = build(tmp_path, [raw_task(MAIN)])

    with pytest.raises(ConflictError, match="not active"):
        mutator.release(PROJECT, MAIN)

    assert_lock_free(fake_env(tmp_path))


def test_lock_timeout_is_honored(tmp_path: Path) -> None:
    env = fake_env(tmp_path)
    holder = MutationLock(lock_path(env))
    holder.acquire(1.0)
    try:
        process = FakeTaskwarrior(env, [raw_task(MAIN)])
        mutator = TaskwarriorMutator(
            process,
            TaskwarriorReader(process),
            env=env,
            lock_timeout=0.05,
        )

        with pytest.raises(LockTimeoutError):
            mutator.note(PROJECT, MAIN, "text")

        assert process.calls == []
    finally:
        holder.release()


def integration(
    taskwarrior_env: Mapping[str, str],
    *,
    lock_timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[TaskwarriorMutator, TaskwarriorReader]:
    process = TaskwarriorProcess.from_environment(env=taskwarrior_env)
    reader = TaskwarriorReader(process)
    return (
        TaskwarriorMutator(
            process, reader, env=taskwarrior_env, lock_timeout=lock_timeout
        ),
        reader,
    )


def test_integration_add_keeps_modifier_like_description_literal(
    taskwarrior_env: Mapping[str, str],
) -> None:
    mutator, reader = integration(taskwarrior_env)
    text = "Ship +urgent project:fake due:tomorrow"

    task = mutator.add(PROJECT, text, "codex:s1")

    assert task.description == text
    assert task.project == PROJECT
    assert task.created_by == "codex:s1"
    stored = {item.description: item for item in reader.list_pending(PROJECT)}
    assert text in stored
    assert stored[text].created_by == "codex:s1"


def test_integration_add_dependencies_block_new_task(
    taskwarrior_env: Mapping[str, str],
) -> None:
    mutator, reader = integration(taskwarrior_env)
    blocker = mutator.add(PROJECT, "blocker", "codex:s1")

    task = mutator.add(
        PROJECT, "blocked goal", "codex:s1", dependencies=[blocker.uuid[:8]]
    )

    assert task.depends == (blocker.uuid,)
    assert reader.get(PROJECT, task.uuid).blocked is True


def test_integration_start_claim_conflicts_and_ready_exclusion(
    taskwarrior_env: Mapping[str, str],
) -> None:
    mutator, reader = integration(taskwarrior_env)
    task = mutator.add(PROJECT, "claim me", "codex:s1")

    started = mutator.start(PROJECT, task.uuid, "codex:s1")

    assert started.active is True
    assert started.started_by == "codex:s1"
    assert all(item.uuid != task.uuid for item in reader.ready(PROJECT))
    with pytest.raises(ConflictError, match="already active"):
        mutator.start(PROJECT, task.uuid, "codex:s2")


def test_integration_start_refuses_unavailable_tasks(
    taskwarrior_env: Mapping[str, str],
    run_task: Any,
) -> None:
    mutator, reader = integration(taskwarrior_env)
    blocker = mutator.add(PROJECT, "blocker", "codex:s1")
    mutator.add(PROJECT, "blocked goal", "codex:s1", dependencies=[blocker.uuid])
    run_task(["add", "waiter", f"project:{PROJECT}", "wait:1day"])
    run_task(["add", "future", f"project:{PROJECT}", "scheduled:1day"])
    tasks = {item.description: item for item in reader.list_pending(PROJECT)}

    with pytest.raises(ConflictError, match="blocked by"):
        mutator.start(PROJECT, tasks["blocked goal"].uuid, "codex:s1")
    with pytest.raises(ConflictError, match="waiting"):
        mutator.start(PROJECT, tasks["waiter"].uuid, "codex:s1")
    with pytest.raises(ConflictError, match="scheduled"):
        mutator.start(PROJECT, tasks["future"].uuid, "codex:s1")
    with pytest.raises(TaskNotFoundError):
        mutator.start(PROJECT, MAIN, "codex:s1")


def test_integration_release_retains_started_by_and_reason(
    taskwarrior_env: Mapping[str, str],
) -> None:
    mutator, reader = integration(taskwarrior_env)
    task = mutator.add(PROJECT, "release me", "codex:s1")
    mutator.start(PROJECT, task.uuid, "codex:s1")

    released = mutator.release(PROJECT, task.uuid, reason="waiting on +review decision")

    assert released.active is False
    assert released.started_by == "codex:s1"
    assert any(
        item.description == "waiting on +review decision"
        for item in released.annotations
    )
    again = mutator.start(PROJECT, task.uuid, "codex:s2")
    assert again.active is True
    assert again.started_by == "codex:s2"
    assert reader.get(PROJECT, task.uuid).started_by == "codex:s2"


def test_integration_done_records_closer_and_hides_history(
    taskwarrior_env: Mapping[str, str],
) -> None:
    mutator, reader = integration(taskwarrior_env)
    task = mutator.add(PROJECT, "finish me", "codex:s1")
    mutator.start(PROJECT, task.uuid, "codex:s1")

    completed = mutator.done(PROJECT, task.uuid, "codex:s2")

    assert completed.status == "completed"
    assert completed.closed_by == "codex:s2"
    assert completed.started_by == "codex:s1"
    with pytest.raises(TaskNotFoundError):
        reader.get(PROJECT, task.uuid)
    assert all(item.uuid != task.uuid for item in reader.list_pending(PROJECT))


def test_integration_done_requires_active_taskx_start(
    taskwarrior_env: Mapping[str, str],
    run_task: Any,
) -> None:
    mutator, reader = integration(taskwarrior_env)
    pending = mutator.add(PROJECT, "never started", "codex:s1")
    direct = mutator.add(PROJECT, "started outside taskx", "codex:s1")
    released = mutator.add(PROJECT, "released early", "codex:s1")
    run_task([direct.uuid, "start"])
    mutator.start(PROJECT, released.uuid, "codex:s1")
    mutator.release(PROJECT, released.uuid)
    assert reader.get(PROJECT, direct.uuid).active is True
    assert reader.get(PROJECT, direct.uuid).started_by is None

    with pytest.raises(ConflictError, match="not active"):
        mutator.done(PROJECT, pending.uuid, "codex:s1")
    with pytest.raises(ConflictError, match="not started through taskx"):
        mutator.done(PROJECT, direct.uuid, "codex:s1")
    with pytest.raises(ConflictError, match="not active"):
        mutator.done(PROJECT, released.uuid, "codex:s1")


def test_integration_note_stores_literal_annotation(
    taskwarrior_env: Mapping[str, str],
) -> None:
    mutator, reader = integration(taskwarrior_env)
    task = mutator.add(PROJECT, "noted", "codex:s1")
    text = "Design: docs/parser.md +docs project:none"

    noted = mutator.note(PROJECT, task.uuid, text)

    assert any(item.description == text for item in noted.annotations)
    assert reader.get(PROJECT, task.uuid).annotations[-1].description == text


def test_integration_dependencies_add_remove_self_cross_cycle(
    taskwarrior_env: Mapping[str, str],
    run_task: Any,
) -> None:
    mutator, reader = integration(taskwarrior_env)
    one = mutator.add(PROJECT, "one", "codex:s1")
    two = mutator.add(PROJECT, "two", "codex:s1")
    run_task(["add", "foreign", "project:other"])
    foreign = {item.description: item for item in reader.list_pending("other")}[
        "foreign"
    ]

    with pytest.raises(UsageError, match="itself"):
        mutator.set_dependency(PROJECT, one.uuid, one.uuid, add=True)
    with pytest.raises(TaskNotFoundError):
        mutator.set_dependency(PROJECT, one.uuid, foreign.uuid, add=True)

    linked = mutator.set_dependency(PROJECT, one.uuid, two.uuid, add=True)
    assert linked.depends == (two.uuid,)
    assert reader.get(PROJECT, one.uuid).blocked is True

    unlinked = mutator.set_dependency(PROJECT, one.uuid, two.uuid, add=False)
    assert unlinked.depends == ()

    mutator.set_dependency(PROJECT, one.uuid, two.uuid, add=True)
    with pytest.raises(TaskwarriorError):
        mutator.set_dependency(PROJECT, two.uuid, one.uuid, add=True)


def test_integration_lock_guards_and_times_out(
    taskwarrior_env: Mapping[str, str],
) -> None:
    holder = MutationLock.for_environment(taskwarrior_env)
    holder.acquire(1.0)
    try:
        mutator, _ = integration(taskwarrior_env, lock_timeout=0.05)

        with pytest.raises(LockTimeoutError):
            mutator.add(PROJECT, "locked out", "codex:s1")
    finally:
        holder.release()
