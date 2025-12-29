from __future__ import annotations

from pathlib import Path

from kimi_cli.e2e_timewalker import (
    AnsiReplayParser,
    HtmlRenderer,
    ImageExporter,
    InputStep,
    OutputCondition,
    PrivateSequenceHandler,
    PtySize,
    ScriptConfig,
    ScriptDriver,
    TerminalCapabilities,
    extract_keyframes,
)


def test_private_sequence_handler_suppresses_private_sequences() -> None:
    handler = PrivateSequenceHandler(capabilities=TerminalCapabilities())
    chunk = b"\x1b[?25lHello\x1b]8;;https://example.com\x1b\\"
    normalized, warnings = handler.normalize(chunk)
    assert "Hello" in normalized
    assert not normalized.startswith("\x1b[?25l")
    kinds = {warning.kind for warning in warnings}
    assert "dec-private" in kinds
    assert "osc-suppressed" in kinds


def test_replay_parser_and_keyframe_extraction(artifact_dir: Path) -> None:
    output_dir = artifact_dir / "session"
    config = ScriptConfig(
        command=["/bin/sh"],
        steps=[
            InputStep(
                payload="printf 'frame-one'",
                mark="first",
                expect=OutputCondition(contains="frame-one"),
            ),
            InputStep(payload="printf ' frame-two'", mark="second"),
            InputStep(payload="exit"),
        ],
        output_dir=output_dir,
        timeout=10.0,
        pty_size=PtySize(rows=24, cols=120),
    )
    artifacts = ScriptDriver().run(config)

    parser = AnsiReplayParser(size=PtySize(rows=24, cols=120))
    replay_result = parser.parse(artifacts.ansi_path)
    assert replay_result.states, "expected at least one screen state"

    frames = extract_keyframes(replay_result.states, artifacts.keyframes)
    assert "first" in frames and "second" in frames
    assert "frame-one" in "\n".join(frames["first"].text_lines)

    html_output = output_dir / "first.html"
    HtmlRenderer().render(frames["first"], html_output, title="Test Frame")
    assert html_output.exists()
    assert "Terminal Frame" not in html_output.read_text(encoding="utf-8")

    image_output = output_dir / "first.png"
    ImageExporter().render(frames["first"], image_output)
    assert image_output.exists()
