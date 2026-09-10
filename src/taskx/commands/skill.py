"""Install taskx's bundled agent skill."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import TextIO

from taskx.errors import ConflictError, TaskxError, UsageError
from taskx.project import resolve_project

_LOCAL_DIRECTORIES = {
    "codex": Path(".agents/skills"),
    "claude": Path(".claude/skills"),
    "opencode": Path(".opencode/skills"),
}
_GLOBAL_DIRECTORIES = {
    "codex": Path(".agents/skills"),
    "claude": Path(".claude/skills"),
    "opencode": Path(".config/opencode/skills"),
}


@dataclass(frozen=True, slots=True)
class SkillInstallation:
    """The outcome of installing the bundled skill."""

    path: Path
    changed: bool


def skill_path(
    agent: str,
    *,
    global_install: bool,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the documented taskx skill destination for *agent*."""

    directories = _GLOBAL_DIRECTORIES if global_install else _LOCAL_DIRECTORIES
    try:
        relative = directories[agent]
    except KeyError as error:
        raise UsageError(f"unsupported skill agent: {agent}") from error

    if global_install:
        root = home if home is not None else _home(env)
    else:
        root = Path(resolve_project(cwd=cwd, env=env).root)
    return root / relative / "taskx" / "SKILL.md"


def install_skill(
    agent: str,
    *,
    global_install: bool,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> SkillInstallation:
    """Install the bundled taskx skill without overwriting changed content."""

    target = skill_path(
        agent,
        global_install=global_install,
        cwd=cwd,
        env=env,
        home=home,
    )
    content = files("taskx._skill").joinpath("SKILL.md").read_bytes()

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise TaskxError(
            f"could not install taskx skill at {target}: {error}"
        ) from error

    try:
        with target.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        try:
            if target.read_bytes() == content:
                return SkillInstallation(path=target, changed=False)
        except OSError:
            pass
        raise ConflictError(f"refusing to overwrite existing skill: {target}") from None
    except OSError as error:
        raise TaskxError(
            f"could not install taskx skill at {target}: {error}"
        ) from error

    return SkillInstallation(path=target, changed=True)


def run(
    args: argparse.Namespace,
    *,
    cwd: Path | None,
    env: Mapping[str, str],
    stdout: TextIO,
) -> int:
    """Run a nested skill command."""

    if args.skill_command != "install":
        raise UsageError(f"unknown skill command: {args.skill_command}")

    result = install_skill(
        args.agent,
        global_install=args.global_install,
        cwd=cwd,
        env=env,
    )
    if result.changed:
        stdout.write(f"installed taskx skill at {result.path}\n")
    else:
        stdout.write(f"taskx skill already installed at {result.path}\n")
    return 0


def _home(env: Mapping[str, str] | None) -> Path:
    if env is not None:
        value = env.get("HOME")
        if value and value.strip():
            return Path(value).resolve()
    return Path.home()
