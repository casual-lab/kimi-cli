from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class Keyframe:
    label: str
    offset: int
    timestamp: float


class AnsiStreamRecorder:
    """Persist raw ANSI byte stream to disk while tracking offsets."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("wb")
        self._offset = 0
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def offset(self) -> int:
        return self._offset

    def append(self, chunk: bytes) -> int:
        if not chunk:
            return self._offset

        with self._lock:
            self._file.write(chunk)
            self._offset += len(chunk)
            return self._offset

    def close(self) -> None:
        with self._lock:
            if self._file.closed:
                return
            self._file.flush()
            self._file.close()

    def __enter__(self) -> "AnsiStreamRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()


class KeyframeRegistry:
    """Maintain a list of logical keyframes during recording."""

    def __init__(self, recorder: AnsiStreamRecorder, json_path: Path) -> None:
        self._recorder = recorder
        self._json_path = json_path
        self._json_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[Keyframe] = []
        self._lock = threading.Lock()

    @property
    def records(self) -> list[Keyframe]:
        return list(self._records)

    def mark(self, label: str) -> Keyframe:
        with self._lock:
            frame = Keyframe(label=label, offset=self._recorder.offset, timestamp=time.time())
            self._records.append(frame)
            return frame

    def extend(self, frames: Iterable[Keyframe]) -> None:
        with self._lock:
            self._records.extend(frames)

    def flush(self) -> None:
        with self._lock:
            payload = [asdict(frame) for frame in self._records]
            self._json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
