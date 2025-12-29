from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest

from kimi_cli.e2e_timewalker import (
    ExecutionOrchestrator,
    InputStep,
    MarkStep,
    ResizeStep,
    ScriptDriver,
    WaitStep,
)
from kimi_cli.e2e_timewalker.dsl import build_script_config, load_scenario


@pytest.fixture()
def simple_scenario() -> dict:
    return {
        "name": "demo",
        "meta": {
            "id": "demo",
            "command": ["/bin/sh"],
            "timeout": 15,
            "pty": {"rows": 30, "cols": 120},
        },
        "steps": [
            {
                "type": "command",
                "run": "printf 'dsl-step'",
                "mark": "after-command",
                "expect": {"contains": "dsl"},
                "timeout": 5,
            },
            {"type": "wait", "expect": {"contains": "dsl-step"}},
            {"type": "snapshot", "label": "snapshot-1"},
            {"type": "resize", "rows": 40, "cols": 100},
            {"type": "command", "run": "exit", "send_newline": True},
        ],
    }


def test_build_script_config_from_scenario(simple_scenario: dict, artifact_dir: Path) -> None:
    scenario = load_scenario(simple_scenario)
    config = build_script_config(scenario, output_dir=artifact_dir / "run")

    assert isinstance(config.steps[0], InputStep)
    assert isinstance(config.steps[1], WaitStep)
    assert isinstance(config.steps[2], MarkStep)
    assert isinstance(config.steps[3], ResizeStep)
    assert config.steps[0].expect_timeout == 5
    assert config.steps[0].expect and config.steps[0].expect.contains == "dsl"


def test_orchestrator_runs_scenario(simple_scenario: dict, artifact_dir: Path) -> None:
    orchestrator = ExecutionOrchestrator(driver=ScriptDriver())
    result = orchestrator.execute(simple_scenario, output_dir=artifact_dir / "orchestrated")

    assert result.artifacts.exit_status == 0
    assert any(frame.label == "after-command" for frame in result.artifacts.keyframes)
    assert (result.artifacts.ansi_path).exists()


def test_invalid_scenario_raises_validation_error() -> None:
    bad = {"meta": {"cwd": "."}, "steps": []}
    with pytest.raises(jsonschema.ValidationError):
        load_scenario(bad)
