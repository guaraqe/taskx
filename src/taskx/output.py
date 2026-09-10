"""Stable JSON and concise human-readable presentation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, TextIO

from taskx.model import Task


def write_json(value: Any, stream: TextIO) -> None:
    """Write deterministic, human-inspectable JSON."""

    json.dump(value, stream, indent=2, ensure_ascii=False)
    stream.write("\n")


def task_line(task: Task) -> str:
    """Format one task for concise list output."""

    states = []
    if task.active:
        states.append("active")
    if task.blocked:
        states.append("blocked")
    if task.waiting:
        states.append("waiting")
    suffix = f" [{', '.join(states)}]" if states else ""
    return f"{task.uuid} {task.description}{suffix}"


def write_tasks(tasks: Sequence[Task], stream: TextIO, *, json_output: bool) -> None:
    if json_output:
        write_json([task.to_dict() for task in tasks], stream)
        return
    for task in tasks:
        print(task_line(task), file=stream)


def write_task(task: Task, stream: TextIO, *, json_output: bool) -> None:
    if json_output:
        write_json(task.to_dict(), stream)
        return

    values = (
        ("uuid", task.uuid),
        ("description", task.description),
        ("project", task.project),
        ("status", task.status),
        ("active", str(task.active).lower()),
        ("blocked", str(task.blocked).lower()),
        ("waiting", str(task.waiting).lower()),
        ("depends", ", ".join(task.depends)),
        ("created", task.entry),
        ("started", task.start),
        ("ended", task.end),
        ("created_by", task.created_by),
        ("started_by", task.started_by),
        ("closed_by", task.closed_by),
    )
    for name, value in values:
        if value not in (None, ""):
            print(f"{name}: {value}", file=stream)
    for annotation in task.annotations:
        prefix = f"{annotation.entry} " if annotation.entry else ""
        print(f"note: {prefix}{annotation.description}", file=stream)
