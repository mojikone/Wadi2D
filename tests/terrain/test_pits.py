"""Pits of the ground as the cells hold it (W85): found by depth and plan area, filled as terrain objects."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.config.schema import FILL_KIND, PIT_FILL_NAME, Tables, Terrain, TerrainObject
from wadi2d.grid import TileGrid
from wadi2d.tables import ArrayBed, build_tables
from wadi2d.terrain import Ground, apply_objects
from wadi2d.terrain.pits import fill_objects, find_pits, without_fills

DX, K = 10.0, 10
PIXEL = DX / K
SLOPE = 0.01
PJ, PI = 6, 7
"""The pit lies in row PJ of cells, a pixel either side of the west face of column PI."""
DEEP = 30.0


def grid_and_plane() -> tuple[TileGrid, np.ndarray]:
    """A plane falling east at 1 %: every cell drains over its east face, so it holds no sink of its own."""
    grid = TileGrid.from_mask(np.ones((12, 20), bool), 0.0, 0.0, DX)
    ny, nx = grid.shape
    x = (np.arange(nx * K) + 0.5) * PIXEL
    return grid, np.tile(100.0 - SLOPE * x, (ny * K, 1))


def with_pit(z: np.ndarray, deep: float = DEEP) -> np.ndarray:
    """A hole 2 m by 6 m across one face."""
    out = z.copy()
    out[PJ * K + 2 : PJ * K + 8, PI * K - 1 : PI * K + 1] -= deep
    return out


def tables_of(grid, z, edit=None):
    return build_tables(grid, ArrayBed(z, PIXEL), Tables(), 0.03, edit=edit, workers=1)


def test_a_hole_across_a_face_is_one_pit_of_two_cells():
    grid, plane = grid_and_plane()
    z = with_pit(plane)
    (pit,) = find_pits(tables_of(grid, z), Terrain())
    assert set(pit.cells) == {(PJ, PI - 1), (PJ, PI)}
    # the two cells spill over the east face of the lower one: the hole's rim there
    rim = float(plane[PJ * K, (PI + 1) * K - 1])
    assert pit.spill_m == pytest.approx(rim, abs=0.02)
    assert pit.bottom_m == pytest.approx(float(z.min()))
    assert pit.depth_m == pytest.approx(DEEP, abs=0.2)
    assert pit.area_m2 == pytest.approx(
        12.0, rel=0.5
    )  # 12 m2 of hole; the table reads a plan share between rows
    assert pit.volume_m3 == pytest.approx(12.0 * DEEP, rel=0.1)
    x, y = grid.xy_of(np.array(PJ), np.array(PI))
    assert pit.y == pytest.approx(float(y)) and pit.x in (
        pytest.approx(float(x)),
        pytest.approx(float(x) - DX),
    )


def test_a_plane_has_no_pit_and_a_shallow_hollow_is_not_one():
    grid, plane = grid_and_plane()
    assert find_pits(tables_of(grid, plane), Terrain()) == []
    assert find_pits(tables_of(grid, with_pit(plane, deep=3.0)), Terrain()) == []
    assert len(find_pits(tables_of(grid, with_pit(plane, deep=3.0)), Terrain(pit_min_depth=2.0))) == 1


def test_a_pond_large_in_plan_is_not_a_pit_however_deep_a_hole_in_it():
    """A bowl of six cells by six, 8 m deep, with a hole 20 m deeper in one cell: one sink, far over two cells of
    water surface. The hole is under the pond's level, not under a rim of its own."""
    grid, plane = grid_and_plane()
    z = plane.copy()
    z[3 * K : 9 * K, 4 * K : 10 * K] -= 8.0
    z[5 * K + 2 : 5 * K + 8, 6 * K + 2 : 6 * K + 8] -= 20.0
    assert find_pits(tables_of(grid, z), Terrain()) == []
    (pond,) = find_pits(tables_of(grid, z), Terrain(pit_max_cells=100.0))
    assert len(pond.cells) == 36 and pond.depth_m == pytest.approx(28.0, abs=0.5)  # to the rim's lowest face


def test_the_fills_raise_the_hole_to_its_rim_and_nothing_else():
    grid, plane = grid_and_plane()
    z = with_pit(plane)
    tables = tables_of(grid, z)
    pits = find_pits(tables, Terrain())
    fills = fill_objects(pits, tables)
    assert [f.kind for f in fills] == [FILL_KIND, FILL_KIND] and all(
        f.name.startswith(PIT_FILL_NAME) for f in fills
    )
    edit = apply_objects(grid, fills, PIXEL, Terrain(), Ground(ArrayBed(z, PIXEL), grid.x0, grid.y0)).edit
    whole = z.copy()
    edit(whole, 0, 0)
    hole = whole != z
    assert hole.sum() == 12 and np.array_equal(hole, z < plane - 1.0)
    assert np.all(whole[hole] <= pits[0].spill_m) and np.all(whole[hole] > pits[0].spill_m - 1e-4)
    assert np.all(whole[hole] == np.float32(whole[hole]))  # float32, as a DEM's pixels are
    # the same pixels through another window: an edit must not depend on the window it is asked through
    r0, c0 = PJ * K - 7, PI * K - 13
    part = z[r0 : r0 + 31, c0 : c0 + 29].copy()
    edit(part, r0, c0)
    assert np.array_equal(part, whole[r0 : r0 + 31, c0 : c0 + 29])


def test_tables_built_on_the_filled_ground_hold_no_pit_and_the_cells_away_from_it_are_the_same():
    grid, plane = grid_and_plane()
    z = with_pit(plane)
    before = tables_of(grid, z)
    fills = fill_objects(find_pits(before, Terrain()), before)
    edit = apply_objects(grid, fills, PIXEL, Terrain(), Ground(ArrayBed(z, PIXEL), grid.x0, grid.y0)).edit
    after = tables_of(grid, z, edit)
    assert find_pits(after, Terrain()) == []
    away = np.ones(grid.shape, bool)
    away[PJ, PI - 1 : PI + 1] = False
    for name in ("zmin", "zbar"):
        assert np.array_equal(getattr(before, name)[away], getattr(after, name)[away]), name
    for name in ("hc", "dtab"):
        a, b = grid.from_tiles(getattr(before, name)), grid.from_tiles(getattr(after, name))
        assert np.array_equal(a[away], b[away]), name
    assert after.zmin[PJ, PI] == pytest.approx(find_pits(before, Terrain())[0].spill_m, abs=1e-4)


def test_resolving_twice_gives_the_same_objects():
    grid, plane = grid_and_plane()
    tables = tables_of(grid, with_pit(plane))
    fills = fill_objects(find_pits(tables, Terrain()), tables)
    wall = TerrainObject(kind="wall", coordinates=[(0.0, -5.0), (30.0, -5.0)])
    by_hand = TerrainObject(kind="fill", name="yard", coordinates=[(0, 0), (5, 0), (5, -5)], z_constant=101.0)
    assert without_fills([wall, *fills, by_hand]) == [wall, by_hand]


def test_a_fill_needs_an_outline_and_a_level():
    with pytest.raises(ValueError, match="fill needs"):
        TerrainObject(kind="fill", coordinates=[(0, 0), (5, 0)], z_constant=1.0)
    with pytest.raises(ValueError, match="fill needs"):
        TerrainObject(kind="fill", coordinates=[(0, 0), (5, 0), (5, 5)])
