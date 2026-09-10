"""Taskwarrior export JSON to normalized Task conversion."""

from __future__ import annotations

from collections.abc import Mapping

from taskx.errors import TaskwarriorError
from taskx.model import Annotation, Task


def normalize_task(raw: Mapping[str, object], *, blocked: bool = False) -> Task:
    """Convert one Taskwarrior export object into a normalized Task.

    Numeric ``id``, ``urgency``, and any unrecognized fields are ignored.
    The ``blocked`` flag is supplied by the caller because it is calculated
    from the project-wide task set rather than from the single export
    object. Malformed required fields or malformed collection structures
    raise TaskwarriorError instead of leaking low-level lookup errors.
    """

    uuid = _required_string(raw, "uuid")
    description = _required_string(raw, "description")
    project = _required_string(raw, "project")
    status = _required_string(raw, "status")
    start = _optional_string(raw, "start")
    wait = _optional_string(raw, "wait")

    return Task(
        uuid=uuid,
        description=description,
        project=project,
        status=status,
        active=status == "pending" and start is not None,
        blocked=blocked,
        waiting=status == "waiting" or wait is not None,
        depends=_dependencies(raw),
        annotations=_annotations(raw),
        entry=_optional_string(raw, "entry"),
        start=start,
        end=_optional_string(raw, "end"),
        wait=wait,
        scheduled=_optional_string(raw, "scheduled"),
        created_by=_optional_string(raw, "taskx_created_by"),
        started_by=_optional_string(raw, "taskx_started_by"),
        closed_by=_optional_string(raw, "taskx_closed_by"),
    )


def _required_string(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if isinstance(value, str) and value.strip():
        return value
    raise TaskwarriorError(
        f"invalid Taskwarrior export: {key!r} must be a nonempty string"
    )


def _optional_string(raw: Mapping[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TaskwarriorError(
            f"invalid Taskwarrior export: {key!r} must be a string or absent,"
            f" got {type(value).__name__}"
        )
    return value or None


def _dependencies(raw: Mapping[str, object]) -> tuple[str, ...]:
    value = raw.get("depends")
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if not isinstance(value, list):
        raise TaskwarriorError(
            "invalid Taskwarrior export: 'depends' must be a string or a list of"
            f" strings, got {type(value).__name__}"
        )
    dependencies: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise TaskwarriorError(
                "invalid Taskwarrior export: 'depends' entries must be nonempty strings"
            )
        dependencies.append(item)
    return tuple(dependencies)


def _annotations(raw: Mapping[str, object]) -> tuple[Annotation, ...]:
    value = raw.get("annotations")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TaskwarriorError(
            "invalid Taskwarrior export: 'annotations' must be a list,"
            f" got {type(value).__name__}"
        )
    annotations: list[Annotation] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TaskwarriorError(
                "invalid Taskwarrior export: each annotation must be an object"
            )
        description = item.get("description")
        if not isinstance(description, str) or not description.strip():
            raise TaskwarriorError(
                "invalid Taskwarrior export: annotations require a nonempty"
                " 'description'"
            )
        entry = item.get("entry")
        if entry is not None and not isinstance(entry, str):
            raise TaskwarriorError(
                "invalid Taskwarrior export: annotation 'entry' must be a string"
            )
        annotations.append(Annotation(entry=entry, description=description))
    return tuple(annotations)
