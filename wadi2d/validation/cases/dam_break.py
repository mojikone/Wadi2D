"""Instantaneous dam break on a flat frictionless bed, as a 1D profile on a 2D grid.

Stoker, J.J. (1957), Water Waves, Interscience (wet bed: rarefaction, plateau, shock). Ritter, A. (1892), Die
Fortpflanzung der Wasserwellen, Z. Vereines Deutscher Ingenieure 36 (dry bed). Formulas as in SWASHES
(Delestre et al. 2013, Int. J. Numer. Meth. Fluids 72(3)).

The profile runs along x or y, with the deep side on the low-coordinate side of the dam at ``x0``. Each
case ends before the first wave reaches a domain edge, so the sides need no special treatment. Frictionless
only: no closed form exists with friction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property
from typing import Literal

import numpy as np
from scipy.optimize import brentq

from wadi2d.validation._constants import WAVE_ARRIVAL_SAFETY, G
from wadi2d.validation.case import Boundaries, Case, State, Tolerance
from wadi2d.validation.grid import FloatArray, UniformGrid

SOURCE = "Stoker 1957; Ritter 1892; SWASHES (Delestre et al. 2013)"

type Axis = Literal["x", "y"]

DEPTH_LEFT = 2.0
DEPTH_RIGHT = 0.5

STOKER_DEPTH_FRACTION = 0.01
"""Depth RMSE limit as a fraction of the upstream depth."""
RITTER_DEPTH_FRACTION = 0.02
"""As above; the wet-dry front is first order in any scheme."""
DISCHARGE_FRACTION = 0.03
"""Discharge RMSE limit as a fraction of ``h_left sqrt(g h_left)``."""
EXTENT_LIMIT = 0.95
VOLUME_LIMIT = 1.0e-4
"""Relative volume drift over the run, single precision included."""


def _fan(xi: FloatArray, celerity: float) -> tuple[FloatArray, FloatArray]:
    """Depth and velocity in the rarefaction, as functions of ``xi = (x - x0) / t``."""
    return (2.0 * celerity - xi) ** 2 / (9.0 * G), 2.0 * (xi + celerity) / 3.0


def _pack(h: FloatArray, u: FloatArray, axis: Axis) -> State:
    q, zero = h * u, np.zeros_like(h)
    return State(h, q, zero) if axis == "x" else State(h, zero, q)


@dataclass(frozen=True)
class StarState:
    """The plateau between rarefaction and shock."""

    depth: float
    velocity: float
    celerity: float
    shock_speed: float


def solve_star(h_left: float, h_right: float) -> StarState:
    """Match the velocity behind the rarefaction with the one behind the shock (Stoker 1957)."""
    if not 0.0 < h_right < h_left:
        raise ValueError(f"need 0 < h_right < h_left, got {h_right}, {h_left}")
    c_left = math.sqrt(G * h_left)

    def mismatch(h: float) -> float:
        behind_rarefaction = 2.0 * (c_left - math.sqrt(G * h))
        behind_shock = (h - h_right) * math.sqrt(G * (h + h_right) / (2.0 * h * h_right))
        return behind_rarefaction - behind_shock

    depth = float(brentq(mismatch, h_right, h_left, xtol=1.0e-13))
    velocity = 2.0 * (c_left - math.sqrt(G * depth))
    return StarState(depth, velocity, math.sqrt(G * depth), depth * velocity / (depth - h_right))


@dataclass(frozen=True)
class _DamBreak:
    h_left: float
    x0: float
    axis: Axis

    @property
    def c_left(self) -> float:
        """Long-wave speed of the deep side, m/s."""
        return math.sqrt(G * self.h_left)

    def head(self, t: float) -> float:
        """Upstream edge of the rarefaction."""
        return self.x0 - self.c_left * t

    def along(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """The coordinate the profile runs along."""
        return x if self.axis == "x" else y

    def bed(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """Flat bed at zero."""
        return np.zeros_like(x, dtype=np.float64)


@dataclass(frozen=True)
class StokerSolution(_DamBreak):
    """Dam break on a wet bed of depth ``h_right``."""

    h_right: float

    @cached_property
    def star(self) -> StarState:
        """The plateau state."""
        return solve_star(self.h_left, self.h_right)

    def tail(self, t: float) -> float:
        """Downstream edge of the rarefaction."""
        return self.x0 + (self.star.velocity - self.star.celerity) * t

    def shock(self, t: float) -> float:
        """Shock position."""
        return self.x0 + self.star.shock_speed * t

    def state(self, x: FloatArray, y: FloatArray, t: float) -> State:
        """Exact state at time ``t``."""
        s = self.along(x, y)
        if t <= 0.0:
            return _pack(np.where(s <= self.x0, self.h_left, self.h_right), np.zeros_like(s), self.axis)
        xi = (s - self.x0) / t
        star = self.star
        fan_h, fan_u = _fan(xi, self.c_left)
        h = np.select(
            [xi <= -self.c_left, xi <= star.velocity - star.celerity, xi <= star.shock_speed],
            [self.h_left, fan_h, star.depth],
            self.h_right,
        )
        u = np.select(
            [xi <= -self.c_left, xi <= star.velocity - star.celerity, xi <= star.shock_speed],
            [0.0, fan_u, star.velocity],
            0.0,
        )
        return _pack(h, u, self.axis)


@dataclass(frozen=True)
class RitterSolution(_DamBreak):
    """Dam break on a dry bed."""

    def front(self, t: float) -> float:
        """Wet-dry front position."""
        return self.x0 + 2.0 * self.c_left * t

    def state(self, x: FloatArray, y: FloatArray, t: float) -> State:
        """Exact state at time ``t``."""
        s = self.along(x, y)
        if t <= 0.0:
            return _pack(np.where(s <= self.x0, self.h_left, 0.0), np.zeros_like(s), self.axis)
        xi = (s - self.x0) / t
        fan_h, fan_u = _fan(xi, self.c_left)
        conditions = [xi <= -self.c_left, xi <= 2.0 * self.c_left]
        return _pack(
            np.select(conditions, [self.h_left, fan_h], 0.0),
            np.select(conditions, [0.0, fan_u], 0.0),
            self.axis,
        )


def _span(grid: UniformGrid, axis: Axis) -> tuple[float, float]:
    return (grid.x0, grid.length_x) if axis == "x" else (grid.y0, grid.length_y)


def _dam_position(grid: UniformGrid, axis: Axis, x0: float | None) -> float:
    start, length = _span(grid, axis)
    position = start + 0.5 * length if x0 is None else x0
    if not start < position < start + length:
        raise ValueError(f"dam position {position} m is outside the domain")
    return position


def _end_time(grid: UniformGrid, axis: Axis, x0: float, back_speed: float, front_speed: float) -> float:
    start, length = _span(grid, axis)
    return WAVE_ARRIVAL_SAFETY * min((x0 - start) / back_speed, (start + length - x0) / front_speed)


def _tolerance(h_left: float, depth_fraction: float) -> Tolerance:
    return Tolerance(
        depth_rmse=depth_fraction * h_left,
        discharge_rmse=DISCHARGE_FRACTION * h_left * math.sqrt(G * h_left),
        f_statistic=EXTENT_LIMIT,
        volume=VOLUME_LIMIT,
    )


def build_stoker(
    grid: UniformGrid,
    *,
    h_left: float = DEPTH_LEFT,
    h_right: float = DEPTH_RIGHT,
    x0: float | None = None,
    axis: Axis = "x",
) -> Case:
    """Wet-bed dam break, dam at the domain centre by default."""
    solution = StokerSolution(h_left, _dam_position(grid, axis, x0), axis, h_right)
    return Case(
        name=f"dam_break_stoker_{axis}",
        grid=grid,
        solution=solution,
        boundaries=Boundaries(),
        tolerance=_tolerance(h_left, STOKER_DEPTH_FRACTION),
        t_end=_end_time(grid, axis, solution.x0, solution.c_left, solution.star.shock_speed),
        source=SOURCE,
    )


def build_ritter(
    grid: UniformGrid, *, h_left: float = DEPTH_LEFT, x0: float | None = None, axis: Axis = "x"
) -> Case:
    """Dry-bed dam break, dam at the domain centre by default."""
    solution = RitterSolution(h_left, _dam_position(grid, axis, x0), axis)
    return Case(
        name=f"dam_break_ritter_{axis}",
        grid=grid,
        solution=solution,
        boundaries=Boundaries(),
        tolerance=_tolerance(h_left, RITTER_DEPTH_FRACTION),
        t_end=_end_time(grid, axis, solution.x0, solution.c_left, 2.0 * solution.c_left),
        source=SOURCE,
    )
