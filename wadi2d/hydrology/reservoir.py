"""Reservoirs: level-pool routing as HEC-HMS 4.12 does it. Interface: :func:`conic_storage`, :class:`Spillway`,
:class:`ReservoirOutflowCurve`, :class:`ReservoirOutflowStructures`, registered in the routing registry.

What the HMS technical reference states: the conic formula, the storage-indication step, the primary curve setting
the rows of the combined table, Q = C L H^1.5. What it does not state, measured on the HMS output:

- **Between table rows** S, A and Q are all linear in elevation: Block 4's ELEVATION, STORAGE and AREA series agree
  with this table to 1e-11. Routing on it reproduces Hawasinah 02 at 100 yr to 8e-12 m3/s.
- **Structures** (`Controlled Outflow`): every spillway discharges C L H^1.5 on the same pool head, the main and the
  auxiliary outlet alike; the Majlas and Al Ais 10 flows equal it exactly. One implicit trapezoid per control step
  matches HMS to 1e-11 m wherever the pool moves less than 0.1 m in the step.
- **`Adaptive Control: On`**: a step that moves the pool by more than 0.1 m is cut in two, with the inflow held at
  the mean of the control step in both parts. Up to 0.2 m this matches HMS to 2e-11 m. Above that the deeper splits
  are approximate: HMS's own criterion was not identified, and on the Majlas PMP one partition found, 1/8 1/8 1/4 1/2,
  is not a plain 0.1 m test. Bisecting every part by the same test is the closest form found. It brings the worst
  reservoir peak from 0.33 % to 0.03 % against one trapezoid per step, measured on HMS's inflows.

A pool above the top of its table raises: what HMS does there is not known, so nothing here guesses.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy as np

from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.reservoir_kernel import route_spillways, route_storage_indication
from wadi2d.hydrology.routing import ROUTING_METHODS
from wadi2d.storm.base import FloatArray

RESERVOIR_OUTFLOW_CURVE = "Reservoir Outflow Curve"
RESERVOIR_OUTFLOW_STRUCTURES = "Reservoir Outflow Structures"
CONIC_DIVISOR = 3.0
MAIN_OUTLET = 0
AUXILIARY_OUTLET = 1
LEVEL_ITERATIONS = 80
LEVEL_TOLERANCE_M = 1.0e-12
ADAPTIVE_LEVEL_CHANGE_M = 0.1
ADAPTIVE_BISECTIONS = 8


def conic_storage(elevations_m: FloatArray, areas_m2: FloatArray) -> FloatArray:
    """Storage at each row, m3, zero at the first: dS = dz / 3 (A1 + A2 + sqrt(A1 A2))."""
    slices = np.diff(elevations_m) / CONIC_DIVISOR
    lower, upper = areas_m2[:-1], areas_m2[1:]
    return np.concatenate(([0.0], np.cumsum(slices * (lower + upper + np.sqrt(lower * upper)))))


def _check_table(
    name: str, elevations_m: FloatArray, areas_m2: FloatArray, initial_elevation_m: float
) -> None:
    if len(elevations_m) != len(areas_m2) or len(elevations_m) < 2:
        raise ValueError(f"{name}: an elevation-area table needs two rows or more, one area per elevation")
    if np.any(np.diff(elevations_m) <= 0.0) or np.any(areas_m2 < 0.0):
        raise ValueError(f"{name}: elevations must rise and areas may not be negative")
    if not elevations_m[0] <= initial_elevation_m <= elevations_m[-1]:
        raise ValueError(f"{name}: initial elevation {initial_elevation_m} m is outside the table")


@ROUTING_METHODS.register(RESERVOIR_OUTFLOW_CURVE)
@dataclass(frozen=True, eq=False)
class ReservoirOutflowCurve:
    """`Modified Puls` on an elevation-area-outflow curve; the elevation-area curve is primary, so its rows rule."""

    elevations_m: FloatArray
    areas_m2: FloatArray
    outflow_elevations_m: FloatArray
    outflows_m3s: FloatArray
    initial_elevation_m: float

    def __post_init__(self) -> None:
        _check_table(RESERVOIR_OUTFLOW_CURVE, self.elevations_m, self.areas_m2, self.initial_elevation_m)

    @cached_property
    def storage_m3(self) -> FloatArray:
        """The storage column of the combined table."""
        return conic_storage(self.elevations_m, self.areas_m2)

    @cached_property
    def outflow_m3s(self) -> FloatArray:
        """The outflow column of the combined table: the outflow curve read at the primary rows."""
        return np.interp(self.elevations_m, self.outflow_elevations_m, self.outflows_m3s)

    def branches(self, inflow_m3s: FloatArray, dt_minutes: float) -> tuple[FloatArray, FloatArray]:
        """The main outflow at the times of the inflow; this method has no auxiliary outlet."""
        initial = float(np.interp(self.initial_elevation_m, self.elevations_m, self.storage_m3))
        main, overtopped = route_storage_indication(
            inflow_m3s, dt_minutes * SECONDS_PER_MINUTE, self.storage_m3, self.outflow_m3s, initial
        )
        if overtopped:
            raise ValueError(f"{RESERVOIR_OUTFLOW_CURVE}: the pool passed the top of its table")
        return main, np.zeros_like(main)

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        """The main outflow at the times of the inflow, m3/s."""
        return self.branches(inflow_m3s, dt_minutes)[0]


@dataclass(frozen=True)
class Spillway:
    """A broad-crested spillway, Q = C L H^1.5, to the main or the auxiliary outlet."""

    crest_elevation_m: float
    crest_length_m: float
    coefficient: float
    outlet: int = MAIN_OUTLET


@ROUTING_METHODS.register(RESERVOIR_OUTFLOW_STRUCTURES)
@dataclass(frozen=True, eq=False)
class ReservoirOutflowStructures:
    """`Controlled Outflow` on an elevation-area curve, with no tailwater and no evaporation."""

    elevations_m: FloatArray
    areas_m2: FloatArray
    spillways: tuple[Spillway, ...]
    initial_elevation_m: float
    max_bisections: int = ADAPTIVE_BISECTIONS

    def __post_init__(self) -> None:
        _check_table(RESERVOIR_OUTFLOW_STRUCTURES, self.elevations_m, self.areas_m2, self.initial_elevation_m)
        if not self.spillways:
            raise ValueError(f"{RESERVOIR_OUTFLOW_STRUCTURES}: no outlet")

    @cached_property
    def storage_m3(self) -> FloatArray:
        """The storage at each row of the table."""
        return conic_storage(self.elevations_m, self.areas_m2)

    def branches(self, inflow_m3s: FloatArray, dt_minutes: float) -> tuple[FloatArray, FloatArray]:
        """The main and the auxiliary outflow at the times of the inflow, m3/s."""
        main, auxiliary, overtopped = route_spillways(
            inflow_m3s,
            dt_minutes * SECONDS_PER_MINUTE,
            self.elevations_m,
            self.storage_m3,
            np.array([spillway.crest_elevation_m for spillway in self.spillways]),
            np.array([spillway.crest_length_m for spillway in self.spillways]),
            np.array([spillway.coefficient for spillway in self.spillways]),
            np.array([spillway.outlet for spillway in self.spillways], dtype=np.int64),
            self.initial_elevation_m,
            LEVEL_ITERATIONS,
            LEVEL_TOLERANCE_M,
            ADAPTIVE_LEVEL_CHANGE_M,
            self.max_bisections,
        )
        if overtopped:
            raise ValueError(f"{RESERVOIR_OUTFLOW_STRUCTURES}: the pool passed the top of its table")
        return main, auxiliary

    def route(self, inflow_m3s: FloatArray, dt_minutes: float) -> FloatArray:
        """The main outflow at the times of the inflow, m3/s."""
        return self.branches(inflow_m3s, dt_minutes)[0]
