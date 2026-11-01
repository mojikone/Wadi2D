"""Flow over a thin broad-crested weir across a flat frictionless channel.

Free flow passes critical depth on the crest: ``yc = 2 H / 3`` and ``q = (2/3) sqrt(2 g / 3) H^1.5``, about
``1.705 H^1.5`` in SI units (Henderson 1966, Open Channel Flow, ch. 6; Chow 1959). ``H`` is the total head
over the crest, velocity head included.

The drowned reference is not unique, and the forms here differ widely: at ``H = 1``, ``P = 2``, tailwater
2.9 m, ``q`` is 1.26, 1.52 and 0.81 m2/s in the order below. Choose one before reading a tolerance.

* ``DrownedReference.ENERGY``, the textbook form: energy from upstream to the crest with the tailwater level
  standing on the crest, ``q = hd sqrt(2 g (H - hd))``. Joins the free law at ``hd = 2 H / 3``.
* ``DrownedReference.BORDA``: energy up to the crest, then momentum from the crest to the tailwater with
  hydrostatic pressure on the downstream step (a Borda expansion). This is the closure of the shallow-water
  equations on a step, and it stays modular above the textbook 2/3, to ``hd = 0.79 H`` at ``P / H = 2``.
* ``villemonte_unit_discharge`` (Villemonte 1947, Eng. News-Record 139), the empirical reduction factor,
  from sharp-crested data; it lies below the free law at any submergence, so it never meets the other two.

The crest is one cell wide by default, in the bed. With ``crest_width=0`` the bed stays flat and the crest
is only a line on a cell face at ``crest_x``, for a solver that carries it as a crest-aware face.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np
from scipy.optimize import brentq

from wadi2d.validation._constants import G
from wadi2d.validation._hydraulics import depth_from_energy, specific_force, spinup_time
from wadi2d.validation.case import TRANSMISSIVE, Boundaries, Boundary, BoundaryKind, Case, State, Tolerance
from wadi2d.validation.grid import FloatArray, UniformGrid

SOURCE = "Henderson 1966; Chow 1959; Villemonte 1947 for the empirical drowned factor"

HEAD = 1.0
CREST_HEIGHT = 2.0

MODULAR_LIMIT = 2.0 / 3.0
"""Crest depth over head at critical flow, and the textbook limit of free flow."""
VILLEMONTE_HEAD_POWER = 1.5
VILLEMONTE_EXPONENT = 0.385
EDGE_MARGIN = 1.0e-9
"""Relative margin on the crest edge, against rounding of cell centres."""

FREE_FRACTION = 0.05
DROWNED_FRACTION = 0.10
"""RMSE limits on discharge (fraction of ``q``) and depth (fraction of ``H``); see the README."""


class DrownedReference(Enum):
    """Which law closes the drowned weir; see the module docstring."""

    ENERGY = auto()
    BORDA = auto()


def free_unit_discharge(head: float) -> float:
    """Free flow over an ideal critical section, m2/s."""
    return MODULAR_LIMIT * math.sqrt(2.0 * G / 3.0) * head**1.5


def drowned_unit_discharge(head: float, crest_depth: float) -> float:
    """Textbook drowned flow with ``crest_depth`` of water on the crest; the free law below the limit."""
    if crest_depth <= MODULAR_LIMIT * head:
        return free_unit_discharge(head)
    return crest_depth * math.sqrt(2.0 * G * (head - crest_depth))


def villemonte_unit_discharge(head: float, tail_head: float) -> float:
    """Free flow reduced by the Villemonte factor; ``tail_head`` is the tailwater head over the crest."""
    submergence = max(tail_head, 0.0) / head
    return free_unit_discharge(head) * (1.0 - submergence**VILLEMONTE_HEAD_POWER) ** VILLEMONTE_EXPONENT


def borda_crest_depth(head: float, crest_height: float, tailwater: float) -> float | None:
    """Depth on the crest by energy upstream and momentum downstream; None while the crest stays critical.

    ``tailwater`` is the depth on the flat bed downstream of the weir.
    """

    def discharge(y: float) -> float:
        return y * math.sqrt(2.0 * G * (head - y))

    def momentum_excess(y: float) -> float:
        q = discharge(y)
        return q * q / y + 0.5 * G * (y + crest_height) ** 2 - float(specific_force(q, tailwater))

    critical = MODULAR_LIMIT * head
    if momentum_excess(critical) >= 0.0:
        return None
    return float(brentq(momentum_excess, critical, head))


@dataclass(frozen=True)
class WeirSolution:
    """Piecewise constant steady state on the three stretches of the channel."""

    q: float
    head: float
    crest_height: float
    crest_x: float
    crest_width: float
    upstream_depth: float
    crest_depth: float
    downstream_depth: float

    @property
    def _half_width(self) -> float:
        """Half the crest width, with a margin so a cell centre on the edge reads as crest."""
        return 0.5 * self.crest_width * (1.0 + EDGE_MARGIN)

    def bed(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """Bed elevation, m; flat when the crest is a line."""
        if self.crest_width == 0.0:
            return np.zeros_like(x, dtype=np.float64)
        return np.where(np.abs(x - self.crest_x) <= self._half_width, self.crest_height, 0.0)

    def state(self, x: FloatArray, y: FloatArray, t: float) -> State:
        """The steady state, at every time."""
        h = np.select(
            [x < self.crest_x - self._half_width, x <= self.crest_x + self._half_width],
            [self.upstream_depth, self.crest_depth],
            self.downstream_depth,
        )
        return State(h, np.full_like(h, self.q), np.zeros_like(h))


def _free(head: float, crest_height: float) -> tuple[float, float, float, float]:
    q = free_unit_discharge(head)
    energy = crest_height + head
    downstream = depth_from_energy(q, energy, subcritical=False)
    return q, depth_from_energy(q, energy, subcritical=True), MODULAR_LIMIT * head, downstream


def _drowned(
    head: float, crest_height: float, tailwater: float, reference: DrownedReference
) -> tuple[float, float, float, float]:
    if reference is DrownedReference.BORDA:
        crest_depth = borda_crest_depth(head, crest_height, tailwater)
    else:
        crest_depth = tailwater - crest_height
    if crest_depth is None or crest_depth <= MODULAR_LIMIT * head or crest_depth >= head:
        raise ValueError(f"tailwater {tailwater} m does not drown the weir at head {head} m")
    q = drowned_unit_discharge(head, crest_depth)
    upstream = depth_from_energy(q, crest_height + head, subcritical=True)
    return q, upstream, crest_depth, tailwater


def build_weir(
    grid: UniformGrid,
    *,
    head: float = HEAD,
    crest_height: float = CREST_HEIGHT,
    tailwater: float | None = None,
    reference: DrownedReference = DrownedReference.ENERGY,
    crest_width: float | None = None,
) -> Case:
    """A weir across the middle of the grid, flow along +x. ``tailwater`` set means the drowned variant.

    Inflow discharge upstream. Downstream a free outflow, or the tailwater depth when drowned. A free weir
    has no tailwater in the exact state: the flow stays supercritical to the outlet.
    """
    width = grid.dx if crest_width is None else crest_width
    crest_x = grid.x0 + (grid.nx // 2) * grid.dx + 0.5 * width
    drowned = tailwater is not None
    q, upstream, on_crest, downstream = (
        _drowned(head, crest_height, tailwater, reference) if drowned else _free(head, crest_height)
    )
    solution = WeirSolution(q, head, crest_height, crest_x, width, upstream, on_crest, downstream)
    east = Boundary(BoundaryKind.DEPTH, depth=tailwater) if drowned else TRANSMISSIVE
    fraction = DROWNED_FRACTION if drowned else FREE_FRACTION
    return Case(
        name=f"weir_{'drowned_' + reference.name.lower() if drowned else 'free'}",
        grid=grid,
        solution=solution,
        boundaries=Boundaries(west=Boundary(BoundaryKind.INFLOW, discharge=q), east=east),
        tolerance=Tolerance(depth_rmse=fraction * head, discharge_rmse=fraction * q),
        t_end=spinup_time(grid.length_x, crest_height + head),
        source=SOURCE,
    )
