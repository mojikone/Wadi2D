"""Channel routing. Interface: :class:`RoutingMethod`, :data:`ROUTING_METHODS`.

The Muskingum-Cunge method here replicates HEC-HMS 4.12 by default, not the textbook scheme: it reproduces the eight
Block 2 reaches, and every choice HMS leaves undocumented is one named constant below, measured against its output.
Its ``scheme`` can instead be the conserving variant of :mod:`wadi2d.hydrology.routing_conserving`, on the same
cells, sub-steps and section; the job's ``hydrology.reach_routing`` chooses, and the HMS path is untouched by it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from wadi2d.config.schema import REACH_CONSERVING, REACH_HMS
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.routing_conserving import route_cells_conserving
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
# Sub-steps: the control step is then rounded to the nearest divisor of the travel time of a cell, k = round(N c dt
# / L) and at least 1. No Block 2 reach is short enough to show it; the "Delta t" and "Delta x" HMS logged for 8,390
# reach runs on Blocks 2, 4, 6 and Majlas (258 distinct reaches, L / (c dt) from 0.02 to 39) agree with N and k on
# all but one reach, Block 6's R20 (0.94: logged N = 2, k = 2, against 1 and 1), which no input tells apart from its
# neighbours; it stays an unexplained exception, up to 0.09 % on the peaks below it.
CELL_ROUNDING_GUARD = 1.0e-9
ROUND_HALF_UP = 0.5
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

# The conserving variant (Todini 2007, routing_conserving) on the same grid; what the paper leaves open on an
# ephemeral wadi, measured on Block 2 (W29).
CONSERVING_FLOW_FLOOR = HMS_LOW_FLOW
"""The hydraulics are read at no less than this flow, m3/s: at zero flow the celerity and beta are 0 / 0. The same
figure as the HMS low-flow mean, so the two paths agree on what a trickle is; the identity holds whatever it is."""
CONSERVING_MIN_VELOCITY = 0.1
"""The parcel speed that sets a cell's travel time is never taken below this, m/s. Below about 0.2 m3/s in a 60 m
bed the section's speed is lower, a cell would hold its water for hours and R1 would take days to drain; the design
flood is at 1 to 3 m/s and does not see it."""


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


def _refined(inflow_m3s: FloatArray, substeps: int) -> FloatArray:
    """The inflow interpolated linearly onto the sub-steps."""
    times = np.arange(len(inflow_m3s), dtype=np.float64)
    fine = np.arange((len(inflow_m3s) - 1) * substeps + 1, dtype=np.float64) / substeps
    return np.interp(fine, times, inflow_m3s)


@ROUTING_METHODS.register(MUSKINGUM_CUNGE)
@dataclass(frozen=True)
class MuskingumCunge:
    """Muskingum-Cunge on a trapezoid, with `Automatic DX and DT` from an index celerity.

    ``scheme`` is the job's ``hydrology.reach_routing``: HMS-faithful by default, or the conserving variant.
    """

    length_m: float
    slope: float
    roughness: float
    bottom_width_m: float
    side_slope: float
    index_celerity: float
    route_iterations: int = 30
    depth_iterations: int = 20
    scheme: str = REACH_HMS

    def __post_init__(self) -> None:
        if self.scheme not in (REACH_HMS, REACH_CONSERVING):
            raise ValueError(f"reach routing scheme {self.scheme!r}: one of {REACH_HMS!r}, {REACH_CONSERVING!r}")

    def grid(self, dt_seconds: float) -> tuple[int, float, int]:
        """Cells, cell length and sub-steps per control step, as measured from the HMS logs (see above)."""
        cells = math.ceil(self.length_m / (self.index_celerity * dt_seconds) - CELL_ROUNDING_GUARD)
        cell_time = self.length_m / (cells * self.index_celerity)
        return cells, self.length_m / cells, max(1, math.floor(dt_seconds / cell_time + ROUND_HALF_UP))

    def route_conserving(self, inflow_m3s: FloatArray, dt_minutes: float) -> tuple[FloatArray, float]:
        """The conserving variant's outflow at the times of the inflow, m3/s, and what the reach holds at the end of
        the series, m3: the inflow volume equals the outflow volume plus that, to round-off."""
        dt_seconds = dt_minutes * SECONDS_PER_MINUTE
        cells, dx, substeps = self.grid(dt_seconds)
        outflow, storage = route_cells_conserving(
            _refined(inflow_m3s, substeps),
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
            CONSERVING_FLOW_FLOOR,
            CONSERVING_MIN_VELOCITY,
        )
        return outflow[::substeps], storage

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        """The outflow at the times of the inflow, m3/s."""
        if self.scheme == REACH_CONSERVING:
            return self.route_conserving(inflow_m3s, dt_minutes)[0]
        dt_seconds = dt_minutes * SECONDS_PER_MINUTE
        cells, dx, substeps = self.grid(dt_seconds)
        outflow = route_cells(
            _refined(inflow_m3s, substeps),
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
