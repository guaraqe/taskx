from __future__ import annotations

import argparse
from importlib.resources import files
from io import StringIO
from pathlib import Path

import pytest

from taskx.commands import dispatch
from taskx.commands.skill import install_skill, skill_path
from taskx.errors import ConflictError, TaskxError

LOCAL_DIRECTORIES = {
    "codex": Path(".agents/skills/taskx/SKILL.md"),
    "claude": Path(".claude/skills/taskx/SKILL.md"),
    "opencode": Path(".opencode/skills/taskx/SKILL.md"),
}
GLOBAL_DIRECTORIES = {
    "codex": Path(".agents/skills/taskx/SKILL.md"),
    "claude": Path(".claude/skills/taskx/SKILL.md"),
    "opencode": Path(".config/opencode/skills/taskx/SKILL.md"),
}


@pytest.mark.parametrize("agent", ("codex", "claude", "opencode"))
def test_local_destination_uses_git_root_from_nested_directory(
    agent: str, git_repo: Path
) -> None:
    nested = git_repo / "nested" / "source"
    nested.mkdir(parents=True)

    destination = skill_path(agent, global_install=False, cwd=nested)

    assert destination == git_repo.resolve() / LOCAL_DIRECTORIES[agent]


@pytest.mark.parametrize("agent", ("codex", "claude", "opencode"))
def test_global_destination_uses_home_without_a_git_repository(
    agent: str, tmp_path: Path
) -> None:
    home = tmp_path / "home"

    destination = skill_path(
        agent,
        global_install=True,
        cwd=tmp_path,
        home=home,
    )

    assert destination == home / GLOBAL_DIRECTORIES[agent]


def test_install_copies_exact_bundled_skill_and_is_idempotent(git_repo: Path) -> None:
    first = install_skill("codex", global_install=False, cwd=git_repo)
    original_mtime = first.path.stat().st_mtime_ns
    second = install_skill("codex", global_install=False, cwd=git_repo)

    assert first.changed is True
    assert second.changed is False
    assert second.path == first.path
    assert second.path.stat().st_mtime_ns == original_mtime
    assert (
        second.path.read_bytes()
        == files("taskx._skill").joinpath("SKILL.md").read_bytes()
    )


def test_install_refuses_to_overwrite_different_content(git_repo: Path) -> None:
    target = git_repo / LOCAL_DIRECTORIES["claude"]
    target.parent.mkdir(parents=True)
    target.write_text("local customization\n", encoding="utf-8")

    with pytest.raises(ConflictError, match="refusing to overwrite"):
        install_skill("claude", global_install=False, cwd=git_repo)

    assert target.read_text(encoding="utf-8") == "local customization\n"


def test_install_reports_parent_directory_failure(git_repo: Path) -> None:
    obstruction = git_repo / ".agents"
    obstruction.write_text("not a directory\n", encoding="utf-8")

    with pytest.raises(TaskxError, match="could not install taskx skill"):
        install_skill("codex", global_install=False, cwd=git_repo)


def test_dispatch_installs_globally_outside_git_without_taskwarrior(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    output = StringIO()

    result = dispatch(
        argparse.Namespace(
            command="skill",
            skill_command="install",
            agent="opencode",
            global_install=True,
        ),
        cwd=tmp_path,
        env={"HOME": str(home)},
        stdout=output,
    )

    target = home / GLOBAL_DIRECTORIES["opencode"]
    assert result == 0
    assert output.getvalue() == f"installed taskx skill at {target}\n"
    assert target.is_file()


def test_repository_skill_matches_bundled_skill() -> None:
    repository_skill = Path(__file__).parents[1] / "SKILL.md"
    bundled_skill = files("taskx._skill").joinpath("SKILL.md")

    assert repository_skill.read_bytes() == bundled_skill.read_bytes()
