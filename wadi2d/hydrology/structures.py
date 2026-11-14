"""Reservoir outflow structures of HEC-HMS 4.12, behind one interface: each packs itself for the compiled kernel.

Interface: :class:`Structure` (the protocol), :class:`RatingSpillway`, :class:`Orifice`, :class:`LevelDamTop`,
:class:`TabularSeepage`, :class:`SpillwayGate`, :class:`Pump`, :class:`Culvert`, :class:`MonthlyEvaporation`,
:class:`Packed`,
:func:`pack_all`, :data:`STRUCTURE_KINDS`.
The broad-crested :class:`~wadi2d.hydrology.reservoir.Spillway` packs the same way. The laws live in
:mod:`wadi2d.hydrology.structure_kernel`, once; a new structure is a class here and a kind there.

What HMS does that is not in its manual, measured on W59's runs: an orifice's head is taken from the higher of its
centreline and the tailwater; a seepage with no tailwater reads its table at the pool over the bottom of the storage
table, and its tailwater-to-pool table changed nothing in any run, a tailwater above the pool giving negative seepage
from the pool-to-tailwater table instead; monthly evaporation spreads each month's depth over 28 days in February of a
leap year too, by the month a control step starts in. W62's: a gate passes weir flow over its width at the spillway's
coefficient up to a head of one opening, its own law from 1.25 openings, linear between, with sqrt(2 g) as 4.42869; a
pump's minimum run and rest times are minutes, and a pump switches on and off at the start of a step.
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cached_property
from typing import Protocol

import numpy as np

from wadi2d.hydrology import culvert as culverts
from wadi2d.hydrology import structure_kernel as kernel
from wadi2d.storm.base import FloatArray
from wadi2d.storm.registry import Registry

MAIN_OUTLET = kernel.MAIN_OUTLET
AUXILIARY_OUTLET = kernel.AUXILIARY_OUTLET
MILLIMETRES_PER_METRE = 1000.0
SECONDS_PER_DAY = 86400.0
MONTHS = 12
FEBRUARY = 2
HMS_FEBRUARY_DAYS = 28
NO_PARAMETER = 0.0
PARAMETER_SLOTS = 8
"""Numbers a packed structure carries; a kind uses the first few and the rest are zero."""
SECONDS_PER_MINUTE = 60.0


@dataclass(frozen=True, eq=False)
class Packed:
    """One structure as the kernel reads it: kind and outlet codes, three numbers, and its table (may be empty)."""

    kind: int
    outlet: int
    parameters: tuple[float, ...]
    table_x: FloatArray = field(default_factory=lambda: np.zeros(0))
    table_y: FloatArray = field(default_factory=lambda: np.zeros(0))


class Structure(Protocol):
    """A reservoir outflow structure: its outlet and its packed form."""

    outlet: int

    def pack(self) -> Packed: ...

    def label(self) -> str: ...


STRUCTURE_KINDS: Registry[Structure] = Registry("reservoir structure")
RATING_SPILLWAY = "Rating Curve Spillway"
ORIFICE = "Orifice"
LEVEL_DAM_TOP = "Level Dam"
TABULAR_SEEPAGE = "Tabular Dam Seepage"
SLUICE_GATE = "Sluice"
RADIAL_GATE = "Radial"
HEAD_DISCHARGE_PUMP = "Head-Discharge Pump"
CULVERT = "Culvert"
SLUICE_HEAD_EXPONENT = 0.5


def _rising(name: str, x: FloatArray, y: FloatArray) -> None:
    if len(x) != len(y) or len(x) < 2 or np.any(np.diff(x) <= 0.0):
        raise ValueError(f"{name}: a table needs two rows or more and a rising first column")


@STRUCTURE_KINDS.register(RATING_SPILLWAY)
@dataclass(frozen=True, eq=False)
class RatingSpillway:
    """A spillway given as an elevation-discharge table; no tailwater acts on it (measured, W59)."""

    elevations_m: FloatArray
    flows_m3s: FloatArray
    outlet: int = MAIN_OUTLET

    def __post_init__(self) -> None:
        _rising(RATING_SPILLWAY, self.elevations_m, self.flows_m3s)

    def pack(self) -> Packed:
        return Packed(kernel.RATING_CURVE, self.outlet, (NO_PARAMETER,) * 3, self.elevations_m, self.flows_m3s)

    def label(self) -> str:
        return "rating_spillway"


@STRUCTURE_KINDS.register(ORIFICE)
@dataclass(frozen=True)
class Orifice:
    """An orifice outlet, Q = n K A sqrt(2 g H), H from the higher of the centreline and the tailwater."""

    centre_elevation_m: float
    area_m2: float
    coefficient: float
    barrels: int = 1
    outlet: int = MAIN_OUTLET

    def pack(self) -> Packed:
        conveyance = self.barrels * self.coefficient * self.area_m2
        return Packed(kernel.ORIFICE, self.outlet, (self.centre_elevation_m, conveyance, NO_PARAMETER))

    def label(self) -> str:
        return "orifice"


@STRUCTURE_KINDS.register(LEVEL_DAM_TOP)
@dataclass(frozen=True)
class LevelDamTop:
    """A level dam top, Q = C L H^1.5 over the crest, drowned by a tailwater over it through HMS's tabulated
    reduction on the submergence, the same as a broad-crested spillway's (W67, ``structure_kernel.SUBMERGENCE``)."""

    crest_elevation_m: float
    crest_length_m: float
    coefficient: float
    outlet: int = MAIN_OUTLET

    def pack(self) -> Packed:
        return Packed(
            kernel.LEVEL_DAM_TOP, self.outlet, (self.crest_elevation_m, self.crest_length_m, self.coefficient)
        )

    def label(self) -> str:
        return "dam_top"


@STRUCTURE_KINDS.register(TABULAR_SEEPAGE)
@dataclass(frozen=True, eq=False)
class TabularSeepage:
    """Seepage through the dam from a head-discharge table, head = pool - tailwater, to the main outlet."""

    heads_m: FloatArray
    flows_m3s: FloatArray
    outlet: int = MAIN_OUTLET

    def __post_init__(self) -> None:
        _rising(TABULAR_SEEPAGE, self.heads_m, self.flows_m3s)

    def pack(self) -> Packed:
        return Packed(kernel.TABULAR_SEEPAGE, self.outlet, (NO_PARAMETER,) * 3, self.heads_m, self.flows_m3s)

    def label(self) -> str:
        return "seepage"


@STRUCTURE_KINDS.register(SLUICE_GATE)
@STRUCTURE_KINDS.register(RADIAL_GATE)
@dataclass(frozen=True)
class SpillwayGate:
    """A group of identical gates on a broad-crested spillway (HMS's Spillway Gate with a Fixed Opening).

    Weir flow over the group's width at the spillway's coefficient while the head over the crest is at most the
    opening; from 1.25 openings the gate law, sluice C W B k sqrt(H) or radial C k W T^TE B^BE H^HE (W the group's
    width, k = 4.42869); linear in head over opening between. The drowned forms are not identified and a tailwater
    reaching the crest is refused (a plain spillway or dam top is drowned as HMS does it, W67).
    """

    kind: str
    crest_elevation_m: float
    weir_coefficient: float
    gates: int
    width_m: float
    coefficient: float
    opening_m: float
    trunnion_height_m: float = 0.0
    trunnion_exponent: float = 0.0
    opening_exponent: float = 1.0
    head_exponent: float = SLUICE_HEAD_EXPONENT
    outlet: int = MAIN_OUTLET

    def __post_init__(self) -> None:
        if self.kind not in (SLUICE_GATE, RADIAL_GATE):
            raise ValueError(f"spillway gate {self.kind!r}: only {SLUICE_GATE} and {RADIAL_GATE}")
        if self.gates < 1 or self.width_m <= 0.0 or self.opening_m < 0.0:
            raise ValueError(f"spillway gate: {self.gates} gates of {self.width_m} m open {self.opening_m} m")
        if self.kind == SLUICE_GATE and (self.head_exponent, self.opening_exponent, self.trunnion_exponent) != (
            SLUICE_HEAD_EXPONENT, 1.0, 0.0
        ):
            raise ValueError("a sluice gate has no exponents of its own: head 0.5, opening 1, trunnion 0")

    @property
    def total_width_m(self) -> float:
        return self.gates * self.width_m

    def pack(self) -> Packed:
        width = self.total_width_m
        factor = (
            self.coefficient * kernel.GATE_SQRT_2G * width
            * self.trunnion_height_m**self.trunnion_exponent * self.opening_m**self.opening_exponent
        )
        return Packed(
            kernel.GATE, self.outlet,
            (self.crest_elevation_m, self.weir_coefficient * width, factor, self.opening_m, self.head_exponent),
        )

    def label(self) -> str:
        return "gate"


@STRUCTURE_KINDS.register(HEAD_DISCHARGE_PUMP)
@dataclass(frozen=True, eq=False)
class Pump:
    """HMS's Head-Discharge Pump: ``units`` identical pumps that switch together.

    On when the pool reaches ``on_m`` and the pumps have rested ``rest_min``; off below ``off_m`` once they have run
    ``run_min``, and below the intake at once. While on, each pumps the table's flow at the total head, the discharge
    elevation less the pool plus the equipment loss (W62: HMS's flows to the last digit). The table is head against
    flow; a head outside it refuses the run, since what HMS does there is not known.
    """

    heads_m: FloatArray
    flows_m3s: FloatArray
    units: int
    intake_m: float
    discharge_elevation_m: float
    on_m: float
    off_m: float
    head_loss_m: float = 0.0
    run_min: float = 0.0
    rest_min: float = 0.0
    outlet: int = MAIN_OUTLET

    def __post_init__(self) -> None:
        _rising(HEAD_DISCHARGE_PUMP, self.heads_m, self.flows_m3s)
        if self.units < 1:
            raise ValueError(f"{HEAD_DISCHARGE_PUMP}: {self.units} pumps")
        if not self.intake_m <= self.off_m <= self.on_m:
            raise ValueError(f"{HEAD_DISCHARGE_PUMP}: intake {self.intake_m} m, switch-off {self.off_m} m and "
                             f"switch-on {self.on_m} m must rise in that order, as HMS requires")
        if self.run_min < 0.0 or self.rest_min < 0.0:
            raise ValueError(f"{HEAD_DISCHARGE_PUMP}: negative run or rest time")

    def head_m(self, level_m: FloatArray) -> FloatArray:
        """The total head at a pool level."""
        return self.discharge_elevation_m + self.head_loss_m - np.asarray(level_m)

    def pack(self) -> Packed:
        return Packed(
            kernel.PUMP, self.outlet,
            (self.on_m, self.off_m, self.intake_m, self.discharge_elevation_m + self.head_loss_m, float(self.units),
             self.run_min * SECONDS_PER_MINUTE, self.rest_min * SECONDS_PER_MINUTE),
            self.heads_m, self.flows_m3s,
        )

    def label(self) -> str:
        return "pump"


@STRUCTURE_KINDS.register(CULVERT)
@dataclass(frozen=True)
class Culvert:
    """HMS's culvert outlet, box or circular barrels (:mod:`wadi2d.hydrology.culvert`), routed as a rating of pool
    against flow at the reservoir's fixed tailwater (``tailwater_m``, None for none) up to the top of its pool table
    (``top_m``); the reservoir checks both are its own. ``span_m`` is the diameter again for a circular barrel."""

    shape: str
    chart: int
    scale: int
    control: str
    rise_m: float
    span_m: float
    barrels: int
    length_m: float
    entrance: float
    exit: float
    n: float
    inlet_m: float
    outlet_m: float
    outlet: int = MAIN_OUTLET
    tailwater_m: float | None = None
    top_m: float = math.nan

    def __post_init__(self) -> None:
        name = f"culvert ({self.shape}, chart {self.chart} scale {self.scale})"
        if self.shape not in (culverts.BOX, culverts.CIRCULAR):
            raise ValueError(f"{name}: only {culverts.BOX} and {culverts.CIRCULAR} barrels are measured against HMS")
        chart = culverts.INLET_CHARTS.get((self.chart, self.scale))
        if chart is None or chart.shape != self.shape:
            raise ValueError(f"{name}: no such inlet chart for this shape in the measured table")
        if self.control not in culverts.CONTROLS:
            raise ValueError(f"{name}: solution control {self.control!r}")
        if self.barrels < 1 or min(self.rise_m, self.span_m, self.length_m, self.n) <= 0.0:
            raise ValueError(f"{name}: {self.barrels} barrels of {self.rise_m} x {self.span_m} m, {self.length_m} m")
        if self.inlet_m <= self.outlet_m:
            raise ValueError(f"{name}: a barrel with no fall ({self.inlet_m} to {self.outlet_m} m) was not measured")

    @property
    def barrel(self) -> culverts.Barrel:
        feet = culverts.FEET_PER_METRE
        return culverts.Barrel(
            self.shape, self.rise_m * feet, self.span_m * feet, self.length_m * feet, self.inlet_m * feet,
            self.outlet_m * feet, self.n, self.entrance, self.exit,
        )

    @cached_property
    def _rating(self) -> tuple[FloatArray, FloatArray]:
        if math.isnan(self.top_m):
            raise ValueError("a culvert routes once its reservoir has given it the top of the pool table")
        return culverts.rating(
            self.barrel, culverts.INLET_CHARTS[self.chart, self.scale], self.control, self.barrels, self.tailwater_m,
            self.top_m,
        )

    def pack(self) -> Packed:
        levels, flows = self._rating
        return Packed(kernel.RATING_CURVE, self.outlet, (NO_PARAMETER,) * 3, levels, flows)

    def label(self) -> str:
        return "culvert"


@dataclass(frozen=True)
class MonthlyEvaporation:
    """HMS's Monthly Evaporation: twelve depths, mm, January first, each spread evenly over its month's steps."""

    depths_mm: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.depths_mm) != MONTHS or min(self.depths_mm) < 0.0:
            raise ValueError("monthly evaporation needs twelve depths, none negative")

    def rates(self, start: datetime, steps: int, dt_minutes: float) -> FloatArray:
        """The rate of each control step, m/s, by the month the step starts in; February has 28 days in HMS."""
        out = np.empty(max(steps, 1))
        for step in range(len(out)):
            moment = start + timedelta(minutes=step * dt_minutes)
            days = HMS_FEBRUARY_DAYS if moment.month == FEBRUARY else calendar.monthrange(moment.year, moment.month)[1]
            out[step] = self.depths_mm[moment.month - 1] / MILLIMETRES_PER_METRE / (days * SECONDS_PER_DAY)
        return out


@dataclass(frozen=True, eq=False)
class PackedSet:
    """Every structure of a reservoir as the kernel's arrays."""

    kinds: np.ndarray
    outlets: np.ndarray
    parameters: np.ndarray
    table_x: np.ndarray
    table_y: np.ndarray
    table_start: np.ndarray
    table_end: np.ndarray


def pack_all(structures: tuple[Structure, ...]) -> PackedSet:
    """The kernel's arrays of a reservoir's structures, in their order, tables concatenated."""
    packed = [structure.pack() for structure in structures]
    lengths = np.array([len(p.table_x) for p in packed], dtype=np.int64)
    ends = np.cumsum(lengths)
    return PackedSet(
        kinds=np.array([p.kind for p in packed], dtype=np.int64),
        outlets=np.array([p.outlet for p in packed], dtype=np.int64),
        parameters=np.array(
            [tuple(p.parameters) + (NO_PARAMETER,) * (PARAMETER_SLOTS - len(p.parameters)) for p in packed],
            dtype=np.float64,
        ).reshape(len(packed), PARAMETER_SLOTS),
        table_x=np.concatenate([np.asarray(p.table_x, dtype=np.float64) for p in packed] + [np.zeros(0)]),
        table_y=np.concatenate([np.asarray(p.table_y, dtype=np.float64) for p in packed] + [np.zeros(0)]),
        table_start=(ends - lengths).astype(np.int64),
        table_end=ends.astype(np.int64),
    )


def flows_at(
    structures: tuple[Structure, ...],
    levels: FloatArray,
    tailwater: tuple[float, float],
    bottom: float,
    active: np.ndarray | None = None,
) -> np.ndarray:
    """The flow of each structure at each pool level, m3/s (rows: levels); ``tailwater`` is (main, auxiliary),
    NaN for none, ``bottom`` the first elevation of the storage table, and ``active`` each structure's state at each
    level (a pump on, 1, or off, 0), every structure active when None."""
    arrays = pack_all(structures)
    levels = np.atleast_1d(np.asarray(levels, dtype=np.float64))
    if active is None:
        active = np.ones((len(levels), len(structures)))
    return kernel.structure_flows(
        levels,
        arrays.kinds,
        arrays.outlets,
        arrays.parameters,
        arrays.table_x,
        arrays.table_y,
        arrays.table_start,
        arrays.table_end,
        np.array(tailwater, dtype=np.float64),
        bottom,
        np.asarray(active, dtype=np.float64),
    )
