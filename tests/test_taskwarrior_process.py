from __future__ import annotations

import subprocess

import pytest

from taskx.errors import TaskwarriorError
from taskx.taskwarrior.process import UDA_OVERRIDES, TaskwarriorProcess


def test_runner_uses_shell_free_runtime_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_run(
        argv: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        seen["argv"] = argv
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "[]\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = TaskwarriorProcess(env={"TASKDATA": "/tmp/tasks"}).run(
        ["project.is:demo", "export"]
    )

    assert result.stdout == "[]\n"
    assert seen["argv"] == (
        "task",
        "rc.context=",
        "rc.confirmation=off",
        *UDA_OVERRIDES,
        "project.is:demo",
        "export",
    )
    assert seen["check"] is False
    assert seen["capture_output"] is True
    assert seen["text"] is True
    assert "shell" not in seen


def test_runner_turns_nonzero_status_into_expected_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        argv: tuple[str, ...], **_: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, "", "task failed\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(TaskwarriorError, match="task failed"):
        TaskwarriorProcess().run(["export"])


def test_runner_can_return_structured_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        argv: tuple[str, ...], **_: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 4, "bad output", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = TaskwarriorProcess().run(["export"], check=False)

    assert result.returncode == 4
    assert result.stdout == "bad output"
