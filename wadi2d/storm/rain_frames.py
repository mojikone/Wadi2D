"""Rain on a regular grid, one frame per period: what every rain file becomes.

Interface: :class:`RainFrames`, :class:`RainSpec`, :class:`PixelSeries`, :func:`depth_in_mm`. A reader of a file format
turns the file into frames and nothing else; the storm, the cells and the lumped network read only frames. Depths are mm
fallen in the period, whatever the file held. Row 0 is the northern row and column 0 the western one, so a reader flips
what it has to. NaN means no data, which is not the same as no rain. Minutes count from the start of the first period
until :meth:`RainFrames.since` moves them to the start of a run.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Self

import numpy as np

from wadi2d.storm.base import FloatArray

SECONDS_PER_MINUTE = 60.0
NOISE_MM = 1e-3
"""Packing leaves small negative depths where it rained nothing; anything deeper is a flag for no data."""
MINUTES_PER = {"s": 1.0 / SECONDS_PER_MINUTE, "min": 1.0, "h": 60.0, "d": 1440.0}
MM_PER = {
    "mm": 1.0, "millimeter": 1.0, "millimeters": 1.0, "millimetre": 1.0, "millimetres": 1.0, "kgm-2": 1.0, "kg/m2": 1.0,
    "cm": 10.0, "m": 1000.0, "meter": 1000.0, "meters": 1000.0, "metre": 1000.0, "metres": 1000.0, "in": 25.4,
    "inch": 25.4, "inches": 25.4,
}  # fmt: skip
TIME_WORDS = {
    "s": "s", "sec": "s", "second": "s", "min": "min", "minute": "min", "h": "h", "hr": "h", "hour": "h", "d": "d",
    "day": "d",
}  # fmt: skip
MIN_CUMULATIVE_FRAMES = 4


def _time_unit(text: str) -> str | None:
    word = text.removesuffix("-1")
    return TIME_WORDS.get(word) or TIME_WORDS.get(word.removesuffix("s"))


def _read_units(text: str) -> tuple[float, float | None] | None:
    """(mm per unit, minutes the unit is per); None per means a depth. None for units this cannot read."""
    plain = text.strip().lower().replace("**", "").replace("^", "")
    words = plain.split()
    joined = "".join(words)
    if joined in MM_PER:
        return MM_PER[joined], None
    if "/" in joined:
        depth, _, per = joined.rpartition("/")
    elif len(words) > 1:
        depth, per = "".join(words[:-1]), words[-1]
    else:
        return None
    unit = _time_unit(per)
    if depth in MM_PER and unit is not None:
        return MM_PER[depth], MINUTES_PER[unit]
    return None


def depth_in_mm(values: np.ndarray, units: str, forced: str, period_min: np.ndarray) -> np.ndarray:
    """Depth fallen in each period, frames first. ``forced`` is the job's word on the units, ``auto`` the file's."""
    text = units if forced == "auto" else forced
    read = _read_units(text)
    if read is None:
        raise ValueError(f"the units {text!r} of this rain cannot be read: set the units by hand")
    factor, per = read
    out = values.astype(np.float64) * factor
    if per is not None:
        out = out * (period_min / per).reshape(-1, *([1] * (out.ndim - 1)))
    out[out < -NOISE_MM] = np.nan
    return np.where(out < 0.0, 0.0, out)


@dataclass(frozen=True)
class RainSpec:
    """What a job says about a rain file, beyond its path."""

    variable: str | None = None
    """The NetCDF variable, or B/C/F of a DSS pathname; None takes the only one there is."""
    units: str = "auto"
    interval_min: float | None = None
    """Period of a file that has none of its own."""
    stamp: str = "end"
    """Whether a bare time closes its period or opens it; a file with period bounds never needs this."""


@dataclass(frozen=True, eq=False)
class RainFrames:
    """``depths`` is (frames, rows, columns) in mm; ``west`` and ``north`` are the outer corner of the grid."""

    depths: np.ndarray
    starts_min: FloatArray
    ends_min: FloatArray
    west: float
    north: float
    dx: float
    dy: float
    crs: str = ""
    origin: np.datetime64 | None = None
    """The date of minute zero; None for a file with no dates."""

    def __post_init__(self) -> None:
        if self.depths.ndim != 3 or self.depths.shape[0] == 0:
            raise ValueError("rain frames must be (frames, rows, columns), with at least one frame")
        if self.starts_min.size != self.depths.shape[0] or self.ends_min.size != self.depths.shape[0]:
            raise ValueError("rain frames need one start and one end per frame")
        if np.any(self.ends_min <= self.starts_min) or np.any(self.starts_min[1:] < self.ends_min[:-1]):
            raise ValueError("rain periods must run forward and must not overlap")
        if self.dx <= 0.0 or self.dy <= 0.0:
            raise ValueError("rain pixels must have a size")

    @property
    def count(self) -> int:
        return self.depths.shape[0]

    @property
    def rows(self) -> int:
        return self.depths.shape[1]

    @property
    def columns(self) -> int:
        return self.depths.shape[2]

    def pixel_of(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Flat index of the pixel each point falls in, -1 off the grid; ``x`` and ``y`` in this grid's system."""
        column = np.floor((np.asarray(x) - self.west) / self.dx)
        row = np.floor((self.north - np.asarray(y)) / self.dy)
        inside = (column >= 0) & (column < self.columns) & (row >= 0) & (row < self.rows)
        flat = row * self.columns + column
        return np.where(inside, np.nan_to_num(flat), -1.0).astype(np.int64)

    def totals(self) -> FloatArray:
        """Depth over the whole event per pixel; NaN where a pixel never had data."""
        seen = np.isfinite(self.depths).any(axis=0)
        return np.where(seen, np.nansum(self.depths, axis=0), np.nan)

    def missing_share(self) -> float:
        """The share of pixels and frames with no data, among pixels that have data in some frame."""
        seen = np.isfinite(self.depths).any(axis=0)
        if not seen.any():
            return 1.0
        return float(np.count_nonzero(np.isnan(self.depths[:, seen]))) / (self.count * int(seen.sum()))

    def looks_cumulative(self) -> bool:
        """True when every frame holds at least what the one before held: a forecast's rain since its start, perhaps."""
        if self.count < MIN_CUMULATIVE_FRAMES:
            return False
        peak = np.nan_to_num(self.depths).max(axis=(1, 2))
        return bool(peak[-1] > 0.0 and np.all(np.diff(peak) >= 0.0) and peak[-1] > peak[0])

    def since(self, start: np.datetime64) -> Self:
        """The frames from this date on, with minute zero there; a period cut by the date keeps its share of rain."""
        if self.origin is None:
            raise ValueError("this rain has no dates, so a start date means nothing")
        shift = float((start - self.origin) / np.timedelta64(1, "s")) / SECONDS_PER_MINUTE
        keep = self.ends_min > shift
        if not keep.any():
            raise ValueError(f"the rain ends before the run's start date {start}")
        starts, ends = self.starts_min[keep] - shift, self.ends_min[keep] - shift
        depths = self.depths[keep].copy()
        if starts[0] < 0.0:
            depths[0] *= ends[0] / (ends[0] - starts[0])
            starts = starts.copy()
            starts[0] = 0.0
        return replace(self, depths=depths, starts_min=starts, ends_min=ends, origin=start)


class PixelSeries:
    """Cumulative rain of some pixels against time, linear inside a period and level across a gap between periods."""

    def __init__(self, frames: RainFrames, pixels: np.ndarray) -> None:
        self.edges = np.unique(np.concatenate((frames.starts_min, frames.ends_min)))
        steps = np.zeros((self.edges.size - 1, pixels.size))
        at = np.searchsorted(self.edges, frames.starts_min)
        steps[at] = np.nan_to_num(frames.depths.reshape(frames.count, -1)[:, pixels])
        self.cumulative = np.vstack((np.zeros(pixels.size), np.cumsum(steps, axis=0)))

    def at(self, minutes: float) -> FloatArray:
        """Depth fallen by this time, one value per pixel."""
        if minutes <= self.edges[0]:
            return self.cumulative[0]
        if minutes >= self.edges[-1]:
            return self.cumulative[-1]
        k = int(np.searchsorted(self.edges, minutes, side="right")) - 1
        share = (minutes - self.edges[k]) / (self.edges[k + 1] - self.edges[k])
        return self.cumulative[k] + (self.cumulative[k + 1] - self.cumulative[k]) * share
