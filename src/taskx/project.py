"""Git-root discovery and Taskwarrior project identity."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

from taskx.errors import ProjectError

_SHOW_TOPLEVEL = ("git", "rev-parse", "--show-toplevel")

_DISCOVERY_OVERRIDES = frozenset(
    ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")
)

_NOT_IN_REPOSITORY = "taskx must be run inside a Git repository"


@dataclass(frozen=True, slots=True)
class Project:
    """The Git-root-derived identity of the current project."""

    root: str
    name: str

    @property
    def filter(self) -> str:
        """The exact Taskwarrior filter selecting this project."""

        return project_filter(self.name)


def project_filter(name: str) -> str:
    """Return the exact Taskwarrior filter selecting the project *name*."""

    return f"project.is:{name}"


def resolve_project(
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> Project:
    """Resolve the Git root containing *cwd* and its project identity.

    The project name is the basename of the Git root. Repository discovery
    always follows the working directory, so Git environment overrides are
    stripped from the child environment and a stale ``GIT_DIR`` can neither
    redirect nor break resolution. Arguments are passed as an argv list
    without a shell, so paths containing whitespace are safe. Only the
    terminating newline is removed from Git's output, preserving any
    whitespace that belongs to the path itself.

    Raises ``ProjectError`` when the directory is not inside a Git
    repository work tree.
    """

    base_env = os.environ if env is None else env
    child_env = {
        key: value for key, value in base_env.items() if key not in _DISCOVERY_OVERRIDES
    }
    try:
        completed = subprocess.run(
            _SHOW_TOPLEVEL,
            cwd=cwd,
            env=child_env,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise ProjectError(f"could not run Git project discovery: {error}") from error
    if completed.returncode != 0:
        raise ProjectError(_NOT_IN_REPOSITORY)
    root = completed.stdout.removesuffix("\n")
    if not root:
        raise ProjectError(_NOT_IN_REPOSITORY)
    return Project(root=root, name=os.path.basename(root))
