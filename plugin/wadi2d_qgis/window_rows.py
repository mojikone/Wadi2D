# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The window of his item 7 (W101) as plain values: the command, its folder, the words. No Qt here."""

from __future__ import annotations

from pathlib import Path

from .protocol import PIXEL_DEPTH, PIXEL_DIR, PIXEL_HAZARD, PIXEL_SPEED

WINDOWS_DIR = "windows"
WINDOW_TIMEOUT_S = 3600
BUTTON_WORDS = "Map a window at the terrain's finest resolution"
TIP = (
    "Draw a rectangle on the map: the run's depth, speed and hazard in it at the DEM's own pixel{pixel}, from the saved "
    "results; the maps of record are coarser by rule (W100). Nothing of the run is changed."
)
DRAW_WORDS = "Drag a rectangle on the map over the area to map at the terrain's finest resolution."
GROUP_WORDS = "Window at the DEM pixel, {name}"
LAYERS = ((PIXEL_DEPTH, "Depth, m", "depth"), (PIXEL_SPEED, "Speed, m/s", None), (PIXEL_HAZARD, "Hazard class", "hazard"))


def window_args(run: Path, box: tuple[float, float, float, float], out: Path) -> list[str]:
    """``wadi2d window`` at the DEM's own pixel (``--pixel 0``) into ``out``."""
    return ["window", str(run), *(f"{v:.3f}" for v in box), "--pixel", "0", "--out", str(out)]


def window_folder(run: Path, box: tuple[float, float, float, float]) -> Path:
    xmin, ymin, xmax, ymax = (round(v) for v in box)
    return Path(run) / PIXEL_DIR / WINDOWS_DIR / f"window_{xmin}_{ymin}_{xmax}_{ymax}_dem"


def tip_text(pixel: float | None) -> str:
    return TIP.format(pixel=f", {pixel:g} m on this DEM" if pixel else "")
