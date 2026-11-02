# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading a run folder: the progress tail, the run state, the live raster's whereabouts. No Qt, no QGIS."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .protocol import (
    EXIT_FINISHED,
    LIVE_DEPTH,
    LIVE_LATEST,
    PROGRESS_FILE,
    RECENT_S,
    exit_message,
    pid_alive,
    read_run_info,
)

PRODUCT_STAGES = {
    "ground": "Pixel maps: reading the terrain",
    "maps": "Pixel maps: saved map",
    "rasters": "Pixel maps: writing the rasters",
    "smooth": "Pixel maps: drawing the polygons and the depth",
}


class ProgressTail:
    """Reads ``progress.jsonl`` from its last offset; a half-written last line waits for the next poll."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._offset = 0
        self._partial = b""

    def poll(self) -> list[dict]:
        """The events that arrived since the last call. The file is held open only while reading."""
        try:
            size = self.path.stat().st_size
            if size < self._offset:  # the file was replaced
                self._offset, self._partial = 0, b""
            if size == self._offset:
                return []
            with self.path.open("rb") as stream:
                stream.seek(self._offset)
                data = stream.read()
        except OSError:
            return []
        self._offset += len(data)
        lines = (self._partial + data).split(b"\n")
        self._partial = lines.pop()
        return [event for event in map(_parse, lines) if event is not None]


def _parse(line: bytes) -> dict | None:
    try:
        event = json.loads(line.decode("utf-8", "replace"))
    except ValueError:
        return None
    return event if isinstance(event, dict) and "ev" in event else None


@dataclass
class RunState:
    """Everything the dock shows about a run, folded from its events."""

    t_end: float | None = None
    t: float = 0.0
    dt: float | None = None
    wet_cells: int | None = None
    wet_area_km2: float | None = None
    mass_error: float | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    error_xy: tuple[float, float] | None = None
    finished: bool = False
    exit_code: int | None = None
    message: str = ""
    product_stage: str | None = None
    product_percent: float = 0.0
    product_done: int = 0
    product_of: int = 0
    products: str | None = None

    def apply(self, event: dict) -> None:
        kind = event.get("ev")
        if kind == "start":
            self.t_end = event.get("duration_s", self.t_end)
        elif kind == "step":
            self.t = event.get("t", self.t)
            self.dt = event.get("dt", self.dt)
            self.wet_cells = event.get("wet_cells", self.wet_cells)
            self.mass_error = event.get("mass_error", self.mass_error)
        elif kind == "products":
            self.product_stage = event.get("stage")
            self.product_percent = event.get("percent", self.product_percent)
            self.product_done = event.get("done", 0)
            self.product_of = event.get("of", 0)
        elif kind == "warn":
            self.warnings.append(str(event.get("message", "")))
        elif kind == "error":  # a numerical failure still writes its maps: only "done" or the exit ends a run
            self.error = str(event.get("message", ""))
            self.error_xy = event_xy(event)
            self.exit_code = event.get("code", self.exit_code)
        elif kind == "done":
            self.t = event.get("t", self.t)
            self.exit_code = event.get("code", self.exit_code)
            self.wet_area_km2 = event.get("wet_area_km2", self.wet_area_km2)
            balance = event.get("balance") or {}  # a short run ends before its first throttled "step"
            self.mass_error = balance.get("relative_error", self.mass_error)
            self.products = event.get("products", self.products)
            self.product_stage = None
            self.finished = True

    @property
    def percent(self) -> int:
        if self.product_stage is not None:
            return max(0, min(100, int(self.product_percent)))
        if not self.t_end:
            return 0
        return max(0, min(100, int(100 * self.t / self.t_end)))

    @property
    def status(self) -> str:
        """Simulated time, time step, wet cells and mass error on one line; or where the pixel maps have got to."""
        if self.product_stage is not None:
            return _product_status(self.product_stage, self.product_done, self.product_of)
        parts = [f"{_clock(self.t)} of {_clock(self.t_end)}" if self.t_end else _clock(self.t)]
        if self.dt is not None:
            parts.append(f"step {self.dt:.3g} s")
        if self.wet_cells is not None:
            parts.append(f"{self.wet_cells:,} wet cells")
        if self.wet_area_km2 is not None:
            parts.append(f"wet area {self.wet_area_km2:,.2f} km2")
        if self.mass_error is not None:
            parts.append(f"mass error {self.mass_error:.1e}")
        return " | ".join(parts)

    @property
    def succeeded(self) -> bool:
        return self.exit_code == EXIT_FINISHED

    def outcome(self) -> str:
        """The plain end-of-run message: what happened, the engine's words, and where."""
        words = [self.message or exit_message(self.exit_code)]
        if self.error:
            words.append(self.error.rstrip(". ") + ".")
        if self.error_xy:
            words.append(f"At x {self.error_xy[0]:,.1f}, y {self.error_xy[1]:,.1f} (marked on the map).")
        words.extend(warning.rstrip(". ") + "." for warning in dict.fromkeys(self.warnings))
        return " ".join(words)


def _product_status(stage: str, done: int, of: int) -> str:
    words = PRODUCT_STAGES.get(stage, "Pixel maps")
    if stage == "maps" and of:
        return f"{words}: {done} of {of}"
    return words


def event_xy(event: dict) -> tuple[float, float] | None:
    """The map position of an event's cell, in the DEM CRS, if it names one."""
    cell = event.get("cell")
    if isinstance(cell, dict) and cell.get("x") is not None and cell.get("y") is not None:
        return float(cell["x"]), float(cell["y"])
    return None


def _clock(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes // 60} h {minutes % 60:02d} min"


def read_state(out_dir: Path | str) -> RunState:
    """The state of a run folder from its whole progress file."""
    state = RunState(t_end=read_run_info(out_dir).get("t_end"))
    for event in ProgressTail(Path(out_dir) / PROGRESS_FILE).poll():
        state.apply(event)
    return state


def run_is_live(out_dir: Path | str) -> bool:
    """A run with no end in its progress file whose process exists, or which wrote very recently."""
    progress = Path(out_dir) / PROGRESS_FILE
    if not progress.is_file() or read_state(out_dir).finished:
        return False
    pid = read_run_info(out_dir).get("pid")
    if pid:
        return pid_alive(pid)
    return time.time() - progress.stat().st_mtime < RECENT_S


def live_source(out_dir: Path | str) -> tuple[Path, tuple[int, int]] | None:
    """Where the live depth raster is, and a stamp that changes when it is rewritten.

    ``live/depth.tif`` normally. If the engine cannot rewrite it in place (a Windows file lock), it writes
    numbered files and names the current one in ``live/latest.json``.
    """
    root = Path(out_dir)
    path = root / LIVE_DEPTH
    try:
        latest = json.loads((root / LIVE_LATEST).read_text(encoding="utf-8"))
        path = root / "live" / Path(latest["path"]).name
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        info = path.stat()
    except OSError:
        return None
    return path, (info.st_mtime_ns, info.st_size)
