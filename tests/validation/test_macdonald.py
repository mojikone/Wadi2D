"""MacDonald: the bed solves the steady ODE for each prescribed depth; regimes and the jump are right."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.validation import BoundaryKind, UniformGrid
from wadi2d.validation._constants import G
from wadi2d.validation._hydraulics import critical_depth, friction_slope, froude, specific_force
from wadi2d.validation.cases.macdonald import JUMP_POSITION, Variant, build_macdonald

LENGTH = 1000.0
GRID = UniformGrid(0.0, 0.0, 5.0, 200, 3)
STEP = 0.05
JUMP_CLEARANCE = 1.0
"""Distance kept from the jump when differencing across it would mean nothing, m."""


def _sample_points(variant: Variant) -> np.ndarray:
    s = np.linspace(1.0, LENGTH - 1.0, 2001)
    if variant is Variant.JUMP:
        s = s[np.abs(s - JUMP_POSITION * LENGTH) > JUMP_CLEARANCE]
    return s


@pytest.mark.parametrize("variant", list(Variant))
def test_bed_satisfies_the_steady_momentum_equation(variant) -> None:
    case = build_macdonald(GRID, variant)
    solution = case.solution
    s = _sample_points(variant)
    zero = np.zeros_like(s)
    h = solution.depth(s)
    dz = (solution.bed(s + STEP, zero) - solution.bed(s - STEP, zero)) / (2.0 * STEP)
    dh = (solution.depth(s + STEP) - solution.depth(s - STEP)) / (2.0 * STEP)
    q = solution.q
    residual = (1.0 - q * q / (G * h**3)) * dh + dz + friction_slope(q, h, solution.manning_n)
    assert np.max(np.abs(residual)) < 1e-6


@pytest.mark.parametrize("variant", list(Variant))
def test_bed_slope_formula_matches_the_differenced_bed(variant) -> None:
    solution = build_macdonald(GRID, variant).solution
    s = _sample_points(variant)
    zero = np.zeros_like(s)
    dz = (solution.bed(s + STEP, zero) - solution.bed(s - STEP, zero)) / (2.0 * STEP)
    assert np.allclose(dz, solution.bed_slope(s), atol=1e-6)


def test_regimes_are_what_the_variants_say() -> None:
    s = np.linspace(0.0, LENGTH, 1001)
    sub = build_macdonald(GRID, Variant.SUBCRITICAL).solution
    sup = build_macdonald(GRID, Variant.SUPERCRITICAL).solution
    assert np.all(froude(sub.q, sub.depth(s)) < 1.0)
    assert np.all(froude(sup.q, sup.depth(s)) > 1.0)


def test_jump_conserves_momentum_keeps_the_bed_continuous_and_changes_regime() -> None:
    solution = build_macdonald(GRID, Variant.JUMP).solution
    q = solution.q
    jump = JUMP_POSITION * LENGTH
    gap = 1e-7
    points = np.array([jump - gap, jump + gap])
    h_ahead, h_behind = solution.depth(points)
    assert specific_force(q, h_ahead) == pytest.approx(specific_force(q, h_behind), rel=1e-9)
    assert froude(q, h_ahead) > 1.0 > froude(q, h_behind)
    bed = solution.bed(points, np.zeros_like(points))
    assert bed[0] == pytest.approx(bed[1], abs=1e-5)


def test_jump_position_is_stable_both_ways() -> None:
    """A jump pushed downstream or upstream must meet a restoring force; a Lax jump alone is no proof."""
    solution = build_macdonald(GRID, Variant.JUMP).solution
    q, n = solution.q, solution.manning_n
    jump = JUMP_POSITION * LENGTH
    gap = 1e-7
    points = np.array([jump - gap, jump + gap])
    h1, h2 = solution.depth(points)
    slope1, slope2 = solution.depth_dx(points)
    fr1, fr2 = froude(q, h1) ** 2, froude(q, h2) ** 2
    friction_gap = friction_slope(q, h1, n) - friction_slope(q, h2, n)
    pushed_down = (h2 - h1) * (1.0 - fr2) * slope2 + h1 * friction_gap
    pushed_up = (h2 - h1) * (1.0 - fr1) * slope1 + h2 * friction_gap
    assert pushed_down > 0.0
    assert pushed_up > 0.0


def test_boundaries_match_the_regime() -> None:
    q = 2.0
    sub = build_macdonald(GRID, Variant.SUBCRITICAL).boundaries
    assert sub.west.kind is BoundaryKind.INFLOW
    assert sub.west.discharge == q
    assert sub.west.depth is None
    assert sub.east.kind is BoundaryKind.DEPTH
    sup = build_macdonald(GRID, Variant.SUPERCRITICAL).boundaries
    assert sup.west.depth is not None
    assert sup.east.kind is BoundaryKind.TRANSMISSIVE
    jump = build_macdonald(GRID, Variant.JUMP).boundaries
    assert jump.west.depth is not None
    assert jump.east.kind is BoundaryKind.DEPTH


def test_state_on_the_grid_carries_the_constant_discharge() -> None:
    case = build_macdonald(GRID, Variant.SUBCRITICAL)
    state = case.exact(0.0)
    assert state.h.shape == (GRID.ny, GRID.nx)
    assert np.all(state.qx == 2.0)
    assert np.all(state.qy == 0.0)
    assert np.min(state.h) > critical_depth(2.0)
    assert case.manning_n > 0.0
    assert np.ptp(case.bed(), axis=0).max() == 0.0


def test_origin_shifts_the_solution_with_the_grid() -> None:
    shifted = UniformGrid(500.0, 0.0, 5.0, 200, 3)
    plain, moved = (build_macdonald(g, Variant.JUMP) for g in (GRID, shifted))
    assert np.allclose(plain.bed(), moved.bed())
    assert np.allclose(plain.exact(0.0).h, moved.exact(0.0).h)
