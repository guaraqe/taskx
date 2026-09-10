"""AI session and human actor detection from the process environment."""

from __future__ import annotations

import getpass
from collections.abc import Mapping

from taskx.errors import ActorError

OVERRIDE_VARIABLE = "TASKX_ACTOR"

_CODEX_VARIABLES = ("CODEX_SESSION_ID", "CODEX_THREAD_ID")
_CLAUDE_VARIABLES = ("CLAUDE_SESSION_ID", "CLAUDE_SESSION")
_OPENCODE_VARIABLES = ("OPENCODE_SESSION_ID", "OPENCODE_SESSION")
_USERNAME_VARIABLES = ("LOGNAME", "USER", "LNAME", "USERNAME")


def _first_value(env: Mapping[str, str], names: tuple[str, ...]) -> str | None:
    """Return the first nonempty stripped value among *names*."""

    for name in names:
        value = env.get(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _session_actor(
    env: Mapping[str, str], prefix: str, names: tuple[str, ...]
) -> str | None:
    session = _first_value(env, names)
    if session is None:
        return None
    return f"{prefix}:{session}"


def codex_actor(env: Mapping[str, str]) -> str | None:
    """Detect an OpenAI Codex session actor."""
    return _session_actor(env, "codex", _CODEX_VARIABLES)


def claude_actor(env: Mapping[str, str]) -> str | None:
    """Detect a Claude Code session actor."""
    return _session_actor(env, "claude", _CLAUDE_VARIABLES)


def opencode_actor(env: Mapping[str, str]) -> str | None:
    """Detect an OpenCode session actor injected into the environment."""
    return _session_actor(env, "opencode", _OPENCODE_VARIABLES)


def _os_username() -> str | None:
    """Best-effort local username lookup outside *env*."""

    try:
        return getpass.getuser()
    except Exception:
        return None


def current_actor(env: Mapping[str, str], *, username: str | None = None) -> str:
    """Resolve the current actor identity from *env*.

    Precedence: the ``TASKX_ACTOR`` override, the Codex, Claude Code, and
    OpenCode session detectors, then ``human:<username>``. Empty or
    whitespace-only values never win. *username* injects the fallback name
    for deterministic callers; otherwise the mapping's username variables
    and finally the OS login name are consulted.
    """

    override = _first_value(env, (OVERRIDE_VARIABLE,))
    if override is not None:
        return override

    for detector in (codex_actor, claude_actor, opencode_actor):
        actor = detector(env)
        if actor is not None:
            return actor

    injected = username.strip() if username else ""
    resolved = injected or _first_value(env, _USERNAME_VARIABLES) or _os_username()
    if resolved:
        return f"human:{resolved}"

    raise ActorError("could not determine current actor; set TASKX_ACTOR explicitly")
