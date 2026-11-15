"""W50: the kept cells' ground read tile by tile on threads is the ground the whole-strip read gave, pixel for pixel,
holes and their fill included."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from tests.engine.conftest import job, write_dem
from wadi2d.products import ground as ground_mod
from wadi2d.products.ground import CellReader, read_cells
from wadi2d.run import prepare_grid
from wadi2d.solver.layout import TILE

K, NX, NY = 4, 80, 70


@pytest.fixture(scope="module")
def holed(tmp_path_factory):
    """Ground with holes: scattered, in patches, at a strip's edge; every cell's centre pixel holds data."""
    tmp = tmp_path_factory.mktemp("holed")
    rng = np.random.default_rng(7)
    z = 100.0 + rng.random((NY * K, NX * K)) * 3.0
    z[rng.random(z.shape) < 0.04] = np.nan
    z[20:60, 30:90] = np.nan  # a patch: its holes fill from the centre pixels kept below
    # along the line between two strips: neither may fill from the other
    z[TILE * K - 3 : TILE * K + 3, :] = np.nan
    z[:, -6:] = np.nan  # the east edge of the strips
    centre = (slice(K // 2, None, K), slice(K // 2, None, K))
    z[centre] = 100.0 + rng.random(z[centre].shape)
    dem = write_dem(tmp / "dem.tif", z, 0.5)
    cfg = job(dem, NX, NY, 2.0)
    tables, _crs = prepare_grid(cfg, tmp / "cache")
    keep = (rng.random(tables.grid.mask.shape) > 0.6) & tables.grid.mask
    keep[5:15, 7:23] = tables.grid.mask[5:15, 7:23]
    return cfg, tables, keep


def _whole(cfg, tables, keep, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(ground_mod._ThreadBeds, "pick", lambda *_a: False)
        return read_cells(cfg, tables, keep)


@pytest.mark.parametrize("margin", [ground_mod.FILL_MARGIN, 1])
def test_tiles_on_threads_read_what_the_whole_strips_read(holed, monkeypatch, margin) -> None:
    """With the margin as shipped the first read always suffices; with one pixel it grows, doubling, to the strip."""
    cfg, tables, keep = holed
    whole = _whole(cfg, tables, keep, monkeypatch)
    monkeypatch.setattr(ground_mod, "FILL_MARGIN", margin)
    seen = []
    real = ground_mod._filled_near
    monkeypatch.setattr(ground_mod, "_filled_near", lambda *a: seen.append(1) or real(*a))
    fast = read_cells(cfg, tables, keep)
    assert seen  # holes were filled tile by tile
    assert not np.isnan(fast.ground).any()
    np.testing.assert_array_equal(fast.rows, whole.rows)
    np.testing.assert_array_equal(fast.cols, whole.cols)
    np.testing.assert_array_equal(fast.ground, whole.ground)
    assert fast.datum == whole.datum


@pytest.mark.parametrize("stride", [2, 3, 4])
def test_a_strided_window_read_whole_and_sliced_is_gdals_decimated_read(holed, stride) -> None:
    """W80: the same pixels and holes as :meth:`RasterBed._window`, windows inside, across and past the raster."""
    from wadi2d.terrain import RasterBed

    cfg, _tables, _keep = holed
    rng = np.random.default_rng(stride)
    with RasterBed(cfg.terrain.dem, stride) as bed:
        h, w = bed.src.height, bed.src.width
        boxes = [(-7, -5, 40, 50), (h - 30, w - 41, 30, 40), (h + 5, 0, 10, 10), (0, 0, h // stride, w // stride)]
        boxes += [(int(rng.integers(-20, h)), int(rng.integers(-20, w)), int(rng.integers(1, 90)), int(rng.integers(1, 90))) for _ in range(40)]
        for row, col, nrows, ncols in boxes:
            z, mask = ground_mod._strided_window(bed, row, col, nrows, ncols)
            z0, mask0 = bed._window(row, col, nrows, ncols)
            np.testing.assert_array_equal(mask, mask0)
            np.testing.assert_array_equal(z, z0)
        bed.bind(bed.left, bed.top)
        for fill in (True, False):  # and the whole read, fill and all
            np.testing.assert_array_equal(ground_mod._read(bed, 3, 5, 60, 70, fill), bed.read(3, 5, 60, 70, fill))


def test_one_thread_reads_what_many_read(holed, monkeypatch) -> None:
    cfg, tables, keep = holed
    many = read_cells(cfg, tables, keep)
    monkeypatch.setattr(ground_mod, "READ_WORKERS", 1)
    real = ground_mod._ThreadBeds.__init__
    monkeypatch.setattr(ground_mod._ThreadBeds, "__init__", lambda self, *a: real(self, *a, workers=1))
    np.testing.assert_array_equal(read_cells(cfg, tables, keep).ground, many.ground)


@pytest.mark.parametrize("threads", [True, False])
def test_a_run_of_kept_cells_reads_the_ground_the_whole_read_gives(holed, monkeypatch, threads) -> None:
    """Holes are filled from the strip of tiles the whole read sees, whatever part of the strip is asked for; with
    the tiles on threads and with each strip read whole."""
    cfg, tables, keep = holed
    whole = read_cells(cfg, tables, keep)
    if not threads:
        monkeypatch.setattr(ground_mod._ThreadBeds, "pick", lambda *_a: False)
    rng = np.random.default_rng(11)
    with CellReader(cfg, tables, keep) as reader:
        assert reader.datum == whole.datum and reader.k == whole.k
        cuts = np.sort(rng.integers(0, whole.rows.size, 9))
        for a, b in pairwise(cuts):
            np.testing.assert_array_equal(reader.read(int(a), int(b)), whole.ground[a:b])
        assert reader.read(5, 5).shape == (0, whole.k**2)
