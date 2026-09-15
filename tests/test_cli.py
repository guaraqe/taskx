from __future__ import annotations

import argparse

import pytest

import taskx.commands
from taskx.cli import main


@pytest.mark.parametrize(
    ("argv", "expected"),
    (
        (["ready", "--json"], {"command": "ready", "json_output": True}),
        (["list"], {"command": "list", "json_output": False}),
        (
            ["show", "deadbeef", "--json"],
            {"command": "show", "uuid": "deadbeef", "json_output": True},
        ),
        (
            [
                "add",
                "Implement parser",
                "--depends",
                "aaa",
                "--depends",
                "bbb",
                "--json",
            ],
            {
                "command": "add",
                "description": "Implement parser",
                "depends": ["aaa", "bbb"],
                "json_output": True,
            },
        ),
        (
            ["release", "deadbeef", "--reason", "Needs design", "--json"],
            {
                "command": "release",
                "uuid": "deadbeef",
                "reason": "Needs design",
                "json_output": True,
            },
        ),
        (
            ["depends", "aaa", "remove", "bbb", "--json"],
            {
                "command": "depends",
                "uuid": "aaa",
                "action": "remove",
                "dependency_uuid": "bbb",
                "json_output": True,
            },
        ),
        (["actor"], {"command": "actor"}),
        (["project"], {"command": "project"}),
        (["help", "agent"], {"command": "help", "topic": "agent"}),
    ),
)
def test_typed_commands_map_to_dispatch_namespaces(
    argv: list[str],
    expected: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[argparse.Namespace] = []

    def dispatch(args: argparse.Namespace) -> int:
        seen.append(args)
        return 0

    monkeypatch.setattr(taskx.commands, "dispatch", dispatch)

    assert main(argv) == 0
    assert [vars(args) for args in seen] == [expected]


@pytest.mark.parametrize("agent", ("codex", "claude", "opencode"))
@pytest.mark.parametrize("global_install", (False, True))
def test_skill_install_subcommands_preserve_their_shape(
    agent: str,
    global_install: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[argparse.Namespace] = []

    def dispatch(args: argparse.Namespace) -> int:
        seen.append(args)
        return 0

    monkeypatch.setattr(taskx.commands, "dispatch", dispatch)
    argv = ["skill", "install", agent]
    if global_install:
        argv.append("--global")

    assert main(argv) == 0
    assert [vars(args) for args in seen] == [
        {
            "command": "skill",
            "skill_command": "install",
            "agent": agent,
            "global_install": global_install,
        }
    ]


def test_top_level_help_explains_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--help"]) == 0

    output = capsys.readouterr().out
    assert "Project-aware development tasks backed by Taskwarrior" in output
    assert "List tasks that are ready to be claimed" in output
    assert "Manage the taskx workflow skill for coding agents" in output
    assert "taskx help agent" in output


def test_nested_help_explains_installers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["skill", "install", "--help"]) == 0

    output = capsys.readouterr().out
    assert "Install the taskx workflow skill for an agent" in output
    assert "Install for Codex" in output
    assert "Install for Claude Code" in output
    assert "Install for OpenCode" in output


def test_invalid_usage_is_friendly_and_has_no_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["show"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Missing argument" in captured.err
    assert "UUID" in captured.err
    assert "Traceback" not in captured.err


def test_command_callback_nonzero_result_becomes_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def dispatch(args: argparse.Namespace) -> int:
        return 4

    monkeypatch.setattr(taskx.commands, "dispatch", dispatch)

    assert main(["start", "deadbeef"]) == 4
