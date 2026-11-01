"""Dam break: the Stoker star state against the jump conditions; Ritter front and head."""

from __future__ import annotations

import math

import numpy as np
import pytest

from wadi2d.validation import UniformGrid
from wadi2d.validation._constants import G
from wadi2d.validation.cases.dam_break import build_ritter, build_stoker, solve_star

H_LEFT, H_RIGHT = 2.0, 0.5
PAIRS = [(H_LEFT, H_RIGHT), (0.005, 0.001), (10.0, 0.05)]
GRID = UniformGrid(0.0, 0.0, 1.0, 1000, 5)


@pytest.mark.parametrize(("h_left", "h_right"), PAIRS)
def test_star_state_satisfies_rankine_hugoniot(h_left, h_right) -> None:
    star = solve_star(h_left, h_right)
    h, u, s = star.depth, star.velocity, star.shock_speed
    mass = s * (h - h_right) - h * u
    momentum = s * h * u - (h * u * u + 0.5 * G * (h * h - h_right * h_right))
    assert mass == pytest.approx(0.0, abs=1e-9 * h * u)
    assert momentum == pytest.approx(0.0, abs=1e-9 * h * u * u)


@pytest.mark.parametrize(("h_left", "h_right"), PAIRS)
def test_star_state_lies_on_the_riemann_invariant(h_left, h_right) -> None:
    star = solve_star(h_left, h_right)
    assert star.velocity + 2.0 * star.celerity == pytest.approx(2.0 * math.sqrt(G * h_left), rel=1e-12)


@pytest.mark.parametrize(("h_left", "h_right"), PAIRS)
def test_star_state_solves_the_swashes_polynomial(h_left, h_right) -> None:
    star = solve_star(h_left, h_right)
    cm2, gh = star.celerity**2, G * h_right
    left = 8.0 * gh * cm2 * (math.sqrt(G * h_left) - star.celerity) ** 2
    right = (cm2 - gh) ** 2 * (cm2 + gh)
    assert left == pytest.approx(right, rel=1e-8)


def test_stoker_profile_joins_its_pieces() -> None:
    solution = build_stoker(GRID).solution
    star = solution.star
    t = 40.0
    ahead = 1e-6

    def depth(position: float) -> float:
        x = np.array([position])
        return float(solution.state(x, np.zeros_like(x), t).h[0])

    assert depth(solution.head(t) - ahead) == pytest.approx(H_LEFT)
    assert depth(solution.head(t) + ahead) == pytest.approx(H_LEFT, rel=1e-5)
    assert depth(solution.tail(t) - ahead) == pytest.approx(star.depth, rel=1e-5)
    assert depth(solution.tail(t) + ahead) == pytest.approx(star.depth)
    assert depth(solution.shock(t) - ahead) == pytest.approx(star.depth)
    assert depth(solution.shock(t) + ahead) == pytest.approx(H_RIGHT)


@pytest.mark.parametrize("build", [build_stoker, build_ritter])
def test_volume_is_conserved_before_the_waves_reach_the_sides(build) -> None:
    case = build(GRID)
    start = float(np.sum(case.initial().h))
    assert float(np.sum(case.exact(case.t_end).h)) == pytest.approx(start, rel=1e-3)
    assert case.boundaries.is_closed


def test_ritter_front_and_head_positions() -> None:
    h_left = 3.0
    case = build_ritter(GRID, h_left=h_left, x0=400.0)
    solution = case.solution
    c0 = math.sqrt(G * h_left)
    t = 20.0
    assert solution.front(t) == pytest.approx(400.0 + 2.0 * c0 * t)
    assert solution.head(t) == pytest.approx(400.0 - c0 * t)
    x = np.array([solution.front(t) - 1e-3, solution.front(t) + 1e-3])
    h = solution.state(x, np.zeros_like(x), t).h
    assert h[0] > 0.0
    assert h[0] < 1e-7
    assert h[1] == 0.0


def test_ritter_velocity_at_the_dam_section_is_two_thirds_of_c0() -> None:
    """The critical section stays at the dam: h = 4 h0 / 9, u = 2 c0 / 3."""
    h_left = 2.0
    solution = build_ritter(GRID, h_left=h_left, x0=500.0).solution
    x = np.array([500.0])
    state = solution.state(x, np.zeros_like(x), 15.0)
    c0 = math.sqrt(G * h_left)
    assert state.h[0] == pytest.approx(4.0 * h_left / 9.0)
    assert state.qx[0] / state.h[0] == pytest.approx(2.0 * c0 / 3.0)


@pytest.mark.parametrize("build", [build_stoker, build_ritter])
def test_axis_y_is_the_transpose_of_axis_x(build) -> None:
    along_x = build(UniformGrid(0.0, 0.0, 1.0, 400, 6))
    along_y = build(UniformGrid(0.0, 0.0, 1.0, 6, 400), axis="y")
    t = 0.5 * along_x.t_end
    x_state, y_state = along_x.exact(t), along_y.exact(t)
    assert np.allclose(x_state.h, y_state.h.T)
    assert np.allclose(x_state.qx, y_state.qy.T)
    assert np.all(y_state.qx == 0.0)


def test_end_time_stops_before_the_sides() -> None:
    case = build_stoker(GRID)
    solution = case.solution
    assert solution.shock(case.t_end) < GRID.length_x
    assert solution.head(case.t_end) > 0.0
