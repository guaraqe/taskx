from __future__ import annotations

import json
import os
from collections.abc import Sequence
from io import StringIO
from pathlib import Path

import pytest

from taskx.cli import build_parser, main
from taskx.commands import dispatch
from taskx.model import Task


class StubTaskwarrior:
    def __init__(self, task: Task) -> None:
        self.task = task
        self.calls: list[tuple[str, ...]] = []

    def ready(self, project: str) -> list[Task]:
        self.calls.append(("ready", project))
        return [self.task]

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


def test_help_and_actor_do_not_require_a_git_repository(tmp_path: Path) -> None:
    adapter = StubTaskwarrior(_task())

    help_output = StringIO()
    assert (
        dispatch(
            build_parser().parse_args(["help", "agent"]),
            cwd=tmp_path,
            env={},
            stdout=help_output,
            taskwarrior=adapter,
        )
        == 0
    )
    assert "taskx ready --json" in help_output.getvalue()

    actor_output = StringIO()
    assert (
        dispatch(
            build_parser().parse_args(["actor"]),
            cwd=tmp_path,
            env={"TASKX_ACTOR": "test:actor"},
            stdout=actor_output,
            taskwarrior=adapter,
        )
        == 0
    )
    assert actor_output.getvalue() == "test:actor\n"


def test_ready_builds_project_and_actor_context(
    git_repo: Path,
) -> None:
    task = _task(project=git_repo.name)
    adapter = StubTaskwarrior(task)
    output = StringIO()

    result = dispatch(
        build_parser().parse_args(["ready", "--json"]),
        cwd=git_repo,
        env=os.environ | {"TASKX_ACTOR": "test:actor"},
        stdout=output,
        taskwarrior=adapter,
    )

    assert result == 0
    assert adapter.calls == [("ready", git_repo.name)]
    assert json.loads(output.getvalue()) == [task.to_dict()]


def test_main_presents_expected_errors_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["ready"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: taskx must be run inside a Git repository\n"


def _task(*, project: str = "demo") -> Task:
    return Task(
        uuid="12345678-1111-1111-1111-111111111111",
        description="Implement parser",
        project=project,
        status="pending",
    )
