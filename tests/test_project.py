import os
import subprocess
from pathlib import Path

import pytest

from taskx.errors import ProjectError
from taskx.project import Project, project_filter, resolve_project


def git(*args: str, cwd: str | os.PathLike[str]) -> None:
    subprocess.run(("git", *args), cwd=cwd, check=True, capture_output=True, text=True)


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git("init", "-q", cwd=path)
    return path


def test_resolves_root_name_and_filter_from_nested_cwd(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "My Repo")
    nested = repo / "source dir" / "nested dir"
    nested.mkdir(parents=True)

    project = resolve_project(cwd=nested)

    assert Path(project.root) == repo.resolve()
    assert project.name == "My Repo"
    assert project.filter == "project.is:My Repo"


def test_filter_is_exact_and_verbatim() -> None:
    assert project_filter("wirecat") == "project.is:wirecat"
    assert project_filter("My Repo") == "project.is:My Repo"
    assert Project(root="/home/user/src/a b", name="a b").filter == ("project.is:a b")


def test_defaults_to_current_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path / "work repo")
    nested = repo / "deep dir"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    project = resolve_project()

    assert project.name == "work repo"
    assert Path(project.root) == repo.resolve()


def test_stale_git_environment_cannot_redirect_discovery(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "some repo")
    nested = repo / "sub dir"
    nested.mkdir()
    env = os.environ | {
        "GIT_DIR": str(tmp_path / "elsewhere.git"),
        "GIT_WORK_TREE": str(tmp_path / "elsewhere"),
    }

    project = resolve_project(cwd=nested, env=env)

    assert Path(project.root) == repo.resolve()
    assert project.name == "some repo"


def test_preserves_whitespace_belonging_to_the_path(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "space repo ")
    nested = repo / "inner "
    nested.mkdir()

    project = resolve_project(cwd=nested)

    assert Path(project.root) == repo.resolve()
    assert project.name == "space repo "
    assert project.filter == "project.is:space repo "


def test_fails_outside_repository(tmp_path: Path) -> None:
    outside = tmp_path / "plain dir"
    outside.mkdir()

    with pytest.raises(ProjectError, match="must be run inside a Git repository"):
        resolve_project(cwd=outside)


def test_fails_in_bare_repository(tmp_path: Path) -> None:
    bare = tmp_path / "bare repo.git"
    git("init", "-q", "--bare", str(bare), cwd=tmp_path)

    with pytest.raises(ProjectError, match="must be run inside a Git repository"):
        resolve_project(cwd=bare)
