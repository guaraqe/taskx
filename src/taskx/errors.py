"""Stable error and exit-code contracts for taskx."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Process exit codes exposed by the command-line interface."""

    SUCCESS = 0
    ERROR = 1
    USAGE = 2
    NOT_FOUND = 3
    CONFLICT = 4


class TaskxError(Exception):
    """An expected error that can be presented without a traceback."""

    exit_code = ExitCode.ERROR


class UsageError(TaskxError):
    exit_code = ExitCode.USAGE


class TaskNotFoundError(TaskxError):
    exit_code = ExitCode.NOT_FOUND


class ConflictError(TaskxError):
    exit_code = ExitCode.CONFLICT


class ProjectError(TaskxError):
    """The current working directory cannot identify a project."""


class ActorError(TaskxError):
    """No valid actor identity could be resolved."""


class TaskwarriorError(TaskxError):
    """Taskwarrior rejected or could not perform an operation."""


class PostconditionError(TaskwarriorError):
    """A mutation completed without establishing its required invariant."""


class LockTimeoutError(TaskxError):
    """The mutation lock could not be acquired within the allowed time."""
