"""Thacker's oscillations in a parabolic bowl, moving shoreline with no friction.

Thacker, W.C. (1981), Some exact solutions to the nonlinear shallow-water wave equations, J. Fluid Mech. 107,
499-508; in the form and with the default parameters of SWASHES (Delestre et al. 2013, Int. J. Numer. Meth.
Fluids 72(3), sections on the planar surface in a paraboloid and the radially symmetrical paraboloid).

Bowl, in both cases: ``z(r) = -h0 (1 - r^2 / a^2)``, with ``r`` measured from the bowl centre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from wadi2d.validation._constants import G
from wadi2d.validation.case import Boundaries, Case, State, Tolerance
from wadi2d.validation.grid import FloatArray, UniformGrid

SOURCE = "Thacker 1981, J. Fluid Mech. 107; SWASHES (Delestre et al. 2013)"

# Parameters of SWASHES.
BOWL_RADIUS = 1.0
CENTRE_DEPTH = 0.1
PLANAR_ETA = 0.5
CURVED_R0 = 0.8
PERIODS_TO_RUN = 3.0

DEPTH_RMSE_FRACTION = 0.02
"""Depth RMSE limit as a fraction of ``h0``."""
DISCHARGE_RMSE_FRACTION = 0.05
"""Discharge RMSE limit as a fraction of the peak of ``h0 sqrt(g h0)``."""
EXTENT_LIMIT = 0.95
VOLUME_LIMIT = 1.0e-4
"""Relative volume drift over the run, single precision included."""


@dataclass(frozen=True)
class _Bowl:
    """The parabolic bowl with its centre at ``(xc, yc)``."""

    radius: float
    centre_depth: float
    xc: float
    yc: float

    def relative(self, x: FloatArray, y: FloatArray) -> tuple[FloatArray, FloatArray]:
        """Coordinates from the bowl centre."""
        return x - self.xc, y - self.yc

    def bed(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """Bed elevation, m."""
        dx, dy = self.relative(x, y)
        return -self.centre_depth * (1.0 - (dx * dx + dy * dy) / self.radius**2)


@dataclass(frozen=True)
class PlanarSolution(_Bowl):
    """A plane of water sloshing in the bowl: uniform velocity rotating at ``omega``, shoreline a circle."""

    eta: float

    @property
    def omega(self) -> float:
        """Angular frequency, ``sqrt(2 g h0) / a``, rad/s."""
        return math.sqrt(2.0 * G * self.centre_depth) / self.radius

    @property
    def period(self) -> float:
        """Oscillation period, s."""
        return 2.0 * math.pi / self.omega

    def shoreline_centre(self, t: float) -> tuple[float, float]:
        """Centre of the circular shoreline, whose radius stays ``a``."""
        phase = self.omega * t
        return self.xc + self.eta * math.cos(phase), self.yc + self.eta * math.sin(phase)

    def velocity(self, t: float) -> tuple[float, float]:
        """The uniform velocity ``(u, v)``, m/s."""
        phase = self.omega * t
        speed = self.eta * self.omega
        return -speed * math.sin(phase), speed * math.cos(phase)

    def state(self, x: FloatArray, y: FloatArray, t: float) -> State:
        """Exact state at time ``t``."""
        dx, dy = self.relative(x, y)
        phase = self.omega * t
        scale = self.eta * self.centre_depth / self.radius**2
        surface = scale * (2.0 * dx * math.cos(phase) + 2.0 * dy * math.sin(phase) - self.eta)
        h = np.maximum(surface - self.bed(x, y), 0.0)
        u, v = self.velocity(t)
        return State(h, h * u, h * v)


@dataclass(frozen=True)
class CurvedSolution(_Bowl):
    """A radially symmetric pulsation: the wet disc breathes, its surface stays a paraboloid.

    With ``A = (a^2 - r0^2) / (a^2 + r0^2)`` and ``s(t) = sqrt(1 - A^2) / (1 - A cos(omega t))``, the SWASHES
    depth reduces to ``h = h0 (s - (r / a)^2 s^2)``, which gives the shoreline ``r = a / sqrt(s)``.
    """

    r0: float

    @property
    def amplitude(self) -> float:
        """The parameter ``A``."""
        return (self.radius**2 - self.r0**2) / (self.radius**2 + self.r0**2)

    @property
    def omega(self) -> float:
        """Angular frequency, ``sqrt(8 g h0) / a``, rad/s."""
        return math.sqrt(8.0 * G * self.centre_depth) / self.radius

    @property
    def period(self) -> float:
        """Oscillation period, s."""
        return 2.0 * math.pi / self.omega

    def _stretch(self, t: float) -> float:
        """The factor ``s(t)``."""
        a = self.amplitude
        return math.sqrt(1.0 - a * a) / (1.0 - a * math.cos(self.omega * t))

    def shoreline_radius(self, t: float) -> float:
        """Radius of the shoreline at time ``t``, m."""
        return self.radius / math.sqrt(self._stretch(t))

    @property
    def max_shoreline_radius(self) -> float:
        """Largest radius of the shoreline, reached at half a period, m."""
        return self.shoreline_radius(0.5 * self.period)

    def radial_rate(self, t: float) -> float:
        """The factor ``f`` of the radial velocity ``u_r = f r``, 1/s."""
        a = self.amplitude
        phase = self.omega * t
        return self.omega * a * math.sin(phase) / (2.0 * (1.0 - a * math.cos(phase)))

    def state(self, x: FloatArray, y: FloatArray, t: float) -> State:
        """Exact state at time ``t``."""
        dx, dy = self.relative(x, y)
        s = self._stretch(t)
        h = np.maximum(self.centre_depth * (s - (dx * dx + dy * dy) / self.radius**2 * s * s), 0.0)
        rate = self.radial_rate(t)
        return State(h, h * rate * dx, h * rate * dy)


def _check_fits(grid: UniformGrid, xc: float, yc: float, reach: float) -> None:
    half_x, half_y = 0.5 * grid.length_x, 0.5 * grid.length_y
    gap = min(half_x - abs(xc - grid.centre[0]), half_y - abs(yc - grid.centre[1])) - reach
    if gap <= 0.0:
        raise ValueError(f"the wet region of radius {reach} m leaves the domain")


def _tolerance(centre_depth: float) -> Tolerance:
    return Tolerance(
        depth_rmse=DEPTH_RMSE_FRACTION * centre_depth,
        discharge_rmse=DISCHARGE_RMSE_FRACTION * centre_depth * math.sqrt(G * centre_depth),
        f_statistic=EXTENT_LIMIT,
        volume=VOLUME_LIMIT,
    )


def build_planar(
    grid: UniformGrid,
    *,
    radius: float = BOWL_RADIUS,
    centre_depth: float = CENTRE_DEPTH,
    eta: float = PLANAR_ETA,
    centre: tuple[float, float] | None = None,
) -> Case:
    """Planar oscillation in a bowl centred at ``centre`` (the domain centre by default)."""
    xc, yc = centre or grid.centre
    _check_fits(grid, xc, yc, radius + eta)
    solution = PlanarSolution(radius, centre_depth, xc, yc, eta)
    return Case(
        name="thacker_planar",
        grid=grid,
        solution=solution,
        boundaries=Boundaries(),
        tolerance=_tolerance(centre_depth),
        t_end=PERIODS_TO_RUN * solution.period,
        source=SOURCE,
    )


def build_curved(
    grid: UniformGrid,
    *,
    radius: float = BOWL_RADIUS,
    centre_depth: float = CENTRE_DEPTH,
    r0: float = CURVED_R0,
    centre: tuple[float, float] | None = None,
) -> Case:
    """Radially symmetric oscillation in a bowl centred at ``centre`` (the domain centre by default)."""
    xc, yc = centre or grid.centre
    solution = CurvedSolution(radius, centre_depth, xc, yc, r0)
    _check_fits(grid, xc, yc, solution.max_shoreline_radius)
    return Case(
        name="thacker_curved",
        grid=grid,
        solution=solution,
        boundaries=Boundaries(),
        tolerance=_tolerance(centre_depth),
        t_end=PERIODS_TO_RUN * solution.period,
        source=SOURCE,
    )
