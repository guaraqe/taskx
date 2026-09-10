"""Subprocess-level black-box tests for the integrated taskx CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

_TIMEOUT_SECONDS = 60.0
_DEFAULT_TASKRC = "confirmation=no\n"
_SOURCE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _require_taskwarrior() -> None:
    if shutil.which("task") is None:
        pytest.skip("Taskwarrior executable is not available")


@dataclass(frozen=True, slots=True)
class Workspace:
    """One temporary Git repository plus a fully isolated Taskwarrior store."""

    root: Path
    env: dict[str, str]


def make_workspace(
    tmp_path: Path,
    *,
    name: str = "demo",
    taskrc_text: str = _DEFAULT_TASKRC,
) -> Workspace:
    """Create a repository and (re)configure the shared isolated store.

    Workspaces built from the same ``tmp_path`` deliberately share one
    Taskwarrior data directory, taskrc, and mutation lock.
    """

    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--quiet", str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    data = tmp_path / "task-data"
    data.mkdir(mode=0o700, exist_ok=True)
    taskrc = tmp_path / "taskrc"
    taskrc.write_text(taskrc_text, encoding="utf-8")
    env = os.environ.copy()
    env.update({"TASKDATA": str(data), "TASKRC": str(taskrc)})
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(_SOURCE_ROOT / "src"), env.get("PYTHONPATH", "")) if part
    )
    return Workspace(root=repo, env=env)


def with_actor(workspace: Workspace, actor: str) -> dict[str, str]:
    env = dict(workspace.env)
    env["TASKX_ACTOR"] = actor
    return env


def run_taskx(
    workspace: Workspace,
    arguments: Sequence[str],
    *,
    actor: str = "human:alice",
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "taskx", *arguments],
        cwd=workspace.root if cwd is None else cwd,
        env=with_actor(workspace, actor),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )


def raw_task(
    workspace: Workspace,
    arguments: Sequence[str],
    *,
    keep_context: bool = False,
) -> subprocess.CompletedProcess[str]:
    prefix = [] if keep_context else ["rc.context="]
    return subprocess.run(
        ["task", *prefix, *arguments],
        cwd=workspace.root,
        env=workspace.env,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )


def export_raw(workspace: Workspace, *filters: str) -> list[dict[str, Any]]:
    result = raw_task(workspace, (*filters, "rc.json.array=off", "export"))
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def add_task(
    workspace: Workspace,
    description: str,
    *,
    actor: str = "human:alice",
) -> dict[str, Any]:
    result = run_taskx(workspace, ["add", description, "--json"], actor=actor)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def listing(
    workspace: Workspace,
    command: str,
    *,
    actor: str = "human:alice",
) -> list[dict[str, Any]]:
    result = run_taskx(workspace, [command, "--json"], actor=actor)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_complete_lifecycle_attribution_and_disappearance(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)

    created = add_task(workspace, "Implement parser", actor="human:alice")
    uuid = str(created["uuid"])
    assert created["created_by"] == "human:alice"
    assert [task["uuid"] for task in listing(workspace, "ready")] == [uuid]

    started = run_taskx(workspace, ["start", uuid], actor="human:alice")
    assert started.returncode == 0, started.stderr
    assert started.stdout == f"started {uuid}\n"

    denied = run_taskx(workspace, ["start", uuid], actor="human:bob")
    assert denied.returncode == 4, denied.stderr
    assert "already active" in denied.stderr
    assert "human:alice" in denied.stderr

    released = run_taskx(
        workspace,
        ["release", uuid, "--reason", "Waiting for API decision"],
        actor="human:alice",
    )
    assert released.returncode == 0, released.stderr
    assert released.stdout == f"released {uuid}\n"
    assert [task["uuid"] for task in listing(workspace, "ready")] == [uuid]

    restarted = run_taskx(workspace, ["start", uuid], actor="human:bob")
    assert restarted.returncode == 0, restarted.stderr

    completed = run_taskx(workspace, ["done", uuid], actor="human:bob")
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == f"completed {uuid}\n"

    assert listing(workspace, "ready") == []
    assert listing(workspace, "list") == []

    raw = export_raw(workspace, f"uuid:{uuid}")
    assert len(raw) == 1
    assert raw[0]["status"] == "completed"
    assert raw[0]["taskx_created_by"] == "human:alice"
    assert raw[0]["taskx_started_by"] == "human:bob"
    assert raw[0]["taskx_closed_by"] == "human:bob"


def test_concurrent_starts_admit_exactly_one_actor(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    task = add_task(workspace, "Contested task")
    uuid = str(task["uuid"])
    actors = ("human:alice", "human:bob")

    processes = [
        subprocess.Popen(
            [sys.executable, "-m", "taskx", "start", uuid],
            cwd=workspace.root,
            env=with_actor(workspace, actor),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for actor in actors
    ]
    outcomes = [process.communicate(timeout=90.0) for process in processes]
    codes = [process.returncode for process in processes]

    assert sorted(codes) == [0, 4]
    winner = actors[codes.index(0)]
    loser_error = outcomes[codes.index(4)][1]
    assert "already active" in loser_error
    assert f"started_by: {winner}" in loser_error

    raw = export_raw(workspace, f"uuid:{uuid}")
    assert raw[0]["taskx_started_by"] == winner
    assert raw[0]["start"]


def test_exact_project_isolation_excludes_hierarchical_names(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path, name="sites")
    exact = add_task(workspace, "Exact project task")
    raw_task(workspace, ["add", "Child project task", "project:sites.alpha"])
    raw_task(workspace, ["add", "Sibling project task", "project:sites.beta"])

    assert [task["uuid"] for task in listing(workspace, "ready")] == [exact["uuid"]]
    assert [task["uuid"] for task in listing(workspace, "list")] == [exact["uuid"]]

    fuzzy = raw_task(
        workspace,
        ["project:sites", "status:pending", "rc.json.array=off", "export"],
    )
    fuzzy_tasks = [line for line in fuzzy.stdout.splitlines() if line.strip()]
    assert len(fuzzy_tasks) == 3


def test_active_taskwarrior_context_does_not_hide_tasks(tmp_path: Path) -> None:
    workspace = make_workspace(
        tmp_path,
        taskrc_text=("confirmation=no\ncontext=work\ncontext.work=project:hidden\n"),
    )
    created = add_task(workspace, "Visible despite context")

    hidden = raw_task(workspace, ["list"], keep_context=True)
    assert "Visible despite context" not in hidden.stdout

    assert [task["uuid"] for task in listing(workspace, "list")] == [created["uuid"]]


def test_modifier_like_add_description_stays_literal(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    text = "status:pending +READY project:hidden depends:1"

    created = add_task(workspace, text)

    shown = run_taskx(workspace, ["show", str(created["uuid"]), "--json"])
    assert shown.returncode == 0, shown.stderr
    value = json.loads(shown.stdout)
    assert value["description"] == text
    assert value["status"] == "pending"
    assert value["depends"] == []

    raw = export_raw(workspace, f"uuid:{created['uuid']}")
    assert raw[0]["description"] == text


def test_note_and_release_reason_remain_literal(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    task = add_task(workspace, "Annotated task")
    uuid = str(task["uuid"])
    note_text = "urgency:10 +important project:fake"
    reason = "project:other +waiting-design"

    noted = run_taskx(workspace, ["note", uuid, note_text])
    assert noted.returncode == 0, noted.stderr
    started = run_taskx(workspace, ["start", uuid])
    assert started.returncode == 0, started.stderr
    released = run_taskx(workspace, ["release", uuid, "--reason", reason])
    assert released.returncode == 0, released.stderr

    shown = json.loads(run_taskx(workspace, ["show", uuid, "--json"]).stdout)
    annotations = [item["description"] for item in shown["annotations"]]
    assert note_text in annotations
    assert reason in annotations

    raw = export_raw(workspace, f"uuid:{uuid}")
    raw_annotations = [item["description"] for item in raw[0].get("annotations", [])]
    assert note_text in raw_annotations
    assert reason in raw_annotations


def test_waiting_and_scheduled_tasks_appear_in_list_but_not_ready(
    tmp_path: Path,
) -> None:
    workspace = make_workspace(tmp_path)
    add_task(workspace, "Ready task")
    raw_task(workspace, ["add", "Waiting task", "project:demo", "wait:1day"])
    raw_task(workspace, ["add", "Scheduled task", "project:demo", "scheduled:1day"])

    ready = {task["description"] for task in listing(workspace, "ready")}
    listed = {task["description"]: task for task in listing(workspace, "list")}

    assert ready == {"Ready task"}
    assert set(listed) == {"Ready task", "Waiting task", "Scheduled task"}
    assert listed["Waiting task"]["waiting"] is True
    assert listed["Scheduled task"]["waiting"] is False


def test_cross_project_dependency_is_rejected_without_state_change(
    tmp_path: Path,
) -> None:
    alpha = make_workspace(tmp_path, name="alpha")
    beta = make_workspace(tmp_path, name="beta")
    foreign = add_task(alpha, "Foreign task")
    local = add_task(beta, "Local task")

    rejected = run_taskx(
        beta, ["depends", str(foreign["uuid"]), "add", str(local["uuid"])]
    )
    assert rejected.returncode == 3, rejected.stderr
    assert "task not found" in rejected.stderr

    raw_foreign = export_raw(alpha, f"uuid:{foreign['uuid']}")
    assert "depends" not in raw_foreign[0]
    raw_local = export_raw(beta, f"uuid:{local['uuid']}")
    assert raw_local[0]["status"] == "pending"
    assert "depends" not in raw_local[0]
