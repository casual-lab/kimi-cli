from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..pty_runner import PtySize
from .schema import validate_scenario


@dataclass(slots=True)
class Expectation:
    contains: str | None = None
    regex: str | None = None

    def to_dict(self) -> dict[str, str]:  # pragma: no cover - debugging helper
        data: dict[str, str] = {}
        if self.contains is not None:
            data["contains"] = self.contains
        if self.regex is not None:
            data["regex"] = self.regex
        return data


@dataclass(slots=True)
class ScenarioMeta:
    command: list[str]
    cwd: Path | None
    env: dict[str, str]
    pty_size: PtySize
    timeout: float
    read_timeout: float
    output_dir: Path | None
    identifier: str | None


@dataclass(slots=True)
class ScenarioStep:
    kind: str


@dataclass(slots=True)
class CommandStep(ScenarioStep):
    run: str
    mark: str | None
    expect: Expectation | None
    timeout: float | None
    delay: float
    send_newline: bool


@dataclass(slots=True)
class WaitStepDef(ScenarioStep):
    expect: Expectation
    timeout: float


@dataclass(slots=True)
class SnapshotStep(ScenarioStep):
    label: str


@dataclass(slots=True)
class ResizeStepDef(ScenarioStep):
    rows: int
    cols: int


@dataclass(slots=True)
class Scenario:
    meta: ScenarioMeta
    steps: list[ScenarioStep]
    name: str | None = None
    description: str | None = None


def load_scenario(source: Path | dict[str, Any]) -> Scenario:
    if isinstance(source, Path):
        data = json.loads(source.read_text(encoding="utf-8"))
    else:
        data = source
    validate_scenario(data)

    meta_raw = data["meta"]
    command = list(meta_raw["command"])
    cwd = Path(meta_raw["cwd"]) if "cwd" in meta_raw else None
    env = {str(k): str(v) for k, v in meta_raw.get("env", {}).items()}
    pty_raw = meta_raw.get("pty")
    if pty_raw:
        pty_size = PtySize(rows=int(pty_raw["rows"]), cols=int(pty_raw["cols"]))
    else:
        pty_size = PtySize()
    timeout = float(meta_raw.get("timeout", 120.0))
    read_timeout = float(meta_raw.get("read_timeout", 0.2))
    output_dir = Path(meta_raw["output_dir"]) if "output_dir" in meta_raw else None

    meta = ScenarioMeta(
        command=command,
        cwd=cwd,
        env=env,
        pty_size=pty_size,
        timeout=timeout,
        read_timeout=read_timeout,
        output_dir=output_dir,
        identifier=meta_raw.get("id"),
    )

    steps = [
        _parse_step(raw_step)
        for raw_step in data.get("steps", [])
    ]

    return Scenario(
        meta=meta,
        steps=steps,
        name=data.get("name"),
        description=data.get("description"),
    )


def _parse_step(payload: dict[str, Any]) -> ScenarioStep:
    kind = payload["type"]
    if kind == "command":
        expect = _parse_expect(payload.get("expect"))
        return CommandStep(
            kind=kind,
            run=payload["run"],
            mark=payload.get("mark"),
            expect=expect,
            timeout=float(payload["timeout"]) if "timeout" in payload else None,
            delay=float(payload.get("delay", 0.0)),
            send_newline=bool(payload.get("send_newline", True)),
        )
    if kind == "wait":
        expect_payload = payload.get("expect")
        if expect_payload is None:
            msg = "wait step requires expect"
            raise ValueError(msg)
        expect = _parse_expect(expect_payload)
        return WaitStepDef(
            kind=kind,
            expect=expect,
            timeout=float(payload.get("timeout", 10.0)),
        )
    if kind == "snapshot":
        return SnapshotStep(kind=kind, label=payload["label"])
    if kind == "resize":
        return ResizeStepDef(kind=kind, rows=int(payload["rows"]), cols=int(payload["cols"]))
    msg = f"Unsupported step kind: {kind}"
    raise ValueError(msg)


def _parse_expect(payload: dict[str, Any] | None) -> Expectation | None:
    if payload is None:
        return None
    contains = payload.get("contains")
    regex = payload.get("regex")
    return Expectation(contains=contains, regex=regex)
