"""The taskx help agent command."""

from __future__ import annotations

import argparse

from taskx.commands.contracts import CommandContext

AGENT_HELP = """\
Project tasks are managed by taskx.

1. Run `taskx ready --json` to find available work.
2. Inspect a task with `taskx show <uuid> --json`.
3. Run `taskx start <uuid>` before modifying code for it.
4. When the task is complete and verified, immediately run `taskx done <uuid>`.
5. If abandoning or postponing active work, run
   `taskx release <uuid> --reason "..."`.
6. Use `taskx add` for newly discovered work.
7. Do not inspect completed tasks unless explicitly required.
8. Do not maintain parallel task lists in Markdown.
"""


def run(args: argparse.Namespace, context: CommandContext) -> int:
    """Print the compact machine-oriented agent workflow."""

    context.stdout.write(AGENT_HELP)
    return 0
