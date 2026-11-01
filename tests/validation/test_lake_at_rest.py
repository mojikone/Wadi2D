"""Lake at rest: flat surface, no flow, reproducible beds, and the sub-cell sampler."""

from __future__ import annotations

import math

import numpy as np
import pytest

from wadi2d.validation import UniformGrid
from wadi2d.validation.cases.lake_at_rest import (
    RoughBed,
    build_bump,
    build_rough,
    build_slope,
    sample_bed,
)

GRID = UniformGrid.square(100.0, 50)


@pytest.mark.parametrize("build", [build_bump, build_rough, build_slope])
def test_surface_is_flat_and_still(build) -> None:
    case = build(GRID)
    state = case.exact(case.t_end)
    wet = state.h > 0.0
    assert wet.any()
    assert np.ptp((state.h + case.bed())[wet]) == pytest.approx(0.0, abs=1e-12)
    assert np.all(state.qx == 0.0) and np.all(state.qy == 0.0)
    assert case.boundaries.is_closed


def test_slope_has_its_shoreline_in_the_domain() -> None:
    case = build_slope(GRID, slope=0.1)
    x, _ = GRID.mesh()
    h = case.initial().h
    assert np.all(h[x < 50.0] > 0.0)
    assert np.all(h[x > 50.0] == 0.0)
    assert np.allclose(h, np.maximum(0.1 * (50.0 - x), 0.0))


def test_emerged_bump_leaves_a_dry_island() -> None:
    case = build_bump(GRID, eta=0.3, amplitude=0.5)
    h = case.initial().h
    assert h[25, 25] == 0.0
    assert h[0, 0] == pytest.approx(0.3, rel=1e-3)


def test_rough_bed_is_reproducible_and_seed_dependent() -> None:
    x, y = GRID.mesh()
    first, again, other = (RoughBed(0.5, 5.0, seed)(x, y) for seed in (1, 1, 2))
    assert np.array_equal(first, again)
    assert not np.array_equal(first, other)


def test_rough_bed_has_the_asked_amplitude_and_correlation_length() -> None:
    length = 5.0
    bed = RoughBed(0.5, length, seed=3, n_modes=2048)
    grid = UniformGrid(0.0, 0.0, 1.0, 1024, 1024)
    z = bed(*grid.mesh())
    assert np.std(z) == pytest.approx(0.5, rel=0.1)
    lag = int(length / grid.dx)
    correlation = np.mean(z[:, :-lag] * z[:, lag:]) / np.mean(z * z)
    assert correlation == pytest.approx(math.exp(-0.5), abs=0.1)


def test_sample_bed_shape_and_position() -> None:
    grid = UniformGrid(10.0, 20.0, 2.0, 3, 4)

    def plane(x, y):
        return 3.0 * x + 7.0 * y

    k = 4
    samples = sample_bed(plane, grid, k)
    assert samples.shape == (grid.ny, grid.nx, k, k)
    assert np.allclose(samples.mean(axis=(2, 3)), plane(*grid.mesh()))
    step = grid.dx / k
    assert samples[0, 0, 0, 0] == pytest.approx(plane(10.0 + 0.5 * step, 20.0 + 0.5 * step))
    assert samples[0, 0, 0, 1] - samples[0, 0, 0, 0] == pytest.approx(3.0 * step)
    assert samples[0, 0, 1, 0] - samples[0, 0, 0, 0] == pytest.approx(7.0 * step)


def test_flip_y_reverses_the_rows_and_nothing_else() -> None:
    grid = UniformGrid(0.0, 0.0, 2.0, 25, 40)
    flipped = UniformGrid(0.0, 0.0, 2.0, 25, 40, flip_y=True)
    plain, turned = (build_rough(g, seed=4).bed() for g in (grid, flipped))
    assert np.array_equal(plain, turned[::-1, :])
