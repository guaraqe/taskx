import pytest

from taskx.actor import (
    claude_actor,
    codex_actor,
    current_actor,
    opencode_actor,
)
from taskx.errors import ActorError


def test_taskx_actor_override_beats_all_other_sources() -> None:
    env = {
        "TASKX_ACTOR": " ci-bot ",
        "CODEX_SESSION_ID": "codex-1",
        "CLAUDE_SESSION_ID": "claude-1",
        "OPENCODE_SESSION_ID": "opencode-1",
        "USER": "juan",
    }

    assert current_actor(env) == "ci-bot"


def test_detector_precedence_is_codex_then_claude_then_opencode() -> None:
    all_sessions = {
        "CODEX_SESSION_ID": "codex-1",
        "CLAUDE_SESSION_ID": "claude-1",
        "OPENCODE_SESSION_ID": "opencode-1",
        "USER": "juan",
    }

    assert current_actor(all_sessions) == "codex:codex-1"

    without_codex = {k: v for k, v in all_sessions.items() if "CODEX" not in k}
    assert current_actor(without_codex) == "claude:claude-1"

    without_claude = {k: v for k, v in without_codex.items() if "CLAUDE" not in k}
    assert current_actor(without_claude) == "opencode:opencode-1"


def test_session_detectors_beat_human_fallback() -> None:
    assert current_actor({"CLAUDE_SESSION_ID": "abc", "USER": "juan"}) == "claude:abc"
    assert current_actor({"OPENCODE_SESSION_ID": "ses_x", "LOGNAME": "juan"}) == (
        "opencode:ses_x"
    )


def test_empty_values_never_win() -> None:
    assert current_actor({"TASKX_ACTOR": "", "USER": "juan"}) == "human:juan"
    assert current_actor({"TASKX_ACTOR": "   ", "CODEX_SESSION_ID": "s1"}) == (
        "codex:s1"
    )
    assert (
        current_actor(
            {"CODEX_SESSION_ID": "", "CLAUDE_SESSION_ID": "c1", "USER": "juan"}
        )
        == "claude:c1"
    )
    assert current_actor({"CLAUDE_SESSION_ID": " ", "OPENCODE_SESSION_ID": "o1"}) == (
        "opencode:o1"
    )
    assert current_actor({"USER": "", "LOGNAME": "juan"}) == "human:juan"


def test_codex_detector() -> None:
    assert codex_actor({"CODEX_SESSION_ID": "019c"}) == "codex:019c"
    assert codex_actor({"CODEX_THREAD_ID": "t1"}) == "codex:t1"
    assert codex_actor({"CODEX_SESSION_ID": "  "}) is None
    assert codex_actor({}) is None


def test_claude_detector() -> None:
    assert claude_actor({"CLAUDE_SESSION_ID": "abc123"}) == "claude:abc123"
    assert claude_actor({"CLAUDE_SESSION": "s"}) == "claude:s"
    assert claude_actor({"CLAUDE_SESSION_ID": ""}) is None
    assert claude_actor({}) is None


def test_opencode_detector() -> None:
    assert opencode_actor({"OPENCODE_SESSION_ID": "ses_..."}) == "opencode:ses_..."
    assert opencode_actor({"OPENCODE_SESSION": "s"}) == "opencode:s"
    assert opencode_actor({"OPENCODE_SESSION_ID": " "}) is None
    assert opencode_actor({}) is None


def test_human_fallback_uses_mapping_username() -> None:
    assert current_actor({"LOGNAME": "juan", "USER": "other"}) == "human:juan"
    assert current_actor({"USER": "juan"}) == "human:juan"
    assert current_actor({"USERNAME": "juan"}) == "human:juan"
    assert current_actor({"USER": "  juan  "}) == "human:juan"


def test_injected_username_takes_precedence_over_mapping() -> None:
    assert current_actor({"USER": "juan"}, username="robot") == "human:robot"
    assert current_actor({}, username="robot") == "human:robot"
    assert current_actor({}, username=" robot ") == "human:robot"


def test_os_login_username_is_last_resort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("taskx.actor._os_username", lambda: "osuser")
    assert current_actor({}) == "human:osuser"


def test_actor_error_when_no_fallback_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("taskx.actor._os_username", lambda: None)

    with pytest.raises(ActorError, match="TASKX_ACTOR"):
        current_actor({}, username="   ")
