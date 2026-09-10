"""Tests for the taskx mutation lock."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
from itertools import pairwise
from pathlib import Path

import pytest

from taskx import locking
from taskx.errors import LockTimeoutError, TaskxError
from taskx.locking import (
    LOCK_FILENAME,
    MutationLock,
    lock_path,
    mutation_lock,
)

_SRC_DIRECTORY = Path(locking.__file__).resolve().parents[1]

_HOLD_SCRIPT = """\
import os
import sys
import time
from pathlib import Path

from taskx.locking import MutationLock

lock_file = Path(sys.argv[1])
held = Path(sys.argv[2])
release = Path(sys.argv[3]) if len(sys.argv) > 3 else None

with MutationLock(lock_file):
    held.write_text("held")
    if release is None:
        os._exit(0)
    deadline = time.monotonic() + 30.0
    while not release.exists():
        if time.monotonic() > deadline:
            os._exit(1)
        time.sleep(0.01)
"""

_WORKER_SCRIPT = """\
import sys
import time
from pathlib import Path

from taskx.locking import MutationLock

lock_file = Path(sys.argv[1])
output = Path(sys.argv[2])
work = float(sys.argv[3])

with MutationLock(lock_file):
    entered = time.monotonic()
    time.sleep(work)
    exited = time.monotonic()

output.write_text(f"{entered} {exited}\\n")
"""


def _child_env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(_SRC_DIRECTORY)}


def _wait_for(path: Path, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    pytest.fail(f"timed out waiting for {path}")


def test_taskdata_isolates_lock_paths(tmp_path: Path) -> None:
    first = lock_path({"TASKDATA": str(tmp_path / "a")})
    second = lock_path({"TASKDATA": str(tmp_path / "b")})
    assert first != second
    assert lock_path({"TASKDATA": str(tmp_path / "a") + "/"}) == first
    assert first.name == LOCK_FILENAME
    assert first.parent.name == "a"


def test_lock_path_without_taskdata_prefers_user_directories(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    cache = tmp_path / "cache"
    home = tmp_path / "home"
    assert (
        lock_path({"XDG_RUNTIME_DIR": str(runtime)})
        == runtime / "taskx" / LOCK_FILENAME
    )
    assert lock_path({"XDG_CACHE_HOME": str(cache)}) == cache / "taskx" / LOCK_FILENAME
    assert lock_path({"HOME": str(home)}) == home / ".cache" / "taskx" / LOCK_FILENAME
    assert (
        lock_path({"XDG_RUNTIME_DIR": "  ", "HOME": str(home)})
        == home / ".cache" / "taskx" / LOCK_FILENAME
    )


def test_taskdata_takes_precedence_over_user_directories(tmp_path: Path) -> None:
    taskdata = tmp_path / "taskdata"
    runtime = tmp_path / "runtime"
    env = {"TASKDATA": str(taskdata), "XDG_RUNTIME_DIR": str(runtime)}
    assert lock_path(env) == taskdata / LOCK_FILENAME


def test_lock_path_defaults_to_process_environment() -> None:
    assert lock_path() == lock_path(os.environ)


def test_acquire_creates_missing_directories_user_only(tmp_path: Path) -> None:
    lock_file = tmp_path / "taskdata" / LOCK_FILENAME
    with MutationLock(lock_file):
        assert stat.S_IMODE(lock_file.parent.stat().st_mode) & 0o077 == 0
        assert stat.S_IMODE(lock_file.stat().st_mode) == 0o600


def test_mutation_lock_uses_environment_path(tmp_path: Path) -> None:
    env = {"TASKDATA": str(tmp_path / "data")}
    with mutation_lock(env) as lock:
        assert lock.path == lock_path(env)
        assert lock.path.exists()
    assert MutationLock.for_environment(env).path == lock_path(env)


def test_second_holder_cannot_acquire_while_held(tmp_path: Path) -> None:
    lock_file = tmp_path / LOCK_FILENAME
    first = MutationLock(lock_file)
    first.acquire()
    second = MutationLock(lock_file)
    try:
        with pytest.raises(LockTimeoutError):
            second.acquire(timeout=0.05)
    finally:
        first.release()
    first.release()
    second.acquire()
    try:
        with pytest.raises(TaskxError):
            second.acquire()
    finally:
        second.release()


def test_release_on_exceptional_exit(tmp_path: Path) -> None:
    lock_file = tmp_path / LOCK_FILENAME
    with pytest.raises(RuntimeError, match="boom"), MutationLock(lock_file):
        raise RuntimeError("boom")
    with MutationLock(lock_file):
        pass


def test_mutual_exclusion_across_processes(tmp_path: Path) -> None:
    lock_file = tmp_path / LOCK_FILENAME
    held = tmp_path / "held"
    release = tmp_path / "release"
    child = subprocess.Popen(
        [sys.executable, "-c", _HOLD_SCRIPT, str(lock_file), str(held), str(release)],
        env=_child_env(),
    )
    try:
        _wait_for(held)
        lock = MutationLock(lock_file)
        with pytest.raises(LockTimeoutError):
            lock.acquire(timeout=0.2)
        release.write_text("go")
        lock.acquire()
        lock.release()
    finally:
        release.touch()
        child.wait(timeout=10)
    assert child.returncode == 0


def test_lock_released_when_process_exits(tmp_path: Path) -> None:
    lock_file = tmp_path / LOCK_FILENAME
    held = tmp_path / "held"
    child = subprocess.Popen(
        [sys.executable, "-c", _HOLD_SCRIPT, str(lock_file), str(held)],
        env=_child_env(),
    )
    _wait_for(held)
    assert child.wait(timeout=10) == 0
    with MutationLock(lock_file):
        pass


def test_concurrent_critical_sections_do_not_overlap(tmp_path: Path) -> None:
    lock_file = tmp_path / LOCK_FILENAME
    processes = []
    outputs = []
    for index in range(3):
        output = tmp_path / f"worker-{index}"
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    _WORKER_SCRIPT,
                    str(lock_file),
                    str(output),
                    "0.05",
                ],
                env=_child_env(),
            )
        )
        outputs.append(output)
    for process in processes:
        assert process.wait(timeout=30) == 0
    intervals = []
    for output in outputs:
        entered, exited = output.read_text().split()
        intervals.append((float(entered), float(exited)))
    intervals.sort()
    for previous, following in pairwise(intervals):
        assert following[0] >= previous[1] - 0.001
