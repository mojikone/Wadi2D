"""A storm given as a table of periods. Interface: :class:`HyetographStorm`.

Depth falls at a constant rate inside each period, so the table's sum is the storm. A hyetograph is rain as it fell, or
as it was designed, at one area: nothing reduces it, and a design that needs an area reduction is a Hypothetical Storm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

import numpy as np
from numpy.typing import ArrayLike

from wadi2d.storm.base import STORM_METHODS, CumulativeStorm, FloatArray

HYETOGRAPH_STORM = "Hyetograph"


@STORM_METHODS.register(HYETOGRAPH_STORM)
@dataclass(frozen=True, eq=False)
class HyetographStorm(CumulativeStorm):
    """``minutes`` are the edges of the periods, ``cumulative_mm`` the depth fallen by each edge."""

    minutes: FloatArray
    cumulative_mm: FloatArray

    def __post_init__(self) -> None:
        if self.minutes.size != self.cumulative_mm.size:
            raise ValueError("a hyetograph needs one depth per time")
        if np.any(np.diff(self.minutes) <= 0.0) or np.any(np.diff(self.cumulative_mm) < 0.0):
            raise ValueError("a hyetograph's times must rise and its depths must not fall")

    @classmethod
    def from_periods(cls, ends_minutes: ArrayLike, depths_mm: ArrayLike) -> Self:
        """From the end of each period and the depth in it; the first period opens at minute zero."""
        ends = np.asarray(ends_minutes, dtype=np.float64)
        depths = np.asarray(depths_mm, dtype=np.float64)
        return cls(np.concatenate(([0.0], ends)), np.concatenate(([0.0], np.cumsum(depths))))

    @property
    def total_depth(self) -> float:
        """The depth of the whole table, mm."""
        return float(self.cumulative_mm[-1])

    def cumulative_depth(self, minutes: ArrayLike) -> FloatArray:
        """Depth fallen by each time, mm."""
        return np.interp(np.asarray(minutes, dtype=np.float64), self.minutes, self.cumulative_mm)

    def at_area(self, area_km2: float) -> Self:
        """A hyetograph has no area reduction: the same storm."""
        return self
