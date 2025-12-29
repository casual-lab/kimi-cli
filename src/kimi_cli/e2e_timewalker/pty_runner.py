from __future__ import annotations

import fcntl
import os
import pty
import selectors
import signal
import struct
import subprocess
import termios
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping


@dataclass(slots=True)
class PtySize:
    """Terminal size descriptor."""

    rows: int = 24
    cols: int = 80


@dataclass(slots=True)
class PtyExitStatus:
    """Exit information for a PTY-backed subprocess."""

    returncode: int | None
    signal: int | None

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and self.signal is None


class PtySessionRunner:
    """Context manager that launches a subprocess inside a PTY."""

    def __init__(
        self,
        command: Iterable[str],
        *,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        size: PtySize | None = None,
        read_chunk_size: int = 4096,
    ) -> None:
        if not command:
            msg = "Command must not be empty"
            raise ValueError(msg)

        self._command = list(command)
        self._env = self._prepare_env(env)
        self._cwd = cwd
        self._size = size or PtySize()
        self._chunk_size = read_chunk_size

        self._master_fd: int | None = None
        self._slave_fd: int | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._selector = selectors.DefaultSelector()

    def __enter__(self) -> "PtySessionRunner":
        master_fd, slave_fd = pty.openpty()
        self._master_fd = master_fd
        self._slave_fd = slave_fd

        os.set_blocking(master_fd, False)
        self._selector.register(master_fd, selectors.EVENT_READ)
        self._apply_winsize(self._size)

        self._process = subprocess.Popen(
            self._command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=self._env,
            cwd=str(self._cwd) if self._cwd is not None else None,
            start_new_session=True,
            close_fds=True,
        )

        # Close the slave in parent process to avoid descriptor leaks.
        os.close(slave_fd)
        self._slave_fd = None
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        try:
            if self._process and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self._process.kill()
        finally:
            if self._process is not None:
                try:
                    self._process.wait(timeout=1)
                except subprocess.TimeoutExpired:  # pragma: no cover - safety
                    pass
            if self._master_fd is not None:
                self._selector.unregister(self._master_fd)
                os.close(self._master_fd)
            if self._slave_fd is not None:
                os.close(self._slave_fd)

            self._master_fd = None
            self._slave_fd = None
            self._process = None

    @property
    def master_fd(self) -> int:
        if self._master_fd is None:
            msg = "Master FD is not initialised"
            raise RuntimeError(msg)
        return self._master_fd

    @property
    def process(self) -> subprocess.Popen[bytes]:
        if self._process is None:
            msg = "Process is not running"
            raise RuntimeError(msg)
        return self._process

    def read(self, timeout: float | None = None) -> bytes:
        """Read a chunk from the PTY master side."""

        events = self._selector.select(timeout)
        if not events:
            raise TimeoutError("PTY read timed out")

        data = os.read(self.master_fd, self._chunk_size)
        return data

    def write(self, data: bytes) -> int:
        """Write bytes to the PTY master."""

        return os.write(self.master_fd, data)

    def wait(self, timeout: float | None = None) -> PtyExitStatus:
        """Wait for the subprocess to finish."""

        proc = self.process
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - pass-through
            raise TimeoutError("Subprocess did not exit within timeout") from exc

        returncode = proc.returncode
        if returncode is None:
            return PtyExitStatus(returncode=None, signal=None)
        if returncode < 0:
            return PtyExitStatus(returncode=None, signal=abs(returncode))
        return PtyExitStatus(returncode=returncode, signal=None)

    def terminate(self, sig: int = signal.SIGTERM) -> None:
        """Forward a termination signal to the subprocess."""

        try:
            self.process.send_signal(sig)
        except ProcessLookupError:  # pragma: no cover - race condition guard
            return

    def is_running(self) -> bool:
        return self.process.poll() is None

    def resize(self, size: PtySize) -> None:
        """Adjust the underlying PTY window size."""

        self._size = size
        self._apply_winsize(size)

    def _apply_winsize(self, size: PtySize) -> None:
        if self._master_fd is None:
            msg = "PTY not initialised"
            raise RuntimeError(msg)

        packed = struct.pack("HHHH", size.rows, size.cols, 0, 0)
        fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, packed)
        if self._slave_fd is not None:
            fcntl.ioctl(self._slave_fd, termios.TIOCSWINSZ, packed)

    @staticmethod
    def _prepare_env(env: Mapping[str, str] | None) -> MutableMapping[str, str]:
        merged: MutableMapping[str, str] = dict(os.environ)
        if env is not None:
            merged.update(env)
        return merged
