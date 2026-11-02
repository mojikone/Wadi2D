"""``wadi2d rain``: what a rain file holds, for the dock. Interface: :func:`rain_info`.

A file offering more than one series answers with the choices and no frames, so the dock can ask which one.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from wadi2d.io.rain import rain_choices, rain_format, read_rain
from wadi2d.storm.rain_frames import RainSpec


def rain_info(
    source: str,
    variable: str | None = None,
    units: str = "auto",
    interval_min: float | None = None,
    stamp: str = "end",
    start: str | None = None,
) -> dict:
    """A JSON-ready summary; ``frames`` 0 with ``choices`` means the caller has to pick."""
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"{source} not found")
    choices = rain_choices(path)
    info: dict = {"format": rain_format(path), "choices": choices, "frames": 0}
    if variable is None and len(choices) > 1:
        return info
    frames = read_rain(path, RainSpec(variable, units, interval_min, stamp), start)
    totals = frames.totals()
    info.update(
        frames=frames.count,
        duration_min=float(frames.ends_min[-1] - frames.starts_min[0]),
        period_min=float(np.median(frames.ends_min - frames.starts_min)),
        start=None if frames.origin is None else str(frames.origin),
        rows=frames.rows,
        columns=frames.columns,
        pixel=[frames.dx, frames.dy],
        crs=frames.crs,
        mean_mm=float(np.nanmean(totals)),
        max_mm=float(np.nanmax(totals)),
        missing=frames.missing_share(),
        cumulative=frames.looks_cumulative(),
    )
    return info
