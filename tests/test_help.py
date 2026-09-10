from __future__ import annotations

import argparse
from collections.abc import Sequence
from io import StringIO

from taskx.cli import build_parser
from taskx.commands.contracts import CommandContext, CommandHandler
from taskx.commands.help import AGENT_HELP, run
from taskx.model import Task


class NullTaskwarrior:
    """Protocol-conforming stub; the help command never touches Taskwarrior."""

    def ready(self, project: str) -> list[Task]:
        raise NotImplementedError

    def list_pending(self, project: str) -> list[Task]:
        raise NotImplementedError

    def get(self, project: str, reference: str) -> Task:
        raise NotImplementedError

    def add(
        self,
        project: str,
        description: str,
        actor: str,
        dependencies: Sequence[str] = (),
    ) -> Task:
        raise NotImplementedError

    def start(self, project: str, reference: str, actor: str) -> Task:
        raise NotImplementedError

    def release(self, project: str, reference: str, reason: str | None = None) -> Task:
        raise NotImplementedError

    def done(self, project: str, reference: str, actor: str) -> Task:
        raise NotImplementedError

    def note(self, project: str, reference: str, text: str) -> Task:
        raise NotImplementedError

    def set_dependency(
        self,
        project: str,
        reference: str,
        dependency: str,
        *,
        add: bool,
    ) -> Task:
        raise NotImplementedError


def make_context() -> tuple[CommandContext, StringIO]:
    stream = StringIO()
    context = CommandContext(
        project="demo",
        actor="test:fixture",
        taskwarrior=NullTaskwarrior(),
        stdout=stream,
    )
    return context, stream


def test_run_satisfies_command_handler_protocol() -> None:
    handler: CommandHandler = run

    assert handler is run


def test_help_agent_prints_workflow_to_context_stdout() -> None:
    context, stream = make_context()
    args = argparse.Namespace(topic="agent")

    assert run(args, context) == 0
    assert stream.getvalue() == AGENT_HELP


def test_help_agent_text_covers_the_required_workflow() -> None:
    for fragment in (
        "taskx ready --json",
        "taskx show <uuid> --json",
        "taskx start <uuid>",
        "taskx done <uuid>",
        "taskx release <uuid> --reason",
        "taskx add",
        "immediately",
        "completed",
        "Markdown",
    ):
        assert fragment in AGENT_HELP


def test_cli_help_topic_shape_feeds_handler() -> None:
    args = build_parser().parse_args(["help", "agent"])
    context, stream = make_context()

    assert args.topic == "agent"
    assert run(args, context) == 0
    assert "Project tasks are managed by taskx." in stream.getvalue()
