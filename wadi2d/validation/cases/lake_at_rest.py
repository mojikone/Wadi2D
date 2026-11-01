"""Lake at rest: flat still water over a bed that does not help the scheme.

Over a smooth bump, a seeded random rough bed and a steep planar slope with its shoreline in the domain. The
exact state never changes, so any motion is a failure of well-balancing (Audusse et al. 2004, SIAM J. Sci.
Comput. 25(6); SWASHES, Delestre et al. 2013, Int. J. Numer. Meth. Fluids 72(3), lake at rest with immersed
and emerged bump).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property

import numpy as np

from wadi2d.validation._hydraulics import spinup_time
from wadi2d.validation.case import BedFn, Boundaries, Case, State, Tolerance, resting_state
from wadi2d.validation.grid import FloatArray, UniformGrid

SOURCE = "Audusse et al. 2004; SWASHES lake at rest (Delestre et al. 2013)"

# Well-balancing holds to round-off at single precision on depth: the limits are round-off, not scheme error.
DEPTH_LIMIT = 1.0e-5
DISCHARGE_LIMIT = 1.0e-5
EXTENT_LIMIT = 0.999
VOLUME_LIMIT = 1.0e-6
TOLERANCE = Tolerance(
    depth_linf=DEPTH_LIMIT, discharge_linf=DISCHARGE_LIMIT, f_statistic=EXTENT_LIMIT, volume=VOLUME_LIMIT
)

DEFAULT_MODES = 256
"""Fourier modes of the rough bed; enough for the covariance to settle, cheap to evaluate."""


@dataclass(frozen=True)
class LakeSolution:
    """Flat water at level ``eta`` over any bed; dry where the bed stands above it."""

    bed_fn: BedFn
    eta: float

    def bed(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """Bed elevation, m."""
        return self.bed_fn(x, y)

    def state(self, x: FloatArray, y: FloatArray, t: float) -> State:
        """The same state at every time."""
        return resting_state(np.maximum(self.eta - self.bed_fn(x, y), 0.0))


@dataclass(frozen=True)
class GaussianBump:
    """A smooth bump of height ``amplitude`` and standard deviation ``width`` at ``(xc, yc)``."""

    amplitude: float
    width: float
    xc: float
    yc: float

    def __call__(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """Bed elevation, m."""
        r2 = (x - self.xc) ** 2 + (y - self.yc) ** 2
        return self.amplitude * np.exp(-0.5 * r2 / self.width**2)


@dataclass(frozen=True)
class RoughBed:
    """A stationary Gaussian random bed, defined at every point and reproducible from ``seed``.

    Random Fourier features (Rahimi and Recht 2007): the sum of ``n_modes`` cosines with wavenumbers drawn
    from a normal law has zero mean, standard deviation ``amplitude`` and, in expectation, the covariance
    ``amplitude^2 exp(-r^2 / (2 correlation_length^2))``. The sum needs no grid, so the bed can be sampled at
    any resolution and the samples agree.
    """

    amplitude: float
    correlation_length: float
    seed: int
    n_modes: int = DEFAULT_MODES

    @cached_property
    def _modes(self) -> tuple[FloatArray, FloatArray, FloatArray]:
        rng = np.random.default_rng(self.seed)
        kx, ky = rng.normal(0.0, 1.0 / self.correlation_length, size=(2, self.n_modes))
        return kx, ky, rng.uniform(0.0, 2.0 * math.pi, size=self.n_modes)

    def __call__(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """Bed elevation, m."""
        total = np.zeros_like(x, dtype=np.float64)
        for kx, ky, phase in zip(*self._modes, strict=True):
            total += np.cos(kx * x + ky * y + phase)
        return self.amplitude * math.sqrt(2.0 / self.n_modes) * total


@dataclass(frozen=True)
class PlanarBed:
    """A plane through the point ``(xs, ys)`` at level ``level``, rising at ``slope`` towards ``azimuth_deg``.

    The azimuth is counter-clockwise from +x. The shoreline of water at ``level`` is the line through the
    point, normal to the azimuth.
    """

    slope: float
    azimuth_deg: float
    xs: float
    ys: float
    level: float

    def __call__(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """Bed elevation, m."""
        azimuth = math.radians(self.azimuth_deg)
        along = (x - self.xs) * math.cos(azimuth) + (y - self.ys) * math.sin(azimuth)
        return self.level + self.slope * along


def sample_bed(bed: BedFn, grid: UniformGrid, k: int) -> FloatArray:
    """Sample ``bed`` at ``k x k`` points per cell, for building sub-grid tables.

    Returns shape ``(ny, nx, k, k)``: the points are the cell centres of the grid refined ``k`` times, and
    the last two axes run in the row and column order of the grid, so the array tiles back to that raster.
    """
    fine = grid.refine(k)
    samples = bed(*fine.mesh())
    return samples.reshape(grid.ny, k, grid.nx, k).swapaxes(1, 2)


def _lake(name: str, grid: UniformGrid, bed: BedFn, eta: float, depth_scale: float) -> Case:
    return Case(
        name=name,
        grid=grid,
        solution=LakeSolution(bed, eta),
        boundaries=Boundaries(),
        tolerance=TOLERANCE,
        t_end=spinup_time(max(grid.length_x, grid.length_y), depth_scale),
        source=SOURCE,
    )


def build_bump(
    grid: UniformGrid, *, eta: float = 1.0, amplitude: float = 0.5, width: float | None = None
) -> Case:
    """Still water over a Gaussian bump at the domain centre; ``amplitude`` above ``eta`` emerges it."""
    bed = GaussianBump(amplitude, width or 0.1 * grid.length_x, *grid.centre)
    return _lake("lake_bump", grid, bed, eta, eta)


def build_rough(
    grid: UniformGrid,
    *,
    amplitude: float = 0.5,
    correlation_length: float | None = None,
    seed: int = 0,
    eta: float = 0.0,
) -> Case:
    """Still water at ``eta`` over a seeded rough bed; the default leaves about half the bed emerged."""
    bed = RoughBed(amplitude, correlation_length or 5.0 * grid.dx, seed)
    return _lake("lake_rough", grid, bed, eta, amplitude)


def build_slope(
    grid: UniformGrid, *, slope: float = 0.1, azimuth_deg: float = 0.0, level: float = 0.0
) -> Case:
    """Still water on a steep plane, shoreline through the domain centre. Water level is ``level``."""
    bed = PlanarBed(slope, azimuth_deg, *grid.centre, level)
    return _lake("lake_slope", grid, bed, level, slope * 0.5 * grid.length_x)
