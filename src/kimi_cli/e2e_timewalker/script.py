from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .pty_runner import PtySessionRunner, PtySize
from .recording import AnsiStreamRecorder, Keyframe, KeyframeRegistry


class OutputBuffer:
    """Thread-safe collector for PTY output."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._condition = threading.Condition()

    def append(self, chunk: bytes) -> None:
        if not chunk:
            return
        with self._condition:
            self._buffer.extend(chunk)
            self._condition.notify_all()

    def snapshot(self) -> bytes:
        with self._condition:
            return bytes(self._buffer)

    def wait_until(self, predicate: Callable[[str], bool], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                if predicate(self._decode_locked()):
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)

    def _decode_locked(self) -> str:
        return self._buffer.decode("utf-8", errors="ignore")

    def as_text(self) -> str:
        with self._condition:
            return self._decode_locked()


@dataclass(slots=True)
class OutputCondition:
    contains: str | None = None
    regex: str | None = None
    predicate: Callable[[str], bool] | None = None

    def __post_init__(self) -> None:
        if self.contains is None and self.regex is None and self.predicate is None:
            msg = "At least one condition must be provided"
            raise ValueError(msg)
        if self.regex is not None:
            re.compile(self.regex)

    def matches(self, text: str) -> bool:
        if self.contains and self.contains in text:
            return True
        if self.regex and re.search(self.regex, text):
            return True
        if self.predicate and self.predicate(text):
            return True
        return False

    def __repr__(self) -> str:  # pragma: no cover - trivial
        parts: list[str] = []
        if self.contains is not None:
            parts.append(f"contains={self.contains!r}")
        if self.regex is not None:
            parts.append(f"regex={self.regex!r}")
        if self.predicate is not None:
            parts.append(f"predicate={self.predicate!r}")
        return f"OutputCondition({', '.join(parts)})"


@dataclass(slots=True)
class InputStep:
    payload: str
    mark: str | None = None
    expect: OutputCondition | None = None
    expect_timeout: float | None = None
    delay: float = 0.0
    send_newline: bool = True


@dataclass(slots=True)
class WaitStep:
    condition: OutputCondition
    timeout: float = 5.0


@dataclass(slots=True)
class MarkStep:
    label: str


@dataclass(slots=True)
class ResizeStep:
    size: PtySize


Step = InputStep | WaitStep | MarkStep | ResizeStep


@dataclass(slots=True)
class ScriptConfig:
    command: Sequence[str]
    steps: Sequence[Step]
    output_dir: Path
    env: dict[str, str] | None = None
    cwd: Path | None = None
    pty_size: PtySize = field(default_factory=PtySize)
    timeout: float = 60.0
    read_timeout: float = 0.2


@dataclass(slots=True)
class SessionArtifacts:
    exit_status: int | None
    signal: int | None
    ansi_path: Path
    keyframes: list[Keyframe]


class OutputPump(threading.Thread):
    """Background thread that drains PTY output into recorder and buffer."""

    def __init__(
        self,
        runner: PtySessionRunner,
        recorder: AnsiStreamRecorder,
        buffer: OutputBuffer,
        read_timeout: float,
    ) -> None:
        super().__init__(daemon=True)
        self._runner = runner
        self._recorder = recorder
        self._buffer = buffer
        self._read_timeout = read_timeout
        self._stop_event = threading.Event()

    def run(self) -> None:  # noqa: D401 - standard thread run
        while not self._stop_event.is_set():
            try:
                chunk = self._runner.read(timeout=self._read_timeout)
            except TimeoutError:
                if not self._runner.is_running():
                    break
                continue
            if not chunk:
                if not self._runner.is_running():
                    break
                continue
            self._recorder.append(chunk)
            self._buffer.append(chunk)
        # Drain any remaining output after process exit.
        while True:
            try:
                chunk = self._runner.read(timeout=0.05)
            except TimeoutError:
                break
            if not chunk:
                break
            self._recorder.append(chunk)
            self._buffer.append(chunk)

    def stop(self) -> None:
        self._stop_event.set()


class ScriptDriver:
    """Execute a scripted scenario and capture artefacts."""

    def run(self, config: ScriptConfig) -> SessionArtifacts:
        output_dir = config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        ansi_path = output_dir / "ansi.bin"
        keyframe_path = output_dir / "keyframes.json"

        buffer = OutputBuffer()

        with PtySessionRunner(
            config.command,
            env=config.env,
            cwd=config.cwd,
            size=config.pty_size,
        ) as session, AnsiStreamRecorder(ansi_path) as recorder:
            registry = KeyframeRegistry(recorder, keyframe_path)
            pump = OutputPump(session, recorder, buffer, config.read_timeout)
            pump.start()
            exit_info = None
            try:
                self._execute_steps(config.steps, session, registry, buffer)
                exit_info = session.wait(timeout=config.timeout)
            finally:
                pump.stop()
                pump.join(timeout=2)
                registry.flush()

        if exit_info is None:  # pragma: no cover - defensive
            raise RuntimeError("Session terminated without exit status")

        return SessionArtifacts(
            exit_status=exit_info.returncode,
            signal=exit_info.signal,
            ansi_path=ansi_path,
            keyframes=registry.records,
        )

    def _execute_steps(
        self,
        steps: Sequence[Step],
        session: PtySessionRunner,
        registry: KeyframeRegistry,
        buffer: OutputBuffer,
    ) -> None:
        for step in steps:
            if isinstance(step, InputStep):
                self._run_input_step(step, session, registry, buffer)
            elif isinstance(step, WaitStep):
                self._run_wait_step(step, buffer)
            elif isinstance(step, MarkStep):
                registry.mark(step.label)
            elif isinstance(step, ResizeStep):
                session.resize(step.size)
            else:  # pragma: no cover - defensive guard
                msg = f"Unsupported step type: {type(step)!r}"
                raise TypeError(msg)

    def _run_input_step(
        self,
        step: InputStep,
        session: PtySessionRunner,
        registry: KeyframeRegistry,
        buffer: OutputBuffer,
    ) -> None:
        if step.delay > 0:
            time.sleep(step.delay)

        payload = step.payload.encode()
        if step.send_newline and not payload.endswith(b"\n"):
            payload += b"\n"
        session.write(payload)

        if step.mark:
            registry.mark(step.mark)

        if step.expect:
            timeout = step.expect_timeout if step.expect_timeout is not None else 5.0
            matched = buffer.wait_until(step.expect.matches, timeout=timeout)
            if not matched:
                snapshot = buffer.as_text()[-200:]
                msg = (
                    "Condition not met for input step. "
                    f"Expectation: {step.expect!r}, buffer tail: {snapshot}"
                )
                raise TimeoutError(msg)

    def _run_wait_step(self, step: WaitStep, buffer: OutputBuffer) -> None:
        matched = buffer.wait_until(step.condition.matches, timeout=step.timeout)
        if not matched:
            snapshot = buffer.as_text()[-200:]
            msg = (
                "Wait step timed out. "
                f"Expectation: {step.condition!r}, buffer tail: {snapshot}"
            )
            raise TimeoutError(msg)
