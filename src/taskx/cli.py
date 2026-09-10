"""Command-line parsing and top-level error presentation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from taskx.errors import TaskxError


def _with_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="json_output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="taskx")
    commands = parser.add_subparsers(dest="command", required=True)

    for name in ("ready", "list"):
        command = commands.add_parser(name)
        _with_json(command)

    show = commands.add_parser("show")
    show.add_argument("uuid")
    _with_json(show)

    add = commands.add_parser("add")
    add.add_argument("description")
    add.add_argument("--depends", action="append", default=[])
    _with_json(add)

    start = commands.add_parser("start")
    start.add_argument("uuid")
    _with_json(start)

    release = commands.add_parser("release")
    release.add_argument("uuid")
    release.add_argument("--reason")
    _with_json(release)

    done = commands.add_parser("done")
    done.add_argument("uuid")
    _with_json(done)

    note = commands.add_parser("note")
    note.add_argument("uuid")
    note.add_argument("text")
    _with_json(note)

    depends = commands.add_parser("depends")
    depends.add_argument("uuid")
    depends.add_argument("action", choices=("add", "remove"))
    depends.add_argument("dependency_uuid")
    _with_json(depends)

    commands.add_parser("actor")
    commands.add_parser("project")

    skill = commands.add_parser("skill")
    skill_commands = skill.add_subparsers(dest="skill_command", required=True)
    install = skill_commands.add_parser("install")
    installers = install.add_subparsers(dest="agent", required=True)
    for agent in ("codex", "claude", "opencode"):
        installer = installers.add_parser(agent)
        installer.add_argument("--global", action="store_true", dest="global_install")

    help_parser = commands.add_parser("help")
    help_parser.add_argument("topic", choices=("agent",))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from taskx.commands import dispatch

        return dispatch(args)
    except TaskxError as error:
        print(f"error: {error}", file=sys.stderr)
        return int(error.exit_code)
