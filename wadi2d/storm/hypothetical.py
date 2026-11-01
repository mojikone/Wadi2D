"""HMS Hypothetical Storm: a depth, a percent-graph pattern, an area reduction.

Interface: :class:`PercentPattern`, :class:`HypotheticalStorm`. One factor at the storm area scales the whole
depth; the pattern is interpolated linearly at the time asked for, and :class:`CumulativeStorm` turns that into
period-ending increments. Reproduces the HMS 4.12 series on Block 2 to 6e-5 mm (research note H03).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Self

import numpy as np
from numpy.typing import ArrayLike

from wadi2d.storm.arf import ArfTable
from wadi2d.storm.base import STORM_METHODS, CumulativeStorm, FloatArray

PERCENT = 100.0
MINUTES_PER_HOUR = 60.0
HYPOTHETICAL_STORM = "Hypothetical Storm"


@dataclass(frozen=True, eq=False)
class PercentPattern:
    """A cumulative pattern: percent of the duration against percent of the depth."""

    time_percent: FloatArray
    depth_percent: FloatArray

    def __post_init__(self) -> None:
        if len(self.time_percent) != len(self.depth_percent):
            raise ValueError("a percent pattern needs one depth ordinate per time ordinate")
        if np.any(np.diff(self.time_percent) <= 0.0) or np.any(np.diff(self.depth_percent) < 0.0):
            raise ValueError("a percent pattern must rise with time")

    def fraction(self, time_fraction: FloatArray) -> FloatArray:
        """The fraction of the depth fallen at each fraction of the duration; 0 before, 1 after."""
        return np.interp(time_fraction * PERCENT, self.time_percent, self.depth_percent) / PERCENT


@STORM_METHODS.register(HYPOTHETICAL_STORM)
@dataclass(frozen=True, eq=False)
class HypotheticalStorm(CumulativeStorm):
    """``depth_mm`` is the point depth; ``storm_area_km2`` and ``arf`` reduce it. No table means factor 1."""

    depth_mm: float
    pattern: PercentPattern
    duration_hours: float
    storm_area_km2: float | None = None
    arf: ArfTable | None = None

    @property
    def area_factor(self) -> float:
        """The factor at the storm area."""
        if self.arf is None or self.storm_area_km2 is None:
            return 1.0
        return self.arf.factor(self.storm_area_km2)

    @property
    def total_depth(self) -> float:
        """The area-reduced depth, mm."""
        return self.depth_mm * self.area_factor

    def cumulative_depth(self, minutes: ArrayLike) -> FloatArray:
        """Depth fallen by each time, mm."""
        fraction = np.asarray(minutes, dtype=np.float64) / (self.duration_hours * MINUTES_PER_HOUR)
        return self.total_depth * self.pattern.fraction(fraction)

    def at_area(self, area_km2: float) -> Self:
        """The same storm with its storm area set to ``area_km2``."""
        return replace(self, storm_area_km2=area_km2)
