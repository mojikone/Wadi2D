"""Channel routing. Interface: :class:`RoutingMethod`, :data:`ROUTING_METHODS`.

The Muskingum-Cunge method here replicates HEC-HMS 4.12, not the textbook scheme: it reproduces the eight Block 2
reaches, and every choice HMS leaves undocumented is one named constant below, measured against its output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.routing_kernel import route_cells
from wadi2d.storm.base import FloatArray
from wadi2d.storm.registry import Registry

MUSKINGUM_CUNGE = "Muskingum Cunge"
LAG = "Lag"
NO_ROUTING = "None"

# What HMS does not document, measured on Block 2 (DSS series and DA_*_daa.log files) and frozen here.
#
# Cells: N = ceil(L / (c_index dt)), dx = L / N. Every "Delta x" the log prints equals this, and R6 settles that
# it is a ceiling: L / (c dt) = 9.32, logged dx = L / 10.
CELL_ROUNDING_GUARD = 1.0e-9
# Stencil: the reference flow starts from the 3-point mean of old inflow, new inflow and old outflow, then iterates
# on the 4-point mean with the new outflow, up to `Maximum Route Step Iterations`.
# Tolerance: the iteration stops when the outflow moves by less than this fraction of itself. Against the eight
# reaches at 2, 5 and 100 yr, 1e-3 gives a series rmse of 0.0003 m3/s; 3e-4 and 3e-3 are ten times worse, and any
# absolute tolerance is at least seven times worse.
HMS_RELATIVE_TOLERANCE = 1.0e-3
HMS_DEPTH_TOLERANCE = 1.0e-9
# Low flow: below this 3-point mean the coefficients are skipped and the outflow is that mean. Reproduces R5 at the
# wave front to all eight printed decimals; 0.005 or 0.02 is five to nine times worse on the 2 yr reaches.
HMS_LOW_FLOW = 0.01
# New-inflow weight: below C + D = 1 it would go negative, so it is zeroed and split evenly between the other two
# (route_cells). The form was read off the lag of the HMS falling limb; without it the 5 yr peaks miss by 7.5 %.


class RoutingMethod(Protocol):
    """A routing model of one reach."""

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        """The outflow at the times of the inflow, m3/s."""
        ...


ROUTING_METHODS: Registry[RoutingMethod] = Registry("routing")


@ROUTING_METHODS.register(NO_ROUTING)
@dataclass(frozen=True)
class NoRouting:
    """Outflow equals inflow."""

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        """The outflow at the times of the inflow, m3/s."""
        return inflow_m3s


@ROUTING_METHODS.register(LAG)
@dataclass(frozen=True)
class LagRouting:
    """The inflow shifted by ``lag_minutes``, interpolated linearly between steps."""

    lag_minutes: float

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        """The outflow at the times of the inflow, m3/s."""
        times = dt_minutes * np.arange(len(inflow_m3s), dtype=np.float64)
        return np.interp(times - self.lag_minutes, times, inflow_m3s)


@ROUTING_METHODS.register(MUSKINGUM_CUNGE)
@dataclass(frozen=True)
class MuskingumCunge:
    """Muskingum-Cunge on a trapezoid, with `Automatic DX and DT` from an index celerity."""

    length_m: float
    slope: float
    roughness: float
    bottom_width_m: float
    side_slope: float
    index_celerity: float
    route_iterations: int = 30
    depth_iterations: int = 20

    def grid(self, dt_seconds: float) -> tuple[int, float, int]:
        """Cells, cell length and sub-steps per control step.

        When a wave crosses the reach inside one control step, the step is divided and there is one cell. No
        Block 2 reach does this, so the rule is the documented one (research note H02), not a measured one.
        """
        reach_time = self.length_m / self.index_celerity
        if dt_seconds > reach_time:
            return 1, self.length_m, math.ceil(dt_seconds / reach_time - CELL_ROUNDING_GUARD)
        cells = math.ceil(self.length_m / (self.index_celerity * dt_seconds) - CELL_ROUNDING_GUARD)
        return cells, self.length_m / cells, 1

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        """The outflow at the times of the inflow, m3/s."""
        dt_seconds = dt_minutes * SECONDS_PER_MINUTE
        cells, dx, substeps = self.grid(dt_seconds)
        times = np.arange(len(inflow_m3s), dtype=np.float64)
        fine = np.arange((len(inflow_m3s) - 1) * substeps + 1, dtype=np.float64) / substeps
        outflow = route_cells(
            np.interp(fine, times, inflow_m3s),
            cells,
            dt_seconds / substeps,
            dx,
            self.bottom_width_m,
            self.side_slope,
            self.slope,
            self.roughness,
            self.route_iterations,
            self.depth_iterations,
            HMS_DEPTH_TOLERANCE,
            HMS_RELATIVE_TOLERANCE,
            HMS_LOW_FLOW,
        )
        return outflow[::substeps]
