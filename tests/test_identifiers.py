import pytest

from taskx.errors import TaskNotFoundError, UsageError
from taskx.identifiers import resolve_uuid_prefix

UUIDS = (
    "12345678-1111-1111-1111-111111111111",
    "abcdef00-2222-2222-2222-222222222222",
    "abcdef11-3333-3333-3333-333333333333",
)


def test_full_uuid_and_unique_prefix_resolution() -> None:
    assert resolve_uuid_prefix(UUIDS[0], UUIDS) == UUIDS[0]
    assert resolve_uuid_prefix("ABCDEF0", UUIDS) == UUIDS[1]


def test_missing_reference() -> None:
    with pytest.raises(TaskNotFoundError):
        resolve_uuid_prefix("ffffffff", UUIDS)


def test_ambiguous_reference() -> None:
    with pytest.raises(UsageError, match="ambiguous"):
        resolve_uuid_prefix("abcdef", UUIDS)


def test_rejects_non_uuid_characters() -> None:
    with pytest.raises(UsageError, match="invalid"):
        resolve_uuid_prefix("not-a-uuid", UUIDS)
