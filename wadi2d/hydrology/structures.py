"""Reservoir outflow structures of HEC-HMS 4.12, behind one interface: each packs itself for the compiled kernel.

Interface: :class:`Structure` (the protocol), :class:`RatingSpillway`, :class:`Orifice`, :class:`LevelDamTop`,
:class:`TabularSeepage`, :class:`MonthlyEvaporation`, :class:`Packed`, :func:`pack_all`, :data:`STRUCTURE_KINDS`.
The broad-crested :class:`~wadi2d.hydrology.reservoir.Spillway` packs the same way. The laws live in
:mod:`wadi2d.hydrology.structure_kernel`, once; a new structure is a class here and a kind there.

What HMS does that is not in its manual, measured on W59's runs: an orifice's head is taken from the higher of its
centreline and the tailwater; a seepage with no tailwater reads its table at the pool over the bottom of the storage
table, and its tailwater-to-pool table changed nothing in any run, a tailwater above the pool giving negative seepage
from the pool-to-tailwater table instead; monthly evaporation spreads each month's depth over 28 days in February of a
leap year too, by the month a control step starts in.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

import numpy as np

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


@dataclass(frozen=True, eq=False)
class Packed:
    """One structure as the kernel reads it: kind and outlet codes, three numbers, and its table (may be empty)."""

    kind: int
    outlet: int
    parameters: tuple[float, float, float]
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
    """A level dam top, Q = C L H^1.5 over the crest. HMS's drowned rule is a curve not identified (W59), so a
    reservoir refuses a tailwater that reaches the crest."""

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
        parameters=np.array([p.parameters for p in packed], dtype=np.float64).reshape(len(packed), 3),
        table_x=np.concatenate([np.asarray(p.table_x, dtype=np.float64) for p in packed] + [np.zeros(0)]),
        table_y=np.concatenate([np.asarray(p.table_y, dtype=np.float64) for p in packed] + [np.zeros(0)]),
        table_start=(ends - lengths).astype(np.int64),
        table_end=ends.astype(np.int64),
    )


def flows_at(
    structures: tuple[Structure, ...], levels: FloatArray, tailwater: tuple[float, float], bottom: float
) -> np.ndarray:
    """The flow of each structure at each pool level, m3/s (rows: levels); ``tailwater`` is (main, auxiliary),
    NaN for none, and ``bottom`` the first elevation of the storage table."""
    arrays = pack_all(structures)
    return kernel.structure_flows(
        np.atleast_1d(np.asarray(levels, dtype=np.float64)),
        arrays.kinds,
        arrays.outlets,
        arrays.parameters,
        arrays.table_x,
        arrays.table_y,
        arrays.table_start,
        arrays.table_end,
        np.array(tailwater, dtype=np.float64),
        bottom,
    )
