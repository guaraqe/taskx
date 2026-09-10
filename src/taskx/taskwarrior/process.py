"""Shell-free subprocess runner for Taskwarrior."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from taskx.errors import TaskwarriorError
from taskx.taskwarrior.contracts import TaskwarriorCommandResult

UDA_OVERRIDES = (
    "rc.uda.taskx_created_by.type=string",
    "rc.uda.taskx_started_by.type=string",
    "rc.uda.taskx_closed_by.type=string",
)


class TaskwarriorProcess:
    """Invoke Taskwarrior with taskx's required runtime configuration."""

    def __init__(
        self,
        *,
        executable: str = "task",
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> None:
        self._executable = executable
        self._env = dict(env) if env is not None else None
        self._cwd = cwd

    def run(
        self,
        arguments: Sequence[str],
        *,
        check: bool = True,
        input_text: str | None = None,
    ) -> TaskwarriorCommandResult:
        """Run one command, capturing output and raising expected errors."""

        argv = (
            self._executable,
            "rc.context=",
            "rc.confirmation=off",
            *UDA_OVERRIDES,
            *arguments,
        )
        try:
            completed = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                input=input_text,
                env=self._env,
                cwd=self._cwd,
            )
        except FileNotFoundError as error:
            raise TaskwarriorError(
                f"Taskwarrior executable not found: {self._executable}"
            ) from error
        except OSError as error:
            raise TaskwarriorError(f"could not run Taskwarrior: {error}") from error

        result = TaskwarriorCommandResult(
            argv=tuple(argv),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            if not detail:
                detail = f"Taskwarrior exited with status {result.returncode}"
            raise TaskwarriorError(detail)
        return result

    @classmethod
    def from_environment(
        cls, env: Mapping[str, str] | None = None, *, cwd: Path | None = None
    ) -> TaskwarriorProcess:
        """Create a runner with a stable snapshot of the process environment."""

        return cls(env=os.environ if env is None else env, cwd=cwd)
