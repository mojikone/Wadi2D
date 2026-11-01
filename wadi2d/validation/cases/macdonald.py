"""MacDonald steady 1D cases: the depth profile is prescribed, the bed follows from it.

MacDonald, I., Baines, M.J., Nichols, N.K., Samuels, P.G. (1997), Analytic benchmark solutions for
open-channel flows, J. Hydraul. Eng. 123(11), 1041-1045. Subcritical and supercritical profiles and the
1000 m, ``q = 2``, ``n = 0.033`` set-up of SWASHES (Delestre et al. 2013, Int. J. Numer. Meth. Fluids 72(3),
long channel cases). The jump case keeps that set-up with a profile built here, because the bed is exact by
construction for any profile: two linear branches meeting at conjugate depths. Steep ahead of the jump and
mild behind it, so the jump is stable in position.

Steady momentum with Manning friction on a wide channel gives
``z' = (q^2 / (g h^3) - 1) h' - Sf(h)``, that is ``d(z + E)/dx = -Sf``, with ``E`` the specific energy. The
bed is that integral, carried from the outlet upstream and continuous across the jump.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from functools import cached_property
from typing import Protocol

import numpy as np
from scipy.interpolate import CubicHermiteSpline

from wadi2d.validation._constants import G
from wadi2d.validation._hydraulics import (
    critical_depth,
    friction_slope,
    sequent_depth,
    specific_energy,
    spinup_time,
)
from wadi2d.validation.case import TRANSMISSIVE, Boundaries, Boundary, BoundaryKind, Case, State, Tolerance
from wadi2d.validation.grid import FloatArray, UniformGrid

SOURCE = "MacDonald et al. 1997, J. Hydraul. Eng. 123(11); SWASHES (Delestre et al. 2013)"

UNIT_DISCHARGE = 2.0
MANNING_N = 0.033
OUTLET_BED = 0.0

SUBCRITICAL_BUMP = (0.5, 16.0)
"""Relative amplitude and decay rate of the depth bump of the SWASHES subcritical case."""
SUPERCRITICAL_DIP = (-0.2, 36.0)
"""The same for the depth dip of the SWASHES supercritical case."""
JUMP_POSITION = 0.4
"""Jump position as a fraction of the length."""
JUMP_INFLOW_RATIO = 0.7
"""Depth just ahead of the jump as a fraction of critical depth."""
JUMP_UPSTREAM_FALL = 0.2
JUMP_DOWNSTREAM_RISE = 0.05
"""Fall and rise of depth over one channel length, as fractions of the depth at the jump."""

SMOOTH_DEPTH_FRACTION = 0.002
JUMP_DEPTH_FRACTION = 0.02
"""Depth RMSE limits as fractions of critical depth; the jump smears over a few cells in any scheme."""
DISCHARGE_FRACTION = 0.005
"""Discharge RMSE limit as a fraction of ``q``."""

SPLINE_NODES = 4001
"""Nodes of the table of the friction integral; with Gauss panels its error is near round-off."""
GAUSS_POINTS = 3


class Variant(Enum):
    """The flow regime of the case."""

    SUBCRITICAL = auto()
    SUPERCRITICAL = auto()
    JUMP = auto()


class Profile(Protocol):
    """A depth profile with its derivative, in channel coordinates."""

    def depth(self, s: FloatArray) -> FloatArray:
        """Depth at distance ``s`` from the inlet, m."""
        ...

    def depth_dx(self, s: FloatArray) -> FloatArray:
        """Derivative of the depth, m/m."""
        ...


@dataclass(frozen=True)
class GaussianProfile:
    """``base (1 + amplitude exp(-rate (s / length - 1/2)^2))``, the SWASHES form."""

    base: float
    amplitude: float
    rate: float
    length: float

    def depth(self, s: FloatArray) -> FloatArray:
        """Depth, m."""
        xi = s / self.length - 0.5
        return self.base * (1.0 + self.amplitude * np.exp(-self.rate * xi * xi))

    def depth_dx(self, s: FloatArray) -> FloatArray:
        """Derivative of the depth."""
        xi = s / self.length - 0.5
        return (
            self.base * self.amplitude * np.exp(-self.rate * xi * xi) * (-2.0 * self.rate * xi) / self.length
        )


@dataclass(frozen=True)
class LinearProfile:
    """Depth ``anchor_depth`` at ``anchor`` with a constant slope."""

    anchor: float
    anchor_depth: float
    slope: float

    def depth(self, s: FloatArray) -> FloatArray:
        """Depth, m."""
        return self.anchor_depth + self.slope * (s - self.anchor)

    def depth_dx(self, s: FloatArray) -> FloatArray:
        """Derivative of the depth."""
        return np.full_like(s, self.slope, dtype=np.float64)


@dataclass(frozen=True)
class Branch:
    """A smooth stretch of the profile; branches meet at jumps."""

    start: float
    end: float
    profile: Profile


@dataclass(frozen=True)
class MacDonaldSolution:
    """Steady flow of unit discharge ``q`` along +x; ``origin`` is the x of the inlet."""

    q: float
    manning_n: float
    branches: tuple[Branch, ...]
    origin: float = 0.0
    outlet_bed: float = OUTLET_BED

    def _pick(self, s: FloatArray) -> list[tuple[int, FloatArray]]:
        """For each branch, its index and the mask of ``s`` on it; the ends extend past the channel."""
        edges = [-np.inf, *(b.end for b in self.branches[:-1]), np.inf]
        return [(k, (s >= edges[k]) & (s < edges[k + 1])) for k in range(len(self.branches))]

    def depth(self, s: FloatArray) -> FloatArray:
        """Depth at distance ``s`` from the inlet, m."""
        s = np.asarray(s, dtype=np.float64)
        out = np.empty_like(s)
        for k, mask in self._pick(s):
            out[mask] = self.branches[k].profile.depth(s[mask])
        return out

    def depth_dx(self, s: FloatArray) -> FloatArray:
        """Derivative of the depth."""
        s = np.asarray(s, dtype=np.float64)
        out = np.empty_like(s)
        for k, mask in self._pick(s):
            out[mask] = self.branches[k].profile.depth_dx(s[mask])
        return out

    def bed_slope(self, s: FloatArray) -> FloatArray:
        """``dz/dx`` from the steady momentum equation."""
        h = self.depth(s)
        return (self.q * self.q / (G * h**3) - 1.0) * self.depth_dx(s) - friction_slope(
            self.q, h, self.manning_n
        )

    def _friction_table(self, branch: Branch) -> CubicHermiteSpline:
        """The integral of ``Sf`` from the start of ``branch``, as a Hermite spline on exact slopes."""
        nodes = np.linspace(branch.start, branch.end, SPLINE_NODES)
        points, weights = np.polynomial.legendre.leggauss(GAUSS_POINTS)
        half = 0.5 * np.diff(nodes)[:, None]
        panels = (0.5 * (nodes[:-1] + nodes[1:]))[:, None] + half * points
        slopes = friction_slope(self.q, branch.profile.depth(panels), self.manning_n)
        increments = np.sum(half * weights * slopes, axis=1)
        integral = np.concatenate(([0.0], np.cumsum(increments)))
        end_slopes = friction_slope(self.q, branch.profile.depth(nodes), self.manning_n)
        return CubicHermiteSpline(nodes, integral, end_slopes)

    @cached_property
    def _tables(self) -> list[tuple[CubicHermiteSpline, float]]:
        """For each branch, the friction table and the bed at its end, marching from the outlet."""
        tables: list[tuple[CubicHermiteSpline, float]] = []
        bed_end = self.outlet_bed
        for branch in reversed(self.branches):
            table = self._friction_table(branch)
            tables.append((table, bed_end))
            ends = np.array([branch.start, branch.end])
            energy = specific_energy(self.q, branch.profile.depth(ends))
            bed_end += float(energy[1] - energy[0]) + float(table(branch.end))
        return tables[::-1]

    def _bed_along(self, s: FloatArray) -> FloatArray:
        out = np.empty_like(s)
        for k, mask in self._pick(s):
            branch, (table, bed_end) = self.branches[k], self._tables[k]
            end = np.array([branch.end])
            head_end = specific_energy(self.q, branch.profile.depth(end))[0] + table(branch.end)
            head = specific_energy(self.q, branch.profile.depth(s[mask])) + table(s[mask])
            out[mask] = bed_end + head_end - head
        return out

    def bed(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """Bed elevation, m."""
        return self._bed_along(np.asarray(x - self.origin, dtype=np.float64))

    def state(self, x: FloatArray, y: FloatArray, t: float) -> State:
        """The steady state, at every time."""
        h = self.depth(x - self.origin)
        return State(h, np.full_like(h, self.q), np.zeros_like(h))


def _jump_branches(q: float, length: float) -> tuple[Branch, ...]:
    hc = critical_depth(q)
    jump = JUMP_POSITION * length
    h_ahead = JUMP_INFLOW_RATIO * hc
    h_behind = sequent_depth(q, h_ahead)
    ahead = LinearProfile(jump, h_ahead, -JUMP_UPSTREAM_FALL * h_ahead / length)
    behind = LinearProfile(jump, h_behind, JUMP_DOWNSTREAM_RISE * h_behind / length)
    return Branch(0.0, jump, ahead), Branch(jump, length, behind)


def _smooth_branch(q: float, length: float, shape: tuple[float, float]) -> tuple[Branch, ...]:
    amplitude, rate = shape
    return (Branch(0.0, length, GaussianProfile(critical_depth(q), amplitude, rate, length)),)


def _boundaries(variant: Variant, q: float, h_in: float, h_out: float) -> Boundaries:
    inlet_depth = None if variant is Variant.SUBCRITICAL else h_in
    west = Boundary(BoundaryKind.INFLOW, discharge=q, depth=inlet_depth)
    east = TRANSMISSIVE if variant is Variant.SUPERCRITICAL else Boundary(BoundaryKind.DEPTH, depth=h_out)
    return Boundaries(west=west, east=east)


def build_macdonald(
    grid: UniformGrid,
    variant: Variant,
    *,
    q: float = UNIT_DISCHARGE,
    manning_n: float = MANNING_N,
) -> Case:
    """A steady case along +x over the whole grid length, uniform across y, closed on the two long sides."""
    length = grid.length_x
    if variant is Variant.JUMP:
        branches = _jump_branches(q, length)
        depth_fraction = JUMP_DEPTH_FRACTION
    else:
        shape = SUBCRITICAL_BUMP if variant is Variant.SUBCRITICAL else SUPERCRITICAL_DIP
        branches = _smooth_branch(q, length, shape)
        depth_fraction = SMOOTH_DEPTH_FRACTION
    solution = MacDonaldSolution(q, manning_n, branches, origin=grid.x0)
    ends = solution.depth(np.array([0.0, length]))
    hc = critical_depth(q)
    return Case(
        name=f"macdonald_{variant.name.lower()}",
        grid=grid,
        solution=solution,
        boundaries=_boundaries(variant, q, float(ends[0]), float(ends[1])),
        tolerance=Tolerance(depth_rmse=depth_fraction * hc, discharge_rmse=DISCHARGE_FRACTION * q),
        t_end=spinup_time(length, hc),
        source=SOURCE,
        manning_n=manning_n,
    )
