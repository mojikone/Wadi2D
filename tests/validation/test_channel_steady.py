"""Rotated channel: normal depth satisfies Manning, and the geometry does not depend on the angle."""

from __future__ import annotations

import math

import numpy as np
import pytest

from wadi2d.validation import BoundaryKind, UniformGrid
from wadi2d.validation.cases.channel_steady import (
    ANGLES_DEG,
    BED_SLOPE,
    DISCHARGE,
    MANNING_N,
    Conveyance,
    Section,
    Shape,
    build_all_angles,
    build_channel,
    default_section,
)
from wadi2d.validation.cases.lake_at_rest import sample_bed

GRID = UniformGrid.square(400.0, 80)
LINE_POINTS = 20001


def _across(solution, half_width: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Points on a line through the centre, normal to the axis, and the lateral offset of each."""
    theta = math.radians(solution.theta_deg)
    offset = np.linspace(-half_width, half_width, LINE_POINTS)
    return solution.xc - offset * math.sin(theta), solution.yc + offset * math.cos(theta), offset


@pytest.mark.parametrize("shape", list(Shape))
def test_normal_depth_satisfies_manning(shape) -> None:
    solution = build_channel(GRID, shape).solution
    section: Section = solution.section
    y = solution.normal_depth
    area = section.area(y)
    radius = area / section.wetted_perimeter(y)
    manning = area * radius ** (2.0 / 3.0) * math.sqrt(BED_SLOPE) / MANNING_N
    assert manning == pytest.approx(DISCHARGE, rel=1e-9)
    assert solution.froude < 1.0


@pytest.mark.parametrize("shape", list(Shape))
def test_strip_normal_depth_satisfies_the_integrated_law_and_is_shallower(shape) -> None:
    strip = build_channel(GRID, shape, conveyance=Conveyance.STRIP).solution
    textbook = build_channel(GRID, shape).solution
    x, y, offset = _across(strip, 60.0)
    h = strip.state(x, y, 0.0).h
    integrated = np.trapezoid(h ** (5.0 / 3.0), offset) * math.sqrt(BED_SLOPE) / MANNING_N
    assert integrated == pytest.approx(DISCHARGE, rel=1e-4)
    assert strip.normal_depth < textbook.normal_depth


@pytest.mark.parametrize("shape", list(Shape))
@pytest.mark.parametrize("theta", ANGLES_DEG)
def test_field_integrates_to_the_discharge_at_every_angle(shape, theta) -> None:
    solution = build_channel(GRID, shape, theta_deg=theta).solution
    x, y, offset = _across(solution, 60.0)
    state = solution.state(x, y, 0.0)
    radians = math.radians(theta)
    along = state.qx * math.cos(radians) + state.qy * math.sin(radians)
    across = -state.qx * math.sin(radians) + state.qy * math.cos(radians)
    assert np.trapezoid(along, offset) == pytest.approx(DISCHARGE, rel=1e-4)
    assert np.max(np.abs(across)) < 1e-12


@pytest.mark.parametrize("shape", list(Shape))
def test_section_does_not_change_with_the_angle(shape) -> None:
    profiles = []
    for case in build_all_angles(GRID, shape):
        x, y, _ = _across(case.solution, 60.0)
        profiles.append(case.solution.bed(x, y))
    for profile in profiles[1:]:
        assert np.allclose(profile, profiles[0])


@pytest.mark.parametrize("theta", ANGLES_DEG)
def test_bed_falls_along_the_axis_at_the_channel_slope(theta) -> None:
    solution = build_channel(GRID, Shape.TRAPEZOIDAL, theta_deg=theta).solution
    radians = math.radians(theta)
    distance = 50.0
    points_x = np.array([solution.xc, solution.xc + distance * math.cos(radians)])
    points_y = np.array([solution.yc, solution.yc + distance * math.sin(radians)])
    fall = solution.bed(points_x, points_y)
    assert fall[0] - fall[1] == pytest.approx(BED_SLOPE * distance)


def test_wet_plan_area_matches_top_width_times_length_when_resolved() -> None:
    """At 45 degrees on a fine grid, counted wet cells give the section top width."""
    grid = UniformGrid.square(400.0, 800)
    case = build_channel(grid, Shape.TRAPEZOIDAL, theta_deg=45.0)
    solution = case.solution
    x, y = grid.mesh()
    theta = math.radians(45.0)
    along = np.abs((x - solution.xc) * math.cos(theta) + (y - solution.yc) * math.sin(theta))
    window = along < 100.0
    wet_area = np.count_nonzero((case.exact(0.0).h > 0.0) & window) * grid.cell_area
    top_width = solution.section.top_width(solution.normal_depth)
    assert wet_area == pytest.approx(top_width * 200.0, rel=0.02)


def test_plain_stays_dry_and_every_side_takes_the_exact_state() -> None:
    case = build_channel(GRID, theta_deg=30.0)
    state = case.exact(0.0)
    assert np.all(state.h[case.bed() > case.surface(0.0)] == 0.0)
    assert case.boundaries.west.kind is BoundaryKind.EXACT
    assert case.boundaries.north.kind is BoundaryKind.EXACT


def test_sub_cell_samples_keep_the_channel_a_coarse_centre_would_miss() -> None:
    """Cells wider than the channel: the sub-grid sampler still sees its thalweg."""
    coarse = UniformGrid.square(400.0, 8)
    case = build_channel(coarse, theta_deg=30.0)
    samples = sample_bed(case.solution.bed, coarse, 20)
    depth_below_plain = samples.max(axis=(2, 3)) - samples.min(axis=(2, 3))
    assert depth_below_plain.max() > default_section(Shape.RECTANGULAR).bank_height


def test_flow_over_the_banks_is_refused() -> None:
    with pytest.raises(ValueError, match="overtops"):
        build_channel(GRID, discharge=1.0e4)
