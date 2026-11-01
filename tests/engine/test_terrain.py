"""RasterBed windows and the face lattice, without running the solver."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, tilted_box, write_dem
from wadi2d.config.schema import Tables, TerrainObject
from wadi2d.grid import TileGrid
from wadi2d.solver.layout import CLOSED
from wadi2d.tables import build_tables
from wadi2d.terrain import RasterBed, apply_objects
from wadi2d.terrain.crest import NORTH, WEST, staircase


def grid_of(nx: int, ny: int, dx: float) -> TileGrid:
    return TileGrid.from_mask(np.ones((ny, nx), bool), X0, Y0, dx)


def test_window_reads_the_right_pixels(tmp_path):
    z = np.arange(100 * 100, dtype=np.float64).reshape(100, 100)
    with RasterBed(write_dem(tmp_path / "d.tif", z, 2.0)) as bed:
        w = bed.snap((X0 + 21.0, Y0 - 41.0, X0 + 60.0, Y0 - 3.0), 8.0)
        assert (w.x0, w.y0) == (X0 + 20.0, Y0 - 2.0)
        assert (w.nx, w.ny) == (5, 5)
        bed.bind(w.x0, w.y0)
        np.testing.assert_array_equal(bed.read(0, 0, 2, 3), z[1:3, 10:13])


def test_window_off_the_raster_takes_nearest_pixels(tmp_path):
    z = np.arange(64.0).reshape(8, 8)
    with RasterBed(write_dem(tmp_path / "d.tif", z, 1.0)) as bed:
        bed.bind(X0, Y0)
        a = bed.read(-2, -2, 4, 4)
    assert a[0, 0] == z[0, 0]
    assert a[3, 3] == z[1, 1]


def test_nodata_cells_are_inactive_and_filled(tmp_path):
    z = tilted_box(40, 40, 1.0, 0.01)
    z[:, 20:] = np.nan
    with RasterBed(write_dem(tmp_path / "d.tif", z, 1.0)) as bed:
        w = bed.snap((X0, Y0 - 40.0, X0 + 40.0, Y0), 4.0)
        mask = bed.active_mask(w, 4.0)
        bed.bind(w.x0, w.y0)
        a = bed.read(0, 18, 4, 4)
    assert mask[:, :5].all()
    assert not mask[:, 5:].any()
    assert np.isfinite(a).all()
    assert a.max() < 1e6


def test_a_cell_size_off_the_pixel_is_an_error(tmp_path):
    with (
        RasterBed(write_dem(tmp_path / "d.tif", tilted_box(16, 16, 2.0, 0.0), 2.0)) as bed,
        pytest.raises(ValueError, match="not a multiple"),
    ):
        bed.snap(None, 5.0)
    with RasterBed(write_dem(tmp_path / "e.tif", tilted_box(16, 16, 2.0, 0.0), 2.0), pixel_stride=3) as bed:
        assert bed.pixel == 6.0
        with pytest.raises(ValueError, match="not a multiple"):
            bed.snap(None, 8.0)
        assert bed.snap(None, 12.0).nx == 3


def test_pixel_stride_reads_one_pixel_in_each_block(tmp_path):
    z = np.arange(1600.0).reshape(40, 40)
    with RasterBed(write_dem(tmp_path / "d.tif", z, 1.0), pixel_stride=4) as bed:
        bed.bind(X0, Y0)
        a = bed.read(1, 2, 3, 3)
    for r in range(3):
        for c in range(3):
            row = (1 + r) * 4
            col = (2 + c) * 4
            assert z[row, col] <= a[r, c] <= z[row + 3, col + 3]
            assert a[r, c] in z[row : row + 4, col : col + 4]


def test_staircase_is_four_connected_and_stays_near_the_line():
    grid = grid_of(62, 62, 10.0)
    a = (X0 + 44.0, Y0 - 84.0)
    b = (X0 + 394.0, Y0 - 254.0)
    st = staircase(grid, [a, b])
    assert st.size == 35 + 17
    ends = []
    for ax, j, i in zip(st.axis, st.j, st.i, strict=True):
        ends.append(((j, i), (j, i + 1)) if ax == NORTH else ((j, i), (j + 1, i)))
    for (p0, p1), (q0, q1) in itertools.pairwise(ends):
        assert {p0, p1} & {q0, q1}, "edges must share a corner"
    length = np.hypot(350.0, 170.0)
    assert st.factor[0] == pytest.approx(length / (st.size * 10.0))
    assert (st.axis == WEST).sum() == 17


def test_crest_line_factor_and_elevation_interpolated():
    grid = grid_of(30, 30, 10.0)
    obj = TerrainObject(
        kind="crest_line", coordinates=[(X0 + 100.0, Y0 - 100.0), (X0 + 200.0, Y0 - 200.0)], z=[10.0, 20.0]
    )
    crest = apply_objects(grid, [obj], 2.0).crest
    faces = np.isfinite(crest.xz).sum() + np.isfinite(crest.yz).sum()
    assert faces == 20
    assert crest.xlen[np.isfinite(crest.xz)] == pytest.approx(np.sqrt(2.0) / 2.0)
    values = np.concatenate((crest.xz[np.isfinite(crest.xz)], crest.yz[np.isfinite(crest.yz)]))
    assert values.min() > 10.0
    assert values.max() < 20.0
    assert sorted(values)[10] == pytest.approx(15.0, abs=1.0)


def test_spillway_lengths_add_up_to_its_length():
    grid = grid_of(30, 30, 10.0)
    obj = TerrainObject(
        kind="spillway",
        coordinates=[(X0 + 100.0, Y0 - 100.0), (X0 + 100.0, Y0 - 170.0)],
        z_constant=5.0,
        coefficient=2.1,
        length=72.0,
    )
    crest = apply_objects(grid, [obj], 2.0).crest
    on = np.isfinite(crest.xz)
    assert on.sum() == 7
    assert (crest.xlen[on] * 10.0).sum() == pytest.approx(72.0)
    assert (crest.xc[on] == 2.1).all()


def test_spillway_takes_the_dam_faces_it_lies_on():
    grid = grid_of(30, 30, 10.0)
    dam = TerrainObject(
        kind="crest_line", coordinates=[(X0 + 104.0, Y0 - 60.0), (X0 + 116.0, Y0 - 260.0)], z_constant=10.0
    )
    sp = TerrainObject(
        kind="spillway", coordinates=[(X0 + 108.0, Y0 - 130.0), (X0 + 112.0, Y0 - 190.0)], z_constant=8.0,
        coefficient=2.1, length=60.0,
    )  # fmt: skip
    crest = apply_objects(grid, [dam, sp], 2.0).crest
    spill = (crest.xc == 2.1) | (crest.yc == 2.1)
    dam_only = apply_objects(grid, [dam], 2.0).crest
    dam_faces = np.isfinite(dam_only.xz) | np.isfinite(dam_only.yz)
    assert spill.any()
    assert (spill <= dam_faces).all(), "a spillway must not leave the dam's own faces"


def test_wall_closes_faces_and_build_tables_keeps_them_closed():
    grid = grid_of(30, 30, 8.0)
    obj = TerrainObject(kind="wall", coordinates=[(X0 + 80.0, Y0 - 16.0), (X0 + 80.0, Y0 - 160.0)])
    edits = apply_objects(grid, [obj], 8.0)
    z = np.zeros((32, 32))
    from wadi2d.tables import ArrayBed

    tables = build_tables(grid, ArrayBed(z, 8.0), Tables(), 0.03, edits.crest, edits.edit)
    closed = grid.from_tiles(tables.flx) >= CLOSED
    assert closed[3:21, 11].all()
    assert not closed[3:21, 10].any()


def test_burn_line_cuts_the_pixels_it_crosses():
    grid = grid_of(30, 30, 8.0)
    obj = TerrainObject(
        kind="burn_line", coordinates=[(X0, Y0 - 80.0), (X0 + 200.0, Y0 - 80.0)], width=8.0, depth=3.0
    )
    edit = apply_objects(grid, [obj], 2.0).edit
    z = np.full((64, 64), 50.0)
    edit(z, 0, 0)
    assert z.min() == pytest.approx(47.0)
    r = int((grid.y0 - (Y0 - 80.0)) // 2.0)
    assert z[r, 20] == pytest.approx(47.0)
    assert z[r + 10, 20] == pytest.approx(50.0)


def test_objects_need_their_heights():
    with pytest.raises(ValueError, match="z or z_constant"):
        TerrainObject(kind="crest_line", coordinates=[(0.0, 0.0), (1.0, 1.0)])
    with pytest.raises(ValueError, match="one elevation per vertex"):
        TerrainObject(kind="crest_line", coordinates=[(0.0, 0.0), (1.0, 1.0)], z=[1.0])
