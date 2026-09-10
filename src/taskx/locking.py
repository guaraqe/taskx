"""Process-level serialization of taskx mutations through a file lock."""

from __future__ import annotations

import errno
import fcntl
import os
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path
from types import TracebackType
from typing import Self

from taskx.errors import LockTimeoutError, TaskxError

LOCK_FILENAME = "taskx.lock"
DEFAULT_TIMEOUT_SECONDS = 10.0
_POLL_INTERVAL_SECONDS = 0.01


def lock_path(env: Mapping[str, str] | None = None) -> Path:
    """Return the deterministic lock path for one Taskwarrior data store.

    ``TASKDATA`` isolates stores when set; otherwise a per-user runtime or
    cache location is used.
    """

    environment = os.environ if env is None else env
    taskdata = environment.get("TASKDATA", "").strip()
    if taskdata:
        return Path(taskdata).expanduser().resolve() / LOCK_FILENAME
    return _user_lock_directory(environment) / LOCK_FILENAME


def _user_lock_directory(env: Mapping[str, str]) -> Path:
    runtime_dir = env.get("XDG_RUNTIME_DIR", "").strip()
    if runtime_dir:
        return Path(runtime_dir).expanduser() / "taskx"
    cache_dir = env.get("XDG_CACHE_HOME", "").strip()
    if cache_dir:
        return Path(cache_dir).expanduser() / "taskx"
    home = env.get("HOME", "").strip()
    return (Path(home).expanduser() if home else Path.home()) / ".cache" / "taskx"


class MutationLock:
    """Exclusive advisory lock released on normal and exceptional exit."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: int | None = None

    @classmethod
    def for_environment(cls, env: Mapping[str, str] | None = None) -> Self:
        return cls(lock_path(env))

    @property
    def path(self) -> Path:
        return self._path

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def acquire(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        """Acquire the lock, waiting at most *timeout* seconds."""

        if self._fd is not None:
            raise TaskxError(f"lock already held: {self._path}")
        _ensure_parent_directory(self._path)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN):
                    os.close(fd)
                    raise
                if time.monotonic() >= deadline:
                    os.close(fd)
                    message = f"timed out acquiring lock: {self._path}"
                    raise LockTimeoutError(message) from None
                time.sleep(_POLL_INTERVAL_SECONDS)
        with suppress(OSError):
            os.fchmod(fd, 0o600)
        self._fd = fd

    def release(self) -> None:
        """Release the lock; calling this more than once has no effect."""

        fd = self._fd
        if fd is None:
            return
        self._fd = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _ensure_parent_directory(path: Path) -> None:
    directory = path.parent
    if directory.is_dir():
        return
    directory.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        directory.chmod(0o700)


@contextmanager
def mutation_lock(
    env: Mapping[str, str] | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Iterator[MutationLock]:
    """Hold the process lock for one Taskwarrior data store."""

    lock = MutationLock.for_environment(env)
    lock.acquire(timeout)
    try:
        yield lock
    finally:
        lock.release()
