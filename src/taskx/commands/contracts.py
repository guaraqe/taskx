"""Small dependency boundary shared by command handlers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Protocol, TextIO

from taskx.taskwarrior import Taskwarrior


@dataclass(frozen=True, slots=True)
class CommandContext:
    project: str
    actor: str
    taskwarrior: Taskwarrior
    stdout: TextIO


class CommandHandler(Protocol):
    def __call__(self, args: argparse.Namespace, context: CommandContext) -> int: ...
