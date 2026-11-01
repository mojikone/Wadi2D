"""Every case against its own exact state passes; a damaged state fails on the limit it broke."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from wadi2d.validation import Case, State, UniformGrid, compare
from wadi2d.validation.cases.channel_steady import Shape, build_all_angles
from wadi2d.validation.cases.dam_break import build_ritter, build_stoker
from wadi2d.validation.cases.lake_at_rest import build_bump, build_rough, build_slope
from wadi2d.validation.cases.macdonald import Variant, build_macdonald
from wadi2d.validation.cases.thacker import build_curved, build_planar
from wadi2d.validation.cases.weir import build_weir

CHANNEL_GRID = UniformGrid.square(400.0, 80)
LONG_GRID = UniformGrid(0.0, 0.0, 5.0, 200, 3)
BOWL_GRID = UniformGrid.square(4.0, 200)
FLUME_GRID = UniformGrid(0.0, 0.0, 1.0, 200, 3)
SAMPLED_VOLUME_ERROR = 2.0e-3


def _all_cases() -> list[Case]:
    return [
        build_bump(CHANNEL_GRID),
        build_rough(CHANNEL_GRID),
        build_slope(CHANNEL_GRID),
        build_planar(BOWL_GRID),
        build_curved(BOWL_GRID),
        build_stoker(LONG_GRID),
        build_ritter(LONG_GRID),
        build_macdonald(LONG_GRID, Variant.SUBCRITICAL),
        build_macdonald(LONG_GRID, Variant.SUPERCRITICAL),
        build_macdonald(LONG_GRID, Variant.JUMP),
        *build_all_angles(CHANNEL_GRID, Shape.RECTANGULAR),
        *build_all_angles(CHANNEL_GRID, Shape.TRAPEZOIDAL),
        build_weir(FLUME_GRID),
        build_weir(FLUME_GRID, tailwater=2.85),
    ]


CASES = _all_cases()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_every_case_has_the_full_contract(case) -> None:
    bed = case.bed()
    initial = case.initial()
    assert bed.shape == (case.grid.ny, case.grid.nx)
    assert initial.h.shape == bed.shape
    assert initial.qx.shape == bed.shape
    assert initial.qy.shape == bed.shape
    assert np.all(initial.h >= 0.0)
    assert case.t_end > 0.0
    assert case.source


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_exact_state_passes_with_zero_field_error(case) -> None:
    t = 0.6 * case.t_end
    # A field sampled at cell centres is not discretely conservative, so the volume limit is off here.
    unchecked = replace(case, tolerance=replace(case.tolerance, volume=None))
    report = compare(case.exact(t), unchecked, t)
    assert report.passed, report.failures
    assert abs(report.volume_error) < SAMPLED_VOLUME_ERROR
    assert report.depth_rmse == 0.0
    assert report.discharge_rmse == 0.0
    assert report.f_statistic == 1.0


def test_damaged_depth_fails_and_names_the_limit() -> None:
    case = build_planar(BOWL_GRID)
    t = 0.5
    exact = case.exact(t)
    report = compare(State(exact.h * 1.5, exact.qx, exact.qy), case, t)
    assert not report.passed
    assert any(message.startswith("depth_rmse") for message in report.failures)


def test_lost_water_fails_the_volume_check_in_a_closed_domain() -> None:
    case = build_bump(CHANNEL_GRID)
    exact = case.exact(0.0)
    report = compare(State(exact.h * 0.999, exact.qx, exact.qy), case, 0.0)
    assert report.volume_error == pytest.approx(-0.001, rel=1e-6)
    assert any(message.startswith("volume_error") for message in report.failures)


def test_false_flood_lowers_f() -> None:
    case = build_slope(CHANNEL_GRID)
    exact = case.exact(0.0)
    report = compare(State(np.full_like(exact.h, 0.5), exact.qx, exact.qy), case, 0.0)
    assert report.f_statistic < 1.0
    assert any(message.startswith("f_statistic") for message in report.failures)


def test_sub_grid_surface_is_compared_with_the_channel_surface() -> None:
    """A run that gives its own surface is judged on it, not on depth plus the bed at the centre."""
    case = build_all_angles(CHANNEL_GRID, Shape.RECTANGULAR)[1]
    exact = case.exact(0.0)
    wrong = case.surface(0.0) + 1.0
    assert compare(exact, case, 0.0, surface=case.surface(0.0)).surface_rmse == pytest.approx(0.0)
    report = compare(exact, case, 0.0, surface=wrong)
    assert report.surface_rmse == pytest.approx(1.0)
    assert any(message.startswith("surface_rmse") for message in report.failures)


def test_shape_mismatch_is_refused() -> None:
    case = build_bump(CHANNEL_GRID)
    other = build_bump(BOWL_GRID).exact(0.0)
    with pytest.raises(ValueError, match="does not match"):
        compare(other, case, 0.0)


def test_unchecked_limits_stay_unchecked() -> None:
    case = build_bump(CHANNEL_GRID)
    loose = replace(case, tolerance=replace(case.tolerance, depth_linf=None, volume=None, f_statistic=None))
    exact = case.exact(0.0)
    assert compare(State(exact.h + 0.1, exact.qx, exact.qy), loose, 0.0).passed
