"""The contract between an analytic case and whatever tests a solver against it.

A case module exposes one or more ``build_*(grid, ...)`` functions returning a :class:`Case`. A test reads the
bed, the initial state, the boundaries, the exact state at any time and the tolerance from it, and needs
nothing else. Closed forms beyond the fields (periods, shorelines, front positions) stay on
``Case.solution``, an object of the case module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

import numpy as np

from wadi2d.validation._constants import WET_DEPTH
from wadi2d.validation.grid import FloatArray, UniformGrid

type BedFn = Callable[[FloatArray, FloatArray], FloatArray]


@dataclass(frozen=True)
class State:
    """Depth ``h`` (m) and unit discharges ``qx``, ``qy`` (m2/s), three arrays of the same shape."""

    h: FloatArray
    qx: FloatArray
    qy: FloatArray


class Solution(Protocol):
    """An exact solution, defined at any point so a bed can be sampled finer than the grid."""

    def bed(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """Bed elevation ``z(x, y)``, m."""
        ...

    def state(self, x: FloatArray, y: FloatArray, t: float) -> State:
        """Exact state at time ``t``, s."""
        ...


class BoundaryKind(Enum):
    """What a domain side does."""

    CLOSED = auto()  # wall, no flow
    TRANSMISSIVE = auto()  # zero gradient, for an outflow that needs no imposed value
    INFLOW = auto()  # imposed unit discharge; also an imposed depth when the inflow is supercritical
    DEPTH = auto()  # imposed depth
    EXACT = auto()  # the exact state of the case in the ghost cells


@dataclass(frozen=True)
class Boundary:
    """One side. ``discharge`` is signed along +x or +y (m2/s), ``depth`` in m; unused values stay None."""

    kind: BoundaryKind
    discharge: float | None = None
    depth: float | None = None


CLOSED = Boundary(BoundaryKind.CLOSED)
TRANSMISSIVE = Boundary(BoundaryKind.TRANSMISSIVE)
EXACT = Boundary(BoundaryKind.EXACT)


@dataclass(frozen=True)
class Boundaries:
    """The four sides of the rectangular domain."""

    west: Boundary = CLOSED
    east: Boundary = CLOSED
    south: Boundary = CLOSED
    north: Boundary = CLOSED

    @classmethod
    def uniform(cls, side: Boundary) -> Boundaries:
        """The same condition on all four sides."""
        return cls(side, side, side, side)

    @property
    def is_closed(self) -> bool:
        """True when no side lets water through, so the volume must stay at its initial value."""
        return all(b.kind is BoundaryKind.CLOSED for b in (self.west, self.east, self.south, self.north))


@dataclass(frozen=True)
class Tolerance:
    """Limits for a :class:`~wadi2d.validation.compare.Report`; None means not checked.

    Depth and surface limits are in m, discharge limits in m2/s, ``volume`` is a relative error and
    ``f_statistic`` a lower bound. All of them are over wet cells at the resolution stated in the README.
    """

    depth_rmse: float | None = None
    depth_linf: float | None = None
    discharge_rmse: float | None = None
    discharge_linf: float | None = None
    surface_rmse: float | None = None
    f_statistic: float | None = None
    volume: float | None = None
    wet_depth: float = WET_DEPTH


@dataclass(frozen=True)
class Case:
    """An analytic case on a grid. ``manning_n`` is 0 for a frictionless case; ``t_end`` is in s."""

    name: str
    grid: UniformGrid
    solution: Solution
    boundaries: Boundaries
    tolerance: Tolerance
    t_end: float
    source: str
    manning_n: float = 0.0
    surface_fn: BedFn | None = None

    def bed(self) -> FloatArray:
        """Bed elevation at the cell centres, shape ``(ny, nx)``."""
        return self.solution.bed(*self.grid.mesh())

    def initial(self) -> State:
        """The state at t = 0: the exact one, so a steady case starts on its answer."""
        return self.exact(0.0)

    def exact(self, t: float) -> State:
        """Exact state at the cell centres at time ``t``."""
        x, y = self.grid.mesh()
        return self.solution.state(x, y, t)

    def surface(self, t: float) -> FloatArray:
        """Exact water surface at the cell centres.

        ``surface_fn`` overrides depth plus bed where the surface is defined over a whole cell although
        the centre may sit on dry bank, as in the sub-grid channel case.
        """
        if self.surface_fn is not None:
            return self.surface_fn(*self.grid.mesh())
        return self.exact(t).h + self.bed()


def resting_state(h: FloatArray) -> State:
    """A state of depth ``h`` with no flow."""
    return State(h, np.zeros_like(h), np.zeros_like(h))
