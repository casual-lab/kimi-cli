from __future__ import annotations

from pathlib import Path

from kimi_cli.e2e_timewalker import (
    AnsiStreamRecorder,
    InputStep,
    KeyframeRegistry,
    OutputCondition,
    PtySize,
    ScriptConfig,
    ScriptDriver,
    WaitStep,
)


def test_recorder_tracks_offsets(artifact_dir: Path) -> None:
    file_path = artifact_dir / "ansi.bin"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    recorder = AnsiStreamRecorder(file_path)
    try:
        assert recorder.append(b"hello") == 5
        assert recorder.append(b" world") == 11
    finally:
        recorder.close()

    assert file_path.read_bytes() == b"hello world"


def test_keyframe_registry_marks_positions(artifact_dir: Path) -> None:
    file_path = artifact_dir / "ansi.bin"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    recorder = AnsiStreamRecorder(file_path)
    try:
        recorder.append(b"first line\n")
        registry = KeyframeRegistry(recorder, artifact_dir / "keyframes.json")
        first = registry.mark("start")
        recorder.append(b"second line\n")
        second = registry.mark("after-second")
        registry.flush()
    finally:
        recorder.close()

    assert first.offset == len(b"first line\n")
    assert second.offset == len(b"first line\nsecond line\n")

    payload = (artifact_dir / "keyframes.json").read_text(encoding="utf-8")
    assert "start" in payload and "after-second" in payload


def test_script_driver_runs_interactive_shell(artifact_dir: Path) -> None:
    output_dir = artifact_dir / "session"
    output_dir.mkdir(parents=True, exist_ok=True)
    config = ScriptConfig(
        command=["/bin/sh"],
        steps=[
            InputStep(payload="printf 'hello world'", mark="after-print", expect=OutputCondition(contains="hello")),
            WaitStep(condition=OutputCondition(contains="hello world"), timeout=5.0),
            InputStep(payload="exit", expect=None),
        ],
        output_dir=output_dir,
        timeout=10.0,
        pty_size=PtySize(rows=30, cols=120),
    )

    artifacts = ScriptDriver().run(config)

    assert artifacts.exit_status == 0
    assert artifacts.signal is None
    assert artifacts.ansi_path.exists()
    content = artifacts.ansi_path.read_bytes()
    assert b"hello world" in content
    assert any(frame.label == "after-print" for frame in artifacts.keyframes)
