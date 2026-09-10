"""UUID validation and unique-prefix resolution."""

from __future__ import annotations

import re
from collections.abc import Iterable

from taskx.errors import TaskNotFoundError, UsageError

_UUID_REFERENCE = re.compile(r"[0-9a-fA-F-]+\Z")


def resolve_uuid_prefix(reference: str, candidates: Iterable[str]) -> str:
    """Resolve a full UUID or unambiguous UUID prefix from *candidates*."""

    if not reference or _UUID_REFERENCE.fullmatch(reference) is None:
        raise UsageError(f"invalid UUID reference: {reference!r}")

    needle = reference.lower()
    matches = [
        candidate for candidate in candidates if candidate.lower().startswith(needle)
    ]
    if not matches:
        raise TaskNotFoundError(f"task not found: {reference}")
    if len(matches) > 1:
        raise UsageError(f"ambiguous UUID prefix: {reference}")
    return matches[0]
