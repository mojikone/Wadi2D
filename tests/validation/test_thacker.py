"""Thacker: the fields satisfy the equations when differenced; period and shoreline match closed forms."""

from __future__ import annotations

import math

import numpy as np
import pytest

from wadi2d.validation import UniformGrid
from wadi2d.validation._constants import G
from wadi2d.validation.cases.thacker import CurvedSolution, PlanarSolution, build_curved, build_planar

GRID = UniformGrid.square(4.0, 200)
PLANAR = build_planar(GRID)
CURVED = build_curved(GRID)
SPACE_STEP = 1.0e-4
TIME_STEP = 1.0e-4
INNER_DEPTH = 0.01
"""Differences are taken only this deep, so no stencil crosses the shoreline."""
TIMES = (0.0, 0.13, 0.41, 0.77)


def _shallow_water_residuals(solution, x, y, t) -> tuple:
    """Mass and x and y momentum residuals by central differences, in advective form."""
    d = SPACE_STEP
    dt = TIME_STEP

    def fields(xi, yi, ti):
        s = solution.state(xi, yi, ti)
        return s.h, s.qx, s.qy, s.qx / s.h, s.qy / s.h, s.h + solution.bed(xi, yi)

    here = fields(x, y, t)
    east, west = fields(x + d, y, t), fields(x - d, y, t)
    north, south = fields(x, y + d, t), fields(x, y - d, t)
    later, earlier = fields(x, y, t + dt), fields(x, y, t - dt)

    def ddx(i):
        return (east[i] - west[i]) / (2.0 * d)

    def ddy(i):
        return (north[i] - south[i]) / (2.0 * d)

    def ddt(i):
        return (later[i] - earlier[i]) / (2.0 * dt)

    u, v = here[3], here[4]
    mass = ddt(0) + ddx(1) + ddy(2)
    momentum_x = ddt(3) + u * ddx(3) + v * ddy(3) + G * ddx(5)
    momentum_y = ddt(4) + u * ddx(4) + v * ddy(4) + G * ddy(5)
    return mass, momentum_x, momentum_y


@pytest.mark.parametrize("case", [PLANAR, CURVED], ids=["planar", "curved"])
@pytest.mark.parametrize("t", TIMES)
def test_fields_satisfy_the_shallow_water_equations(case, t) -> None:
    x, y = case.grid.mesh()
    inner = case.exact(t).h > INNER_DEPTH
    assert inner.sum() > 1000
    mass, momentum_x, momentum_y = _shallow_water_residuals(case.solution, x[inner], y[inner], t)
    assert np.max(np.abs(mass)) < 1e-6
    assert np.max(np.abs(momentum_x)) < 1e-5
    assert np.max(np.abs(momentum_y)) < 1e-5


@pytest.mark.parametrize("case", [PLANAR, CURVED], ids=["planar", "curved"])
def test_state_repeats_after_one_period(case) -> None:
    start, after = case.exact(0.2), case.exact(0.2 + case.solution.period)
    assert np.allclose(start.h, after.h, atol=1e-10)
    assert np.allclose(start.qx, after.qx, atol=1e-10)


def test_periods_match_the_closed_forms() -> None:
    a, h0 = PLANAR.solution.radius, PLANAR.solution.centre_depth
    assert PLANAR.solution.period == pytest.approx(2.0 * math.pi * a / math.sqrt(2.0 * G * h0))
    assert CURVED.solution.period == pytest.approx(2.0 * math.pi * a / math.sqrt(8.0 * G * h0))


@pytest.mark.parametrize("t", TIMES)
def test_planar_shoreline_is_a_circle_of_the_bowl_radius(t) -> None:
    solution: PlanarSolution = PLANAR.solution
    cx, cy = solution.shoreline_centre(t)
    angles = np.linspace(0.0, 2.0 * math.pi, 73)
    radius = solution.radius
    on_circle = solution.state(cx + radius * np.cos(angles), cy + radius * np.sin(angles), t).h
    inside = solution.state(cx + 0.9 * radius * np.cos(angles), cy + 0.9 * radius * np.sin(angles), t).h
    outside = solution.state(cx + 1.1 * radius * np.cos(angles), cy + 1.1 * radius * np.sin(angles), t).h
    assert np.max(on_circle) == pytest.approx(0.0, abs=1e-12)
    assert np.all(inside > 0.0)
    assert np.all(outside == 0.0)


def test_planar_shoreline_moves_with_the_water() -> None:
    solution: PlanarSolution = PLANAR.solution
    t, dt = 0.3, 1e-5
    before, after = solution.shoreline_centre(t - dt), solution.shoreline_centre(t + dt)
    u, v = solution.velocity(t)
    assert (after[0] - before[0]) / (2.0 * dt) == pytest.approx(u, rel=1e-6)
    assert (after[1] - before[1]) / (2.0 * dt) == pytest.approx(v, rel=1e-6)


@pytest.mark.parametrize("t", TIMES)
def test_curved_shoreline_matches_the_closed_form(t) -> None:
    solution: CurvedSolution = CURVED.solution
    radius = solution.shoreline_radius(t)
    xc, yc = solution.xc, solution.yc
    assert solution.state(np.array([xc + radius]), np.array([yc]), t).h[0] == pytest.approx(0.0, abs=1e-12)
    assert solution.state(np.array([xc + 0.99 * radius]), np.array([yc]), t).h[0] > 0.0
    a = solution.amplitude
    expected = solution.radius * math.sqrt((1.0 - a * math.cos(solution.omega * t)) / math.sqrt(1.0 - a * a))
    assert radius == pytest.approx(expected)


def test_curved_depth_is_the_published_form() -> None:
    """The reduced depth of the module against the full SWASHES expression."""
    solution: CurvedSolution = CURVED.solution
    x, y = GRID.mesh()
    t = 0.37
    a, h0, big_a = solution.radius, solution.centre_depth, solution.amplitude
    r2 = (x - solution.xc) ** 2 + (y - solution.yc) ** 2
    denominator = 1.0 - big_a * math.cos(solution.omega * t)
    surface = h0 * (
        math.sqrt(1.0 - big_a**2) / denominator - 1.0 - r2 / a**2 * ((1.0 - big_a**2) / denominator**2 - 1.0)
    )
    published = np.maximum(surface - solution.bed(x, y), 0.0)
    assert np.allclose(solution.state(x, y, t).h, published, atol=1e-12)


@pytest.mark.parametrize("case", [PLANAR, CURVED], ids=["planar", "curved"])
def test_volume_is_constant_in_time(case) -> None:
    volumes = [float(np.sum(case.exact(t).h)) * case.grid.cell_area for t in TIMES]
    assert np.ptp(volumes) / volumes[0] < 1e-3


def test_a_bowl_that_leaves_the_domain_is_refused() -> None:
    with pytest.raises(ValueError, match="leaves the domain"):
        build_planar(UniformGrid.square(2.5, 50))
