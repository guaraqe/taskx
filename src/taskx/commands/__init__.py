"""Runtime construction and command dispatch."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from taskx.actor import current_actor
from taskx.commands.contracts import CommandContext
from taskx.commands.creation import run as run_creation
from taskx.commands.help import run as run_help
from taskx.commands.inspection import run as run_inspection
from taskx.commands.lifecycle import run as run_lifecycle
from taskx.errors import UsageError
from taskx.project import resolve_project
from taskx.taskwarrior import Taskwarrior, TaskwarriorAdapter


def dispatch(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    stdout: TextIO | None = None,
    taskwarrior: Taskwarrior | None = None,
) -> int:
    """Build only the context needed by *args* and invoke its handler."""

    environment = dict(os.environ if env is None else env)
    output = sys.stdout if stdout is None else stdout
    command = args.command

    project = ""
    actor = ""
    if command not in {"actor", "help"}:
        project = resolve_project(cwd=cwd, env=environment).name
    if command not in {"project", "help"}:
        actor = current_actor(environment)

    adapter = taskwarrior or TaskwarriorAdapter.from_environment(environment, cwd=cwd)
    context = CommandContext(
        project=project,
        actor=actor,
        taskwarrior=adapter,
        stdout=output,
    )

    if command == "help":
        return run_help(args, context)
    if command in {"actor", "project", "ready", "list", "show"}:
        return run_inspection(args, context)
    if command in {"add", "note", "depends"}:
        return run_creation(args, context)
    if command in {"start", "release", "done"}:
        return run_lifecycle(args, context)
    raise UsageError(f"unknown command: {command}")
