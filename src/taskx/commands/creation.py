"""Creation and context commands: add, note, and depends."""

from __future__ import annotations

import argparse

from taskx.commands.contracts import CommandContext
from taskx.errors import UsageError
from taskx.model import Task
from taskx.output import write_task


def run(args: argparse.Namespace, context: CommandContext) -> int:
    """Handle the add, note, and depends subcommands."""

    if args.command == "add":
        task = context.taskwarrior.add(
            context.project, args.description, context.actor, args.depends
        )
        return _present(task, "created", args, context)

    if args.command == "note":
        task = context.taskwarrior.note(context.project, args.uuid, args.text)
        return _present(task, "noted", args, context)

    if args.command == "depends":
        task = context.taskwarrior.set_dependency(
            context.project,
            args.uuid,
            args.dependency_uuid,
            add=args.action == "add",
        )
        return _present(task, "updated", args, context)

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
