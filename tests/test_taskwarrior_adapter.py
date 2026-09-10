from __future__ import annotations

from collections.abc import Mapping

from taskx.taskwarrior import Taskwarrior, TaskwarriorAdapter


def accepts_taskwarrior(adapter: Taskwarrior) -> Taskwarrior:
    return adapter


def test_concrete_adapter_satisfies_public_protocol(
    taskwarrior_env: Mapping[str, str],
) -> None:
    adapter = TaskwarriorAdapter.from_environment(taskwarrior_env)

    assert accepts_taskwarrior(adapter) is adapter
