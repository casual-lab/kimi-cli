from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..script import (
    InputStep,
    MarkStep,
    OutputCondition,
    ResizeStep,
    ScriptConfig,
    WaitStep,
)
from ..pty_runner import PtySize
from .model import (
    CommandStep,
    Expectation,
    ResizeStepDef,
    Scenario,
    ScenarioMeta,
    ScenarioStep,
    SnapshotStep,
    WaitStepDef,
)


@dataclass(slots=True)
class PlannedScenario:
    config: ScriptConfig
    scenario: Scenario


def build_script_config(
    scenario: Scenario,
    *,
    output_dir: Path | None = None,
) -> ScriptConfig:
    meta = scenario.meta
    destination = _resolve_output_dir(meta, output_dir)
    steps = _plan_steps(meta, scenario.steps)
    return ScriptConfig(
        command=meta.command,
        steps=steps,
        output_dir=destination,
        env=meta.env if meta.env else None,
        cwd=meta.cwd,
        pty_size=meta.pty_size,
        timeout=meta.timeout,
        read_timeout=meta.read_timeout,
    )


def _resolve_output_dir(meta: ScenarioMeta, override: Path | None) -> Path:
    if override is not None:
        return override
    if meta.output_dir is not None:
        return meta.output_dir
    base = Path.cwd() / "e2e_timewalker_runs"
    identifier = meta.identifier or "session"
    return base / identifier


def _plan_steps(meta: ScenarioMeta, steps: Sequence[ScenarioStep]) -> list[
    InputStep | WaitStep | MarkStep | ResizeStep
]:
    planned: list[InputStep | WaitStep | MarkStep | ResizeStep] = []
    for step in steps:
        if isinstance(step, CommandStep):
            planned.append(_build_input_step(step))
        elif isinstance(step, WaitStepDef):
            planned.append(_build_wait_step(step))
        elif isinstance(step, SnapshotStep):
            planned.append(MarkStep(label=step.label))
        elif isinstance(step, ResizeStepDef):
            planned.append(ResizeStep(size=PtySize(rows=step.rows, cols=step.cols)))
        else:  # pragma: no cover - defensive
            msg = f"Unsupported scenario step: {type(step)!r}"
            raise TypeError(msg)
    return planned


def _build_input_step(step: CommandStep) -> InputStep:
    condition = _to_condition(step.expect) if step.expect else None
    return InputStep(
        payload=step.run,
        mark=step.mark,
        expect=condition,
        expect_timeout=step.timeout,
        delay=step.delay,
        send_newline=step.send_newline,
    )


def _build_wait_step(step: WaitStepDef) -> WaitStep:
    condition = _to_condition(step.expect)
    return WaitStep(condition=condition, timeout=step.timeout)


def _to_condition(expect: Expectation) -> OutputCondition:
    return OutputCondition(contains=expect.contains, regex=expect.regex)
