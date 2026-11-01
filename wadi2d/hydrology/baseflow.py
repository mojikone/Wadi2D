"""Baseflow. Interface: :class:`BaseflowMethod`, :data:`BASEFLOW_METHODS`.

A baseflow method takes the direct runoff of a subbasin and returns its total outflow. Recession keeps the HMS
semantics of research note H01, algorithm G: the recession anchors to the total flow at the threshold and is
not mass-conservative by design.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from wadi2d.hydrology.constants import SECONDS_PER_DAY, SECONDS_PER_MINUTE
from wadi2d.storm.base import FloatArray
from wadi2d.storm.registry import Registry

NO_BASEFLOW = "None"
RECESSION = "Recession"


class BaseflowMethod(Protocol):
    """A baseflow model of one subbasin."""

    def total_flow(self, direct_m3s: FloatArray, dt_minutes: float, area_km2: float) -> FloatArray:
        """The outflow of each time, direct runoff included, m3/s."""
        ...


BASEFLOW_METHODS: Registry[BaseflowMethod] = Registry("baseflow")


@BASEFLOW_METHODS.register(NO_BASEFLOW)
@dataclass(frozen=True)
class NoBaseflow:
    """Outflow is the direct runoff."""

    def total_flow(self, direct_m3s: FloatArray, dt_minutes: float, area_km2: float) -> FloatArray:
        """The outflow of each time, m3/s."""
        return direct_m3s


@BASEFLOW_METHODS.register(RECESSION)
@dataclass(frozen=True)
class RecessionBaseflow:
    """Recession with a ratio-to-peak threshold; ``initial_m3s_km2`` is a flow per unit area."""

    recession_constant: float
    initial_m3s_km2: float
    threshold_ratio: float

    def total_flow(self, direct_m3s: FloatArray, dt_minutes: float, area_km2: float) -> FloatArray:
        """The outflow of each time, m3/s."""
        factor = self.recession_constant ** (dt_minutes * SECONDS_PER_MINUTE / SECONDS_PER_DAY)
        initial = self.initial_m3s_km2 * area_km2 * factor ** np.arange(len(direct_m3s), dtype=np.float64)
        total = direct_m3s + initial
        peak = 0.0
        recession: float | None = None
        for step in range(len(total)):
            if recession is not None:
                recession *= factor
                if total[step] <= recession:
                    total[step] = recession
                    continue
                recession = None  # a second rise: a new event on top of the initial recession
            peak = max(peak, float(total[step]))
            falling = step > 0 and total[step] < total[step - 1]
            if falling and total[step] <= self.threshold_ratio * peak:
                recession = float(total[step])
                peak = 0.0
        return total
