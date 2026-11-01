"""A constant-intensity storm. Interface: :class:`UniformStorm`."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Self

import numpy as np
from numpy.typing import ArrayLike

from wadi2d.storm.arf import ArfTable
from wadi2d.storm.base import STORM_METHODS, CumulativeStorm, FloatArray

UNIFORM_STORM = "Uniform"


@STORM_METHODS.register(UNIFORM_STORM)
@dataclass(frozen=True, eq=False)
class UniformStorm(CumulativeStorm):
    """``depth_mm`` falls at a constant rate over ``duration_minutes``, reduced like any other storm."""

    depth_mm: float
    duration_minutes: float
    storm_area_km2: float | None = None
    arf: ArfTable | None = None

    @property
    def total_depth(self) -> float:
        """The area-reduced depth, mm."""
        if self.arf is None or self.storm_area_km2 is None:
            return self.depth_mm
        return self.depth_mm * self.arf.factor(self.storm_area_km2)

    def cumulative_depth(self, minutes: ArrayLike) -> FloatArray:
        """Depth fallen by each time, mm."""
        fraction = np.clip(np.asarray(minutes, dtype=np.float64) / self.duration_minutes, 0.0, 1.0)
        return self.total_depth * fraction

    def at_area(self, area_km2: float) -> Self:
        """The same storm with its storm area set to ``area_km2``."""
        return replace(self, storm_area_km2=area_km2)
