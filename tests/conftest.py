from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Return an initialized repository without relying on global Git config."""

    repo = tmp_path / "project"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--quiet", str(repo)],
        check=True,
        text=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def taskwarrior_env(tmp_path: Path) -> Mapping[str, str]:
    """Isolate Taskwarrior completely from the developer's configuration/data."""

    if shutil.which("task") is None:
        pytest.skip("Taskwarrior executable is not available")

    data = tmp_path / "task-data"
    data.mkdir(mode=0o700)
    taskrc = tmp_path / "taskrc"
    taskrc.write_text("confirmation=no\ncontext=\n", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "TASKDATA": str(data),
            "TASKRC": str(taskrc),
            "TASKX_ACTOR": "test:fixture",
        }
    )
    return env


@pytest.fixture
def run_task(
    taskwarrior_env: Mapping[str, str],
) -> Callable[[Sequence[str]], subprocess.CompletedProcess[str]]:
    """Run Taskwarrior with the isolated test environment."""

    def run(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["task", "rc.context=", *arguments],
            check=False,
            capture_output=True,
            text=True,
            env=taskwarrior_env,
        )

    return run
