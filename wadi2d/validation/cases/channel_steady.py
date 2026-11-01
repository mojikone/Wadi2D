"""Uniform flow in a channel carved into a plain, at an angle to the grid.

The rotated-channel test of sub-grid conveyance: the same channel at 0, 15, 30 and 45 degrees must carry the
same discharge at the same depth. Normal depth from Manning (Chow 1959, Open-Channel Hydraulics, ch. 6).

The plain is flat across the channel and falls along it at the channel slope, since uniform flow needs that
slope; only the channel is carved into it, to ``bank_height`` below the plain. Flow runs along the axis at
``theta_deg`` counter-clockwise from +x, through ``centre``.

Two references, and they differ, so a test must say which one it means:

* ``Conveyance.HYDRAULIC_RADIUS``: the textbook ``Q = (1/n) A R^(2/3) S^(1/2)``, ``R = A / P``. Walls count.
  A one-dimensional section and a conveyance table built on ``A / P`` converge to this.
* ``Conveyance.STRIP``: ``Q = (1/n) S^(1/2) int h^(5/3) dn``. Each strip takes friction on its own bed, no
  wall friction and no lateral exchange: the steady solution of the depth-averaged equations on a grid
  that resolves the section. Normal depth comes out shallower.

The local unit discharge in the exact field follows the strip law scaled to the total ``Q`` in both cases.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from functools import cached_property

import numpy as np
from scipy.optimize import brentq

from wadi2d.validation._constants import G
from wadi2d.validation._hydraulics import spinup_time
from wadi2d.validation.case import EXACT, Boundaries, Case, State, Tolerance
from wadi2d.validation.grid import FloatArray, UniformGrid

SOURCE = "Manning normal depth, Chow 1959"

ANGLES_DEG = (0.0, 15.0, 30.0, 45.0)

DISCHARGE = 30.0
BED_SLOPE = 0.002
MANNING_N = 0.03
BANK_HEIGHT = 3.0
PLAIN_LEVEL = 100.0
"""Plain elevation at the centre, m; positive so a run also meets a real elevation magnitude."""
RECTANGULAR_WIDTH = 20.0
TRAPEZOIDAL_WIDTH = 10.0
TRAPEZOIDAL_SIDE_SLOPE = 2.0
"""Horizontal over vertical."""

DEPTH_FRACTION = 0.02
"""Depth and surface RMSE limits as fractions of normal depth."""
DISCHARGE_FRACTION = 0.05
"""Discharge RMSE limit as a fraction of the mean unit discharge."""

MANNING_DEPTH_POWER = 5.0 / 3.0
RADIUS_POWER = 2.0 / 3.0
STRIP_SIDE_FACTOR = 0.75
"""The two side slopes integrate to ``0.75 m y^(8/3)`` in the strip law."""
SMALL_DEPTH = 1.0e-6


class Shape(Enum):
    """The section of the channel."""

    RECTANGULAR = auto()
    TRAPEZOIDAL = auto()


class Conveyance(Enum):
    """Which Manning law defines normal depth; see the module docstring."""

    HYDRAULIC_RADIUS = auto()
    STRIP = auto()


@dataclass(frozen=True)
class Section:
    """Symmetric section: base ``base_width``, ``side_slope`` H:V (0 is vertical), then the plain."""

    base_width: float
    side_slope: float
    bank_height: float

    def area(self, y: float) -> float:
        """Flow area at depth ``y``, m2."""
        return (self.base_width + self.side_slope * y) * y

    def wetted_perimeter(self, y: float) -> float:
        """Wetted perimeter at depth ``y``, m."""
        return self.base_width + 2.0 * y * math.sqrt(1.0 + self.side_slope**2)

    def top_width(self, y: float) -> float:
        """Water-surface width at depth ``y``, m."""
        return self.base_width + 2.0 * self.side_slope * y

    def rise(self, offset: FloatArray) -> FloatArray:
        """Bed height above the thalweg at a lateral ``offset`` from the axis, m."""
        beyond = np.abs(offset) - 0.5 * self.base_width
        if self.side_slope == 0.0:
            return np.where(beyond <= 0.0, 0.0, self.bank_height)
        return np.clip(beyond / self.side_slope, 0.0, self.bank_height)


@dataclass(frozen=True)
class ChannelSolution:
    """Uniform flow of total discharge ``discharge`` (m3/s) along the axis."""

    section: Section
    discharge: float
    slope: float
    manning_n: float
    theta_deg: float
    xc: float
    yc: float
    plain_level: float = PLAIN_LEVEL
    conveyance: Conveyance = Conveyance.HYDRAULIC_RADIUS

    def _strip_integral(self, y: float) -> float:
        """Integral of ``h^(5/3)`` across the section at depth ``y``."""
        section = self.section
        rectangle = section.base_width * y**MANNING_DEPTH_POWER
        return rectangle + STRIP_SIDE_FACTOR * section.side_slope * y ** (MANNING_DEPTH_POWER + 1.0)

    def manning_discharge(self, y: float) -> float:
        """Discharge at depth ``y`` by the law selected in ``conveyance``, m3/s."""
        root_slope = math.sqrt(self.slope)
        if self.conveyance is Conveyance.STRIP:
            return root_slope * self._strip_integral(y) / self.manning_n
        area = self.section.area(y)
        radius = area / self.section.wetted_perimeter(y)
        return root_slope * area * radius**RADIUS_POWER / self.manning_n

    @cached_property
    def normal_depth(self) -> float:
        """Normal depth, m; raises if the flow would leave the banks."""
        top = self.section.bank_height
        if self.manning_discharge(top) <= self.discharge:
            raise ValueError(f"discharge {self.discharge} m3/s overtops the banks")
        return float(brentq(lambda y: self.manning_discharge(y) - self.discharge, SMALL_DEPTH, top))

    @property
    def froude(self) -> float:
        """Froude number of the section, on hydraulic depth."""
        y = self.normal_depth
        area = self.section.area(y)
        return self.discharge / area / math.sqrt(G * area / self.section.top_width(y))

    def _coordinates(self, x: FloatArray, y: FloatArray) -> tuple[FloatArray, FloatArray]:
        """Distance along the axis and lateral offset from it."""
        theta = math.radians(self.theta_deg)
        dx, dy = x - self.xc, y - self.yc
        return dx * math.cos(theta) + dy * math.sin(theta), -dx * math.sin(theta) + dy * math.cos(theta)

    def _thalweg(self, along: FloatArray) -> FloatArray:
        return self.plain_level - self.section.bank_height - self.slope * along

    def bed(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """Bed elevation, m."""
        along, offset = self._coordinates(x, y)
        return self._thalweg(along) + self.section.rise(offset)

    def water_surface(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """The uniform-flow surface, extended over the banks, m."""
        along, _ = self._coordinates(x, y)
        return self._thalweg(along) + self.normal_depth

    def state(self, x: FloatArray, y: FloatArray, t: float) -> State:
        """The steady state, at every time."""
        _, offset = self._coordinates(x, y)
        h = np.maximum(self.normal_depth - self.section.rise(offset), 0.0)
        q = self.discharge * h**MANNING_DEPTH_POWER / self._strip_integral(self.normal_depth)
        theta = math.radians(self.theta_deg)
        return State(h, q * math.cos(theta), q * math.sin(theta))


def default_section(shape: Shape) -> Section:
    """The default section of ``shape``."""
    if shape is Shape.RECTANGULAR:
        return Section(RECTANGULAR_WIDTH, 0.0, BANK_HEIGHT)
    return Section(TRAPEZOIDAL_WIDTH, TRAPEZOIDAL_SIDE_SLOPE, BANK_HEIGHT)


def build_channel(
    grid: UniformGrid,
    shape: Shape = Shape.RECTANGULAR,
    *,
    theta_deg: float = 0.0,
    discharge: float = DISCHARGE,
    slope: float = BED_SLOPE,
    manning_n: float = MANNING_N,
    section: Section | None = None,
    conveyance: Conveyance = Conveyance.HYDRAULIC_RADIUS,
) -> Case:
    """Uniform flow through the domain centre. All sides carry the exact state, since the axis meets them
    at any angle."""
    chosen = section or default_section(shape)
    solution = ChannelSolution(
        chosen, discharge, slope, manning_n, theta_deg, *grid.centre, conveyance=conveyance
    )
    y_n = solution.normal_depth
    mean_q = discharge / chosen.top_width(y_n)
    return Case(
        name=f"channel_{shape.name.lower()}_{theta_deg:g}deg",
        grid=grid,
        solution=solution,
        boundaries=Boundaries.uniform(EXACT),
        tolerance=Tolerance(
            depth_rmse=DEPTH_FRACTION * y_n,
            surface_rmse=DEPTH_FRACTION * y_n,
            discharge_rmse=DISCHARGE_FRACTION * mean_q,
        ),
        t_end=spinup_time(max(grid.length_x, grid.length_y), y_n),
        source=SOURCE,
        manning_n=manning_n,
        surface_fn=solution.water_surface,
    )


def build_all_angles(grid: UniformGrid, shape: Shape = Shape.RECTANGULAR) -> tuple[Case, ...]:
    """The same channel at every angle of the test."""
    return tuple(build_channel(grid, shape, theta_deg=angle) for angle in ANGLES_DEG)
