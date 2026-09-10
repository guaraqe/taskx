"""Inspection commands: actor, project, ready, list, and show."""

from __future__ import annotations

import argparse

from taskx.commands.contracts import CommandContext
from taskx.errors import UsageError
from taskx.output import write_task, write_tasks


def run(args: argparse.Namespace, context: CommandContext) -> int:
    """Dispatch one inspection command based on ``args.command``."""

    command = args.command
    if command == "actor":
        context.stdout.write(f"{context.actor}\n")
    elif command == "project":
        context.stdout.write(f"{context.project}\n")
    elif command == "ready":
        write_tasks(
            context.taskwarrior.ready(context.project),
            context.stdout,
            json_output=_wants_json(args),
        )
    elif command == "list":
        write_tasks(
            context.taskwarrior.list_pending(context.project),
            context.stdout,
            json_output=_wants_json(args),
        )
    elif command == "show":
        write_task(
            context.taskwarrior.get(context.project, args.uuid),
            context.stdout,
            json_output=_wants_json(args),
        )
    else:
        raise UsageError(f"unexpected inspection command: {command}")
    return 0


def _wants_json(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json_output", False))
