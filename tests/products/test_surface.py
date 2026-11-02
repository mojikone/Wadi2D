"""The sloped water surface. The pass marks are the freeboard cases of W2's s09b_freeboard.py, fixed in the brief."""

from __future__ import annotations

import numpy as np
import pytest

from tests.products.conftest import channel_case, marks, surface_of
from wadi2d.products.surface import (
    Neighbours,
    corner_basis,
    corner_groups,
    corner_means,
    face_links,
    fill_cells,
)


class Rolled:
    """Neighbours on a whole small grid, for reading the rules by hand."""

    xp = np

    @staticmethod
    def at(a, dj: int, di: int):
        return np.roll(a, (-dj, -di), axis=(0, 1))


HALF_CELL_LESS_HALF_PIXEL = 12.5
"""Largest distance from a pixel centre to the centre of its 30 m cell along the channel, m."""


@pytest.mark.parametrize("slope", [0.01, 0.05, 0.10])
@pytest.mark.parametrize("level_of", ["level", "fill_level"])
def test_pass_mark_no_false_bank_and_half_the_flat_error(slope: float, level_of: str) -> None:
    flat_error = HALF_CELL_LESS_HALF_PIXEL * slope
    case = channel_case(slope, 1.5 * flat_error)
    flat = marks(case, surface_of(case, case.level, flat=True))
    sloped = marks(case, surface_of(case, getattr(case, level_of)))
    assert flat["surface_error_m"] == pytest.approx(flat_error, rel=0.1)
    assert sloped["false_bank_pct"] == 0.0
    assert sloped["surface_error_m"] <= 0.5 * flat_error


def test_ten_percent_is_followed_though_the_step_between_cells_is_three_metres() -> None:
    case = channel_case(0.10, 1.875)
    sloped = marks(case, surface_of(case, case.level))
    assert sloped["surface_error_m"] < 0.05


def links(level, depth, sill, wet=None, axis=1):
    level = np.asarray(level, np.float32)
    depth = np.asarray(depth, np.float32)
    wet = depth > 0.0 if wet is None else wet
    return face_links(Rolled, level, depth, wet, np.asarray(sill, np.float32), axis, 0.01, 0.5)


def test_water_either_side_above_the_face_is_one_body() -> None:
    assert links([[100.0, 100.2]], [[2.0, 0.3]], [[0.0, 99.0]])[0, 1]


def test_a_steep_step_of_like_depths_is_one_flow() -> None:
    """3 m between cells, 1 m deep: the lower level is under the face, and the flow still crosses it."""
    assert links([[100.0, 97.0]], [[1.0, 1.0]], [[0.0, 97.5]])[0, 1]


def test_a_bank_above_a_wet_neighbour_is_not_joined() -> None:
    """The film on the bank reaches the face, but it is not the deep channel's surface."""
    assert not links([[100.0, 102.6]], [[2.0, 0.2]], [[0.0, 102.5]])[0, 1]


def test_water_below_the_face_on_both_sides_is_not_joined() -> None:
    assert not links([[100.0, 100.5]], [[2.0, 2.0]], [[0.0, 101.0]])[0, 1]


def test_a_dry_neighbour_and_a_closed_face_are_not_joined() -> None:
    assert not links([[100.0, 100.0]], [[2.0, 0.0]], [[0.0, 90.0]])[0, 1]
    assert not links([[100.0, 100.0]], [[2.0, 2.0]], [[0.0, np.inf]])[0, 1]


def test_a_bank_standing_above_a_neighbouring_wet_cell_stays_dry() -> None:
    """A cell of deep channel beside a cell of bank with a film on it: the channel's level must not climb the bank."""
    k = 6
    ground = np.full((1, k * k), 100.0, np.float32)  # channel pixels, west half of the cell
    ground[:, np.arange(k * k) % k >= 3] = 103.0  # bank pixels, east half
    level = np.array([[0.0, 102.0, 103.2, 0.0]], np.float32)  # channel, bank film
    depth = np.array([[0.0, 2.0, 0.2, 0.0]], np.float32)
    sill = np.array([[0.0, 0.0, 103.1, 0.0]], np.float32)
    wet = depth > 0.0
    lx = face_links(Rolled, level, depth, wet, sill, 1, 0.01, 0.5)
    none = np.zeros_like(lx)
    groups = corner_groups(Rolled, lx, none)
    corners = corner_means(Rolled, level, wet, groups)
    surface = np.stack([c[0, 1:2] for c in corners], axis=1) @ corner_basis(np, k).T
    pixel_depth = fill_cells(np, surface, ground, np.array([1.0], np.float32))
    assert not lx.any()
    assert pixel_depth[0, np.arange(k * k) % k >= 3].max() == 0.0


def test_corners_mean_only_what_is_joined() -> None:
    """Four wet cells in a square, the south-west one cut off: the other three share their corner."""
    level = np.zeros((4, 4), np.float32)
    level[1:3, 1:3] = [[10.0, 11.0], [20.0, 12.0]]
    wet = level > 0.0
    lx = np.zeros((4, 4), bool)
    ly = np.zeros((4, 4), bool)
    lx[1, 2] = True  # (1, 1) with (1, 2)
    ly[2, 2] = True  # (1, 2) with (2, 2)
    corners = corner_means(Rolled, level, wet, corner_groups(Rolled, lx, ly))
    south_east_of_nw, south_west_of_ne, north_west_of_se = corners[3][1, 1], corners[2][1, 2], corners[0][2, 2]
    assert south_east_of_nw == pytest.approx(11.0)  # through (1, 2) to (2, 2)
    assert south_west_of_ne == pytest.approx(11.0)
    assert north_west_of_se == pytest.approx(11.0)
    assert corners[1][2, 1] == pytest.approx(20.0)  # the cut-off cell keeps its own level


def test_corner_basis_sums_to_one_and_runs_south_east() -> None:
    basis = corner_basis(np, 4)
    assert np.allclose(basis.sum(axis=1), 1.0)
    assert basis[0, 0] > basis[0, 3]  # the first pixel leans on the north-west corner
    assert basis[-1, 3] > basis[-1, 0]


def test_fill_holds_the_water_of_the_cell_on_any_shape() -> None:
    rng = np.random.default_rng(3)
    ground = rng.uniform(0.0, 3.0, (200, 36)).astype(np.float32)
    surface = rng.uniform(0.0, 1.0, (200, 36)).astype(np.float32)
    water = rng.uniform(0.001, 2.0, 200).astype(np.float32)
    depth = fill_cells(np, surface, ground, water)
    assert np.allclose(depth.mean(axis=1), water, atol=1e-4)


def test_a_thin_sheet_on_a_plane_reads_its_own_depth_not_a_wedge() -> None:
    """A flat fill puts all of it in the low corner; the surface parallel to the ground gives it back evenly."""
    k = 6
    drop = 0.5 * (np.arange(k) + 0.5)  # 3 m over the cell
    ground = np.tile(10.0 - drop, (1, k, 1)).reshape(1, k * k).astype(np.float32)
    flat = fill_cells(np, np.zeros_like(ground), ground, np.array([0.1], np.float32))
    parallel = fill_cells(np, ground - 0.3, ground, np.array([0.1], np.float32))
    assert flat.max() > 0.5
    assert parallel.max() == pytest.approx(0.1, abs=1e-5)


def test_the_flat_list_of_cells_reads_the_same_as_the_grid() -> None:
    rng = np.random.default_rng(2)
    keep = np.zeros((12, 14), bool)
    keep[2:10, 3:12] = rng.random((8, 9)) > 0.2
    level = rng.uniform(10.0, 11.0, keep.shape).astype(np.float32) * keep
    depth = rng.uniform(0.2, 2.0, keep.shape).astype(np.float32) * keep
    sill = rng.uniform(9.0, 12.0, keep.shape).astype(np.float32)
    wet = depth > 0.0

    def means(near, cut):
        lx = face_links(near, cut(level), cut(depth), cut(wet), cut(sill), 1, 0.01, 0.5)
        ly = face_links(near, cut(level), cut(depth), cut(wet), cut(sill), 0, 0.01, 0.5)
        return corner_means(near, cut(level), cut(wet), corner_groups(near, lx, ly))

    grid = means(Rolled, lambda a: a)

    def flat(a):
        return np.append(a[keep], 0).astype(a.dtype)

    listed = means(Neighbours(np, keep), flat)
    for one, other in zip(grid, listed, strict=True):
        np.testing.assert_allclose(one[keep], other[:-1], rtol=1e-6)
