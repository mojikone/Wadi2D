"""The depth-area analysis: each point reads its own area-reduced run.

Interface: :func:`analyse_point`, :func:`analyse`, :class:`PointResult`, :data:`StormAtPoint`. For one analysis
point the storm area becomes that point's drainage area and only the sub-network upstream of it is recomputed,
as HMS does (research note H03, algorithm C). A point's flows are valid at that point and upstream of it, never
elsewhere.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.model import TimeGrid
from wadi2d.hydrology.network import LumpedEngine, Run
from wadi2d.storm.base import FloatArray, SubbasinRain

StormAtPoint = Callable[[str, float], SubbasinRain]
"""The rain of an analysis point, from its name and drainage area in km2."""


@dataclass(frozen=True)
class PointResult:
    """One analysis point: its storm area and flow, with the whole run for the elements above it."""

    point: str
    storm_area_km2: float
    outflow: FloatArray
    run: Run

    @property
    def peak(self) -> float:
        """Peak flow at the point, m3/s."""
        return float(self.outflow.max())

    @property
    def peak_minutes(self) -> float:
        """Time of the peak, minutes from the start of the run."""
        return float(np.argmax(self.outflow)) * self.run.grid.dt_minutes

    @property
    def volume_m3(self) -> float:
        """Outflow volume by the trapezoidal rule, m3."""
        return float(np.trapezoid(self.outflow)) * self.run.grid.dt_minutes * SECONDS_PER_MINUTE


def analyse_point(engine: LumpedEngine, storm: StormAtPoint, grid: TimeGrid, point: str) -> PointResult:
    """Run the sub-network above ``point`` under the storm of its own drainage area."""
    area = engine.basin.drainage_area(point)
    run = engine.run(storm(point, area), grid, only=engine.basin.upstream_of(point))
    return PointResult(point, area, run.outflow[point], run)


def analyse(
    engine: LumpedEngine, storm: StormAtPoint, grid: TimeGrid, points: Iterable[str]
) -> dict[str, PointResult]:
    """Every analysis point in turn."""
    return {point: analyse_point(engine, storm, grid, point) for point in points}


def point_storm(storm: SubbasinRain) -> StormAtPoint:
    """The usual case: one storm, its area set to each point's drainage area."""

    def at_point(_point: str, area_km2: float) -> SubbasinRain:
        return storm.at_area(area_km2)

    return at_point
