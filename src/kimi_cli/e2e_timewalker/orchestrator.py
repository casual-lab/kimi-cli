from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dsl import build_script_config, load_scenario
from .dsl.model import Scenario
from .script import ScriptConfig, ScriptDriver, SessionArtifacts


@dataclass(slots=True)
class ExecutionResult:
    scenario: Scenario
    config: ScriptConfig
    artifacts: SessionArtifacts


class ExecutionOrchestrator:
    """High-level runner that ties DSL parsing with the script driver."""

    def __init__(self, driver: ScriptDriver | None = None) -> None:
        self._driver = driver or ScriptDriver()

    def execute(
        self,
        source: Path | dict[str, Any],
        *,
        output_dir: Path | None = None,
    ) -> ExecutionResult:
        scenario = load_scenario(source)
        config = build_script_config(scenario, output_dir=output_dir)
        artifacts = self._driver.run(config)
        return ExecutionResult(scenario=scenario, config=config, artifacts=artifacts)
