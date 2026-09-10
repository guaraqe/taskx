from __future__ import annotations

import json
from io import StringIO

from taskx.model import Annotation, Task
from taskx.output import task_line, write_task, write_tasks


def sample_task(
    *,
    active: bool = False,
    blocked: bool = False,
    created_by: str | None = None,
    annotations: tuple[Annotation, ...] = (),
) -> Task:
    return Task(
        uuid="12345678-1111-1111-1111-111111111111",
        description="Implement parser",
        project="demo",
        status="pending",
        active=active,
        blocked=blocked,
        created_by=created_by,
        annotations=annotations,
    )


def test_task_line_shows_claim_relevant_state() -> None:
    task = sample_task(active=True, blocked=True)

    assert task_line(task).endswith("Implement parser [active, blocked]")


def test_task_json_uses_normalized_model_without_numeric_id() -> None:
    stream = StringIO()
    task = sample_task(
        created_by="human:juan",
        annotations=(Annotation(entry=None, description="context"),),
    )

    write_task(task, stream, json_output=True)
    value = json.loads(stream.getvalue())

    assert value["uuid"] == task.uuid
    assert value["created_by"] == "human:juan"
    assert value["annotations"] == [{"entry": None, "description": "context"}]
    assert "id" not in value


def test_empty_task_list_is_an_empty_json_array() -> None:
    stream = StringIO()

    write_tasks([], stream, json_output=True)

    assert json.loads(stream.getvalue()) == []
