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
from datetime import datetime
from functools import cached_property

import numpy as np

from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.reservoir_kernel import route_spillways, route_storage_indication
from wadi2d.hydrology.routing import ROUTING_METHODS
from wadi2d.hydrology.structure_kernel import BROAD_CRESTED, route_structures
from wadi2d.hydrology.structures import (
    MonthlyEvaporation,
    Packed,
    Pump,
    RatingSpillway,
    Structure,
    TabularSeepage,
    flows_at,
    pack_all,
)
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
HALF_STEP = 0.5


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

    def pool(
        self, inflow_m3s: FloatArray, outflow_m3s: FloatArray, dt_minutes: float
    ) -> tuple[FloatArray, FloatArray]:
        """Storage, m3, and pool level, m, at the times of a routed inflow and its outflow.

        The storage-indication step holds S2 - S1 = dt ((I1 + I2) / 2 - (O1 + O2) / 2) exactly, so the storage is that
        sum from the initial pool, and the level is the table read back. HMS's STORAGE and ELEVATION series of Block 2's
        Basin 3 agree with this to 3e-7 of the storage and 1 mm (W55).
        """
        start = float(np.interp(self.initial_elevation_m, self.elevations_m, self.storage_m3))
        step = HALF_STEP * dt_minutes * SECONDS_PER_MINUTE
        change = step * (inflow_m3s[1:] + inflow_m3s[:-1] - outflow_m3s[1:] - outflow_m3s[:-1])
        storage = start + np.concatenate(([0.0], np.cumsum(change)))
        return storage, np.interp(storage, self.storage_m3, self.elevations_m)


@dataclass(frozen=True)
class Spillway:
    """A broad-crested spillway, Q = C L H^1.5, to the main or the auxiliary outlet."""

    crest_elevation_m: float
    crest_length_m: float
    coefficient: float
    outlet: int = MAIN_OUTLET

    def pack(self) -> Packed:
        """The kernel's form (:mod:`wadi2d.hydrology.structures`)."""
        return Packed(BROAD_CRESTED, self.outlet, (self.crest_elevation_m, self.crest_length_m, self.coefficient))

    def label(self) -> str:
        return "spillway"


@dataclass(frozen=True, eq=False)
class StructureRun:
    """A routed reservoir with structures, at the times of its inflow: outlets, evaporation, pool, each structure."""

    main_m3s: FloatArray
    auxiliary_m3s: FloatArray
    evaporation_m3s: FloatArray
    pool_m: FloatArray
    storage_m3: FloatArray
    structures_m3s: dict[str, FloatArray]


@ROUTING_METHODS.register(RESERVOIR_OUTFLOW_STRUCTURES)
@dataclass(frozen=True, eq=False)
class ReservoirOutflowStructures:
    """`Controlled Outflow` on an elevation-area (or elevation-storage) curve.

    ``spillways`` are broad-crested; ``structures`` are the other kinds of :mod:`wadi2d.hydrology.structures`.
    ``tailwater_m`` is a fixed main tailwater stage (HMS's Fixed Stage), None for none; the auxiliary outlet has
    none. ``evaporation`` needs the areas and ``start``, the date of the first inflow value. ``storages_m3``, when
    given, is the elevation-storage table and ``areas_m2`` may then be None. A reservoir with broad-crested
    spillways alone and none of the rest routes on :func:`route_spillways`, unchanged since W55.
    """

    elevations_m: FloatArray
    areas_m2: FloatArray | None
    spillways: tuple[Spillway, ...]
    initial_elevation_m: float
    max_bisections: int = ADAPTIVE_BISECTIONS
    structures: tuple[Structure, ...] = ()
    tailwater_m: float | None = None
    evaporation: MonthlyEvaporation | None = None
    start: datetime | None = None
    storages_m3: FloatArray | None = None

    def __post_init__(self) -> None:
        name = RESERVOIR_OUTFLOW_STRUCTURES
        if (self.areas_m2 is None) == (self.storages_m3 is None):
            raise ValueError(f"{name}: give an elevation-area or an elevation-storage table, one of the two")
        column = self.areas_m2 if self.areas_m2 is not None else self.storages_m3
        _check_table(name, self.elevations_m, column, self.initial_elevation_m)
        if not self.spillways and not self.structures:
            raise ValueError(f"{name}: no outlet")
        if self.evaporation is not None and self.areas_m2 is None:
            raise ValueError(f"{name}: monthly evaporation needs an elevation-area table, as in HMS")
        top = float(self.elevations_m[-1])
        for structure in self.structures:
            if isinstance(structure, RatingSpillway) and structure.elevations_m[-1] < top:
                raise ValueError(f"{name}: a rating table ends at {structure.elevations_m[-1]} m, below the pool "
                                 f"table's top {top} m; what HMS does above it is not known")
            if isinstance(structure, TabularSeepage):
                low = self.elevations_m[0] if self.tailwater_m is None else self.tailwater_m
                if structure.heads_m[-1] < top - low:
                    raise ValueError(f"{name}: the seepage table ends at a head of {structure.heads_m[-1]} m, "
                                     f"below the {top - low} m the pool can reach")
            if isinstance(structure, Pump) and self.tailwater_m is not None and self.tailwater_m >= structure.intake_m:
                raise ValueError(f"{name}: tailwater {self.tailwater_m} m reaches a pump's intake at "
                                 f"{structure.intake_m} m; what HMS does then was not identified (W62)")
        if self.tailwater_m is not None:
            for structure in (*self.spillways, *self.structures):
                crest = getattr(structure, "crest_elevation_m", None)
                if structure.outlet == MAIN_OUTLET and crest is not None and self.tailwater_m >= crest:
                    raise ValueError(f"{name}: tailwater {self.tailwater_m} m reaches a weir crest at {crest} m; "
                                     "HMS's drowned-weir rule was not identified (W59)")

    @cached_property
    def storage_m3(self) -> FloatArray:
        """The storage at each row of the table."""
        if self.storages_m3 is not None:
            return self.storages_m3
        return conic_storage(self.elevations_m, self.areas_m2)

    @property
    def _plain(self) -> bool:
        """Broad-crested spillways alone, no tailwater, evaporation or storage table: the W55 path."""
        return not self.structures and self.tailwater_m is None and self.evaporation is None and self.storages_m3 is None

    def run(self, inflow_m3s: FloatArray, dt_minutes: float) -> StructureRun:
        """Route the inflow: both outlets, the evaporation, the pool level and storage, and each structure's flow."""
        structures: tuple[Structure, ...] = (*self.spillways, *self.structures)
        arrays = pack_all(structures)
        steps = max(len(inflow_m3s) - 1, 1)
        if self.evaporation is None:
            rates = np.zeros(steps)
        elif self.start is None:
            raise ValueError(
                f"{RESERVOIR_OUTFLOW_STRUCTURES}: monthly evaporation needs the run's start date "
                "(in a job, storm.rain_start)"
            )
        else:
            rates = self.evaporation.rates(self.start, steps, dt_minutes)
        areas = self.areas_m2 if self.areas_m2 is not None else np.zeros_like(self.elevations_m)
        tailwater = np.array([np.nan if self.tailwater_m is None else self.tailwater_m, np.nan])
        main, auxiliary, lost, level, storage, active, overtopped = route_structures(
            np.asarray(inflow_m3s, dtype=np.float64),
            dt_minutes * SECONDS_PER_MINUTE,
            self.elevations_m,
            self.storage_m3,
            areas,
            rates,
            arrays.kinds,
            arrays.outlets,
            arrays.parameters,
            arrays.table_x,
            arrays.table_y,
            arrays.table_start,
            arrays.table_end,
            tailwater,
            self.initial_elevation_m,
            LEVEL_ITERATIONS,
            LEVEL_TOLERANCE_M,
            ADAPTIVE_LEVEL_CHANGE_M,
            self.max_bisections,
        )
        if overtopped:
            raise ValueError(f"{RESERVOIR_OUTFLOW_STRUCTURES}: the pool passed the top of its table")
        flows = flows_at(structures, level, (tailwater[0], tailwater[1]), float(self.elevations_m[0]), active)
        for index, structure in enumerate(structures):
            if isinstance(structure, Pump):
                heads = structure.head_m(level[active[:, index] > 0.0])
                if heads.size and (heads.min() < structure.heads_m[0] or heads.max() > structure.heads_m[-1]):
                    raise ValueError(
                        f"{RESERVOIR_OUTFLOW_STRUCTURES}: a pump ran at a head of {heads.min():.3f} to "
                        f"{heads.max():.3f} m, outside its table ({structure.heads_m[0]} to {structure.heads_m[-1]} "
                        "m); what HMS does there is not known"
                    )
        labels: dict[str, int] = {}
        named: dict[str, FloatArray] = {}
        for index, structure in enumerate(structures):
            base = structure.label()
            labels[base] = labels.get(base, 0) + 1
            named[f"{base}_{labels[base]}_m3s"] = flows[:, index]
        return StructureRun(main, auxiliary, lost, level, storage, named)

    def pool(
        self, inflow_m3s: FloatArray, outflow_m3s: FloatArray, dt_minutes: float
    ) -> tuple[FloatArray, FloatArray]:
        """Storage, m3, and pool level, m, at the times of the inflow; the outflow is not needed, the run is redone."""
        result = self.run(inflow_m3s, dt_minutes)
        return result.storage_m3, result.pool_m

    def branches(self, inflow_m3s: FloatArray, dt_minutes: float) -> tuple[FloatArray, FloatArray]:
        """The main and the auxiliary outflow at the times of the inflow, m3/s."""
        if not self._plain:
            result = self.run(inflow_m3s, dt_minutes)
            return result.main_m3s, result.auxiliary_m3s
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
