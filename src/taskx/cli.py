"""Typed command-line interface and top-level error presentation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated

import typer

from taskx.errors import TaskxError

app = typer.Typer(
    name="taskx",
    help="Project-aware development tasks backed by Taskwarrior.",
    epilog="Run `taskx help agent` for the agent task lifecycle.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
skill_app = typer.Typer(
    help="Manage the taskx workflow skill for coding agents.",
    no_args_is_help=True,
)
skill_install_app = typer.Typer(
    help="Install the taskx workflow skill for an agent.",
    no_args_is_help=True,
)
app.add_typer(skill_app, name="skill")
skill_app.add_typer(skill_install_app, name="install")

JsonOption = Annotated[
    bool,
    typer.Option("--json", help="Write stable machine-readable JSON."),
]
GlobalOption = Annotated[
    bool,
    typer.Option("--global", help="Install for the current user instead of this repo."),
]
TaskReference = Annotated[
    str,
    typer.Argument(
        help="A full task UUID or an unambiguous UUID prefix.", metavar="UUID"
    ),
]


class DependencyAction(StrEnum):
    """Supported dependency mutations."""

    ADD = "add"
    REMOVE = "remove"


class HelpTopic(StrEnum):
    """Available extended help topics."""

    AGENT = "agent"


def _dispatch(command: str, **values: object) -> None:
    """Translate typed callback values to the stable command boundary."""

    from taskx.commands import dispatch

    result = dispatch(argparse.Namespace(command=command, **values))
    if result:
        raise typer.Exit(result)


@app.command(help="List tasks that are ready to be claimed.")
def ready(json_output: JsonOption = False) -> None:
    _dispatch("ready", json_output=json_output)


@app.command("list", help="List every unfinished task in this Git project.")
def list_tasks(json_output: JsonOption = False) -> None:
    _dispatch("list", json_output=json_output)


@app.command(help="Show one unfinished task.")
def show(uuid: TaskReference, json_output: JsonOption = False) -> None:
    _dispatch("show", uuid=uuid, json_output=json_output)


@app.command(help="Create a task in the current Git project.")
def add(
    description: Annotated[str, typer.Argument(help="A concise task description.")],
    depends: Annotated[
        list[str] | None,
        typer.Option(
            "--depends",
            help="UUID of a prerequisite task; repeat for multiple dependencies.",
        ),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    _dispatch(
        "add",
        description=description,
        depends=[] if depends is None else depends,
        json_output=json_output,
    )


@app.command(help="Claim a task and record the current actor.")
def start(uuid: TaskReference, json_output: JsonOption = False) -> None:
    _dispatch("start", uuid=uuid, json_output=json_output)


@app.command(help="Give up a claimed task so it can be claimed again.")
def release(
    uuid: TaskReference,
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Why the task is being released."),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    _dispatch("release", uuid=uuid, reason=reason, json_output=json_output)


@app.command(help="Complete a claimed task and record the current actor.")
def done(uuid: TaskReference, json_output: JsonOption = False) -> None:
    _dispatch("done", uuid=uuid, json_output=json_output)


@app.command(help="Append a durable annotation to a task.")
def note(
    uuid: TaskReference,
    text: Annotated[str, typer.Argument(help="Annotation text to append.")],
    json_output: JsonOption = False,
) -> None:
    _dispatch("note", uuid=uuid, text=text, json_output=json_output)


@app.command(help="Add or remove a dependency between project tasks.")
def depends(
    uuid: TaskReference,
    action: Annotated[
        DependencyAction,
        typer.Argument(help="Whether to add or remove the dependency."),
    ],
    dependency_uuid: Annotated[
        str,
        typer.Argument(help="UUID or unambiguous prefix of the prerequisite task."),
    ],
    json_output: JsonOption = False,
) -> None:
    _dispatch(
        "depends",
        uuid=uuid,
        action=action.value,
        dependency_uuid=dependency_uuid,
        json_output=json_output,
    )


@app.command(help="Print the actor identity taskx will record.")
def actor() -> None:
    _dispatch("actor")


@app.command(help="Print the exact Git project name used for task scoping.")
def project() -> None:
    _dispatch("project")


def _install_skill(agent: str, global_install: bool) -> None:
    _dispatch(
        "skill",
        skill_command="install",
        agent=agent,
        global_install=global_install,
    )


@skill_install_app.command(help="Install for Codex.")
def codex(global_install: GlobalOption = False) -> None:
    _install_skill("codex", global_install)


@skill_install_app.command(help="Install for Claude Code.")
def claude(global_install: GlobalOption = False) -> None:
    _install_skill("claude", global_install)


@skill_install_app.command(help="Install for OpenCode.")
def opencode(global_install: GlobalOption = False) -> None:
    _install_skill("opencode", global_install)


@app.command("help", help="Show extended workflow guidance.")
def help_command(
    topic: Annotated[HelpTopic, typer.Argument(help="The guidance topic to show.")],
) -> None:
    _dispatch("help", topic=topic.value)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its process exit code."""

    try:
        app(
            args=None if argv is None else list(argv),
            prog_name="taskx",
        )
    except TaskxError as error:
        print(f"error: {error}", file=sys.stderr)
        return int(error.exit_code)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 1
    return 0
