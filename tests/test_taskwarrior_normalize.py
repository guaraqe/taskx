import pytest

from taskx.errors import TaskwarriorError
from taskx.model import Annotation
from taskx.taskwarrior.normalize import normalize_task

UUID = "80b65cb1-5fd2-4efa-b4a8-ebe17346b69c"
DEPENDENCY_UUID = "352fc723-4178-4775-a05a-cb7c6f28ac51"


def base_export() -> dict[str, object]:
    return {
        "uuid": UUID,
        "description": "Implement evaluator",
        "project": "wirecat",
        "status": "pending",
    }


def test_full_export_maps_every_field() -> None:
    raw: dict[str, object] = {
        "id": 12,
        "urgency": 5.5,
        **base_export(),
        "entry": "20260910T060000Z",
        "start": "20260910T070000Z",
        "end": "20260910T080000Z",
        "wait": "20260910T090000Z",
        "scheduled": "20260910T100000Z",
        "depends": [DEPENDENCY_UUID],
        "annotations": [
            {"entry": "20260910T073000Z", "description": "Design: docs/parser.md"}
        ],
        "taskx_created_by": "human:juan",
        "taskx_started_by": "codex:019c",
        "taskx_closed_by": None,
    }

    task = normalize_task(raw, blocked=True)

    assert task.uuid == UUID
    assert task.description == "Implement evaluator"
    assert task.project == "wirecat"
    assert task.status == "pending"
    assert task.active is True
    assert task.blocked is True
    assert task.waiting is True
    assert task.depends == (DEPENDENCY_UUID,)
    assert task.annotations == (
        Annotation(entry="20260910T073000Z", description="Design: docs/parser.md"),
    )
    assert task.entry == "20260910T060000Z"
    assert task.start == "20260910T070000Z"
    assert task.end == "20260910T080000Z"
    assert task.wait == "20260910T090000Z"
    assert task.scheduled == "20260910T100000Z"
    assert task.created_by == "human:juan"
    assert task.started_by == "codex:019c"
    assert task.closed_by is None


def test_minimal_export_defaults_and_unknown_fields_are_ignored() -> None:
    raw: dict[str, object] = {
        "id": 7,
        "urgency": 3.25,
        **base_export(),
        "tags": ["next"],
        "priority": "H",
        "mystery_future_field": {"nested": [1, 2]},
    }

    task = normalize_task(raw)

    assert task.active is False
    assert task.blocked is False
    assert task.waiting is False
    assert task.depends == ()
    assert task.annotations == ()
    assert task.entry is None
    assert task.start is None
    assert task.end is None
    assert task.wait is None
    assert task.scheduled is None
    assert task.created_by is None
    assert task.started_by is None
    assert task.closed_by is None


def test_waiting_flag_from_legacy_status_and_wait_timestamp() -> None:
    legacy = normalize_task({**base_export(), "status": "waiting"})
    assert legacy.waiting is True
    assert legacy.status == "waiting"

    modern = normalize_task({**base_export(), "wait": "20260910T090000Z"})
    assert modern.waiting is True
    assert modern.status == "pending"

    neither = normalize_task(base_export())
    assert neither.waiting is False


def test_active_requires_pending_status_and_nonempty_start() -> None:
    assert normalize_task({**base_export(), "start": "20260910T070000Z"}).active is True

    assert normalize_task(base_export()).active is False

    completed = normalize_task(
        {
            **base_export(),
            "status": "completed",
            "start": "20260910T070000Z",
            "end": "20260910T080000Z",
        }
    )
    assert completed.active is False

    empty_start = normalize_task({**base_export(), "start": ""})
    assert empty_start.start is None
    assert empty_start.active is False


def test_dependencies_accept_absent_string_and_list() -> None:
    assert normalize_task(base_export()).depends == ()
    assert normalize_task({**base_export(), "depends": ""}).depends == ()
    assert normalize_task({**base_export(), "depends": DEPENDENCY_UUID}).depends == (
        DEPENDENCY_UUID,
    )
    assert normalize_task(
        {**base_export(), "depends": [DEPENDENCY_UUID, "aaaabbbb"]}
    ).depends == (DEPENDENCY_UUID, "aaaabbbb")


@pytest.mark.parametrize(
    "bad_depends", [5, {"a": "b"}, ["a", 3], [""], ["a", None], True]
)
def test_malformed_dependencies_raise_taskwarrior_error(
    bad_depends: object,
) -> None:
    with pytest.raises(TaskwarriorError, match="depends"):
        normalize_task({**base_export(), "depends": bad_depends})


def test_annotations_normalized_with_optional_entry() -> None:
    task = normalize_task(
        {
            **base_export(),
            "annotations": [
                {"entry": "20260910T073000Z", "description": "first"},
                {"description": "second"},
            ],
        }
    )

    assert task.annotations == (
        Annotation(entry="20260910T073000Z", description="first"),
        Annotation(entry=None, description="second"),
    )


@pytest.mark.parametrize(
    "bad_annotations",
    [
        3,
        ["plain string"],
        [{"entry": "20260910T073000Z"}],
        [{"description": 4}],
        [{"description": "  "}],
        [{"description": "d", "entry": 5}],
    ],
)
def test_malformed_annotations_raise_taskwarrior_error(
    bad_annotations: object,
) -> None:
    with pytest.raises(TaskwarriorError, match="annotation"):
        normalize_task({**base_export(), "annotations": bad_annotations})


@pytest.mark.parametrize("key", ["uuid", "description", "project", "status"])
@pytest.mark.parametrize("bad_value", [None, 42, "", "   "])
def test_missing_or_malformed_required_fields_raise(
    key: str, bad_value: object
) -> None:
    raw = base_export()
    if bad_value is None:
        del raw[key]
    else:
        raw[key] = bad_value

    with pytest.raises(TaskwarriorError, match=key):
        normalize_task(raw)


def test_malformed_uda_and_timestamp_types_raise() -> None:
    with pytest.raises(TaskwarriorError, match="taskx_started_by"):
        normalize_task({**base_export(), "taskx_started_by": 5})

    with pytest.raises(TaskwarriorError, match="'entry'"):
        normalize_task({**base_export(), "entry": 7})

    with pytest.raises(TaskwarriorError, match="'scheduled'"):
        normalize_task({**base_export(), "scheduled": ["x"]})
