from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import pyte
from pyte.screens import Char

from .pty_runner import PtySize
from .recording import Keyframe

_DEC_PRIVATE_RE = re.compile(r"\x1b\[(\?[\d;]*)([hl])")
_OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)

_DEFAULT_PALETTE = {
    "default": "#d0d0d0",
    "default_bg": "#000000",
    "black": "#000000",
    "red": "#d70000",
    "green": "#5f8700",
    "brown": "#875f00",
    "yellow": "#ffd700",
    "blue": "#005faf",
    "magenta": "#af005f",
    "cyan": "#00afaf",
    "white": "#ffffff",
    "brightblack": "#585858",
    "brightred": "#ff5f5f",
    "brightgreen": "#87ff5f",
    "brightyellow": "#ffffaf",
    "brightblue": "#5fd7ff",
    "brightmagenta": "#ff87ff",
    "brightcyan": "#5fffff",
    "brightwhite": "#ffffff",
}


@dataclass(slots=True)
class TerminalCapabilities:
    supports_dec_private: bool = False
    allow_osc: bool = False


@dataclass(slots=True)
class ParseWarning:
    kind: str
    original: str
    normalized: str | None = None
    message: str | None = None


@dataclass(slots=True)
class WarningEntry:
    offset: int
    warning: ParseWarning


class WarningCollector:
    def __init__(self) -> None:
        self._entries: list[WarningEntry] = []

    def add(self, warning: ParseWarning, *, offset: int) -> None:
        self._entries.append(WarningEntry(offset=offset, warning=warning))

    def extend(self, warnings: Iterable[WarningEntry]) -> None:
        self._entries.extend(warnings)

    def clear(self) -> None:
        self._entries.clear()

    @property
    def entries(self) -> Sequence[WarningEntry]:
        return tuple(self._entries)


class PrivateSequenceHandler:
    """Normalize or suppress private terminal control sequences."""

    def __init__(self, capabilities: TerminalCapabilities | None = None) -> None:
        self._capabilities = capabilities or TerminalCapabilities()

    def normalize(self, chunk: bytes) -> tuple[str, list[ParseWarning]]:
        text = chunk.decode("utf-8", errors="ignore")
        warnings: list[ParseWarning] = []

        def _dec_repl(match: re.Match[str]) -> str:
            if self._capabilities.supports_dec_private:
                return match.group(0)
            seq = match.group(0)
            warnings.append(ParseWarning(kind="dec-private", original=_repr_escape(seq), normalized=""))
            return ""

        def _osc_repl(match: re.Match[str]) -> str:
            if self._capabilities.allow_osc:
                return match.group(0)
            seq = match.group(0)
            warnings.append(ParseWarning(kind="osc-suppressed", original=_repr_escape(seq), normalized=""))
            return ""

        text = _DEC_PRIVATE_RE.sub(_dec_repl, text)
        text = _OSC_RE.sub(_osc_repl, text)
        return text, warnings


@dataclass(slots=True)
class CellStyle:
    char: str
    fg: str | None
    bg: str | None
    bold: bool
    reverse: bool


@dataclass(slots=True)
class ScreenState:
    offset: int
    cursor_row: int
    cursor_col: int
    cells: tuple[tuple[CellStyle, ...], ...]

    @property
    def text_lines(self) -> tuple[str, ...]:
        return tuple("".join(cell.char for cell in row) for row in self.cells)


@dataclass(slots=True)
class ReplayResult:
    states: list[ScreenState]
    warnings: Sequence[WarningEntry]


class AnsiReplayParser:
    def __init__(
        self,
        size: PtySize | None = None,
        *,
        handler: PrivateSequenceHandler | None = None,
        collector: WarningCollector | None = None,
    ) -> None:
        self._size = size or PtySize()
        self._handler = handler or PrivateSequenceHandler()
        self._collector = collector or WarningCollector()
        self._bytes_consumed = 0

    @property
    def bytes_consumed(self) -> int:
        return self._bytes_consumed

    @property
    def warnings(self) -> Sequence[WarningEntry]:
        return self._collector.entries

    def parse(self, path: Path, *, chunk_size: int = 4096) -> ReplayResult:
        screen = pyte.Screen(self._size.cols, self._size.rows)
        stream = pyte.Stream(screen)
        states: list[ScreenState] = []
        self._collector.clear()
        self._bytes_consumed = 0

        with path.open("rb") as handle:
            while True:
                raw = handle.read(chunk_size)
                if not raw:
                    break
                normalized, warnings = self._handler.normalize(raw)
                for warning in warnings:
                    self._collector.add(warning, offset=self._bytes_consumed)
                self._bytes_consumed += len(raw)
                if not normalized:
                    continue
                stream.feed(normalized)
                states.append(self._snapshot(screen, self._bytes_consumed))

        return ReplayResult(states=states, warnings=self._collector.entries)

    def _snapshot(self, screen: pyte.Screen, offset: int) -> ScreenState:
        rows: list[tuple[CellStyle, ...]] = []
        empty = Char(" ")
        for row_idx in range(screen.lines):
            row_buffer = screen.buffer.get(row_idx, {})
            cells: list[CellStyle] = []
            for col_idx in range(screen.columns):
                char = row_buffer.get(col_idx, empty)
                value = char.data if char.data else " "
                cells.append(
                    CellStyle(
                        char=value,
                        fg=char.fg,
                        bg=char.bg,
                        bold=bool(getattr(char, "bold", False)),
                        reverse=bool(getattr(char, "reverse", False)),
                    )
                )
            rows.append(tuple(cells))
        return ScreenState(
            offset=offset,
            cursor_row=screen.cursor.y,
            cursor_col=screen.cursor.x,
            cells=tuple(rows),
        )


def extract_keyframes(states: Sequence[ScreenState], keyframes: Sequence[Keyframe]) -> dict[str, ScreenState]:
    mapping: dict[str, ScreenState] = {}
    if not states:
        return mapping
    for frame in keyframes:
        candidate = _locate_state(states, frame.offset)
        if candidate is not None:
            mapping[frame.label] = candidate
    return mapping


def _locate_state(states: Sequence[ScreenState], offset: int) -> ScreenState | None:
    for state in states:
        if state.offset >= offset:
            return state
    return states[-1] if states else None


class HtmlRenderer:
    """Render screen states to standalone HTML files."""

    def __init__(self, palette: dict[str, str] | None = None) -> None:
        palette = palette or {}
        self._palette = {**_DEFAULT_PALETTE, **palette}

    def render(self, state: ScreenState, path: Path, *, title: str | None = None) -> None:
        html_text = self.render_to_string(state, title=title)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html_text, encoding="utf-8")

    def render_to_string(self, state: ScreenState, *, title: str | None = None) -> str:
        title = title or "Terminal Frame"
        body = "\n".join(self._render_line(idx, row, state) for idx, row in enumerate(state.cells))
        return (
            "<!DOCTYPE html>\n"
            "<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>{html.escape(title)}</title>\n"
            "<style>\n"
            "body { background: #1d1f21; color: #d0d0d0; font-family: 'Fira Code', 'Consolas', 'Menlo', monospace; }\n"
            "pre { line-height: 1.2; font-size: 14px; margin: 16px; }\n"
            ".cursor { outline: 1px solid #ffb454; }\n"
            "</style>\n</head>\n<body>\n<pre>\n"
            f"{body}\n"
            "</pre>\n</body>\n</html>\n"
        )

    def _render_line(self, row_idx: int, row: Sequence[CellStyle], state: ScreenState) -> str:
        fragments: list[str] = []
        for col_idx, cell in enumerate(row):
            fragments.append(self._render_cell(row_idx, col_idx, cell, state))
        return "".join(fragments)

    def _render_cell(self, row_idx: int, col_idx: int, cell: CellStyle, state: ScreenState) -> str:
        char = html.escape(cell.char) if cell.char not in {" ", ""} else "&nbsp;"
        fg = self._resolve_color(cell.fg or "default")
        bg = self._resolve_color(cell.bg or "default_bg")
        if cell.reverse:
            fg, bg = bg, fg
        styles = [f"color: {fg};", f"background: {bg};"]
        if cell.bold:
            styles.append("font-weight: bold;")
        classes: list[str] = []
        if row_idx == state.cursor_row and col_idx == state.cursor_col:
            classes.append("cursor")
        class_attr = f" class=\"{' '.join(classes)}\"" if classes else ""
        style_attr = f" style=\"{''.join(styles)}\""
        return f"<span{class_attr}{style_attr}>{char}</span>"

    def _resolve_color(self, name: str) -> str:
        return self._palette.get(name, self._palette["default"])


class ImageExporter:
    """Export screen states to PNG images using Pillow."""

    def __init__(
        self,
        *,
        font_path: str | None = None,
        font_size: int = 14,
        padding: int = 12,
        background: str = "#000000",
        foreground: str = "#f0f0f0",
    ) -> None:
        try:
            from PIL import ImageFont
        except ImportError as exc:  # pragma: no cover - dependency guard
            msg = "Pillow is required for ImageExporter"
            raise RuntimeError(msg) from exc

        from PIL import ImageFont  # noqa: PLC0415  # lazy import

        self._font = (
            ImageFont.truetype(font_path, font_size)
            if font_path is not None
            else ImageFont.load_default()
        )
        self._font_size = font_size
        self._padding = padding
        self._background = background
        self._foreground = foreground

    def render(self, state: ScreenState, path: Path) -> None:
        from PIL import Image, ImageDraw  # noqa: PLC0415  # lazy import

        lines = ["".join(cell.char for cell in row).rstrip(" ") for row in state.cells]
        if not lines:
            lines = [""]
        text = "\n".join(lines)

        dummy = Image.new("RGB", (1, 1), color=self._background)
        draw = ImageDraw.Draw(dummy)
        left, top, right, bottom = draw.multiline_textbbox((0, 0), text, font=self._font, spacing=0)
        width = max(1, right - left) + self._padding * 2
        height = max(1, bottom - top) + self._padding * 2

        image = Image.new("RGB", (width, height), color=self._background)
        draw = ImageDraw.Draw(image)
        draw.multiline_text(
            (self._padding, self._padding),
            text,
            font=self._font,
            fill=self._foreground,
            spacing=0,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)


def _repr_escape(seq: str) -> str:
    return json.dumps(seq)[1:-1]
