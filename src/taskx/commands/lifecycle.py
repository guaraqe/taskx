"""Lifecycle commands: start, release, and done."""

from __future__ import annotations

import argparse

from taskx.commands.contracts import CommandContext
from taskx.errors import UsageError
from taskx.model import Task
from taskx.output import write_task


def run(args: argparse.Namespace, context: CommandContext) -> int:
    """Handle the start, release, and done subcommands."""

    if args.command == "start":
        task = context.taskwarrior.start(context.project, args.uuid, context.actor)
        return _present(task, "started", args, context)

    if args.command == "release":
        task = context.taskwarrior.release(context.project, args.uuid, args.reason)
        return _present(task, "released", args, context)

    if args.command == "done":
        task = context.taskwarrior.done(context.project, args.uuid, context.actor)
        return _present(task, "completed", args, context)

    raise UsageError(f"command not handled: {args.command}")


def _present(
    task: Task,
    verb: str,
    args: argparse.Namespace,
    context: CommandContext,
) -> int:
    if args.json_output:
        write_task(task, context.stdout, json_output=True)
    else:
        print(f"{verb} {task.uuid}", file=context.stdout)
    return 0
