"""W92: the store's block mean is GDAL's average read (``read_coarse``) to the last bit, ties and holes included."""

from __future__ import annotations

import numpy as np
import pytest

from tests.demstore.test_store import lzw_dem
from tests.engine.conftest import X0, Y0, job
from wadi2d.demstore import chunks as chunks_mod
from wadi2d.demstore import open_bed
from wadi2d.demstore.coarse import can_average, coarse_mean, gdal_chunks, read_coarse_from
from wadi2d.mesh.streams import read_coarse

NY, NX = 1500, 1700
"""Over GDAL's chunk of 1024 x 1024 pixels, so its read is cut into chunks, some with holes and some without."""


@pytest.fixture(autouse=True)
def small_chunks(monkeypatch):
    monkeypatch.setattr(chunks_mod, "CHUNK", 256)
    monkeypatch.setattr(chunks_mod, "_STORES", {})


def tied_ground(seed: int = 5) -> np.ndarray:
    """Ground of float32 values, whose block means fall on a tie between two float32 values about once in a hundred
    (the two paths of GDAL's average round those differently), holes in one corner and a patch in the middle."""
    rng = np.random.default_rng(seed)
    z = (300.0 + 40.0 * rng.random((NY, NX))).astype(np.float32).astype(np.float64)
    z[:300, :400][rng.random((300, 400)) < 0.02] = np.nan
    z[700:760, 900:1000] = np.nan
    z[:, -15:] = np.nan
    return z


def stored(tmp_path):
    dem = lzw_dem(tmp_path / "dem.tif", tied_ground())
    cfg = job(dem, 10, 10, 5.0, grid={"cache_dir": str(tmp_path / "cache")})
    return dem, open_bed(cfg, tmp_path / "cache")


# (first row, first column, rows, columns of cells, cell m, cuts of a cell): DEM pixels of 0.5 m
WINDOWS = [
    (0, 0, NY // 10, NX // 10, 5.0, 1),  # the whole raster, 10 x 10 pixels a block
    (3, 7, 120, 140, 5.0, 1),
    (0, 0, NY // 20, NX // 20, 10.0, 2),
    (5, 2, 30, 35, 20.0, 4),
    (60, 80, 30, 40, 5.0, 1),  # wholly valid ground
]


@pytest.mark.parametrize("window", WINDOWS)
def test_the_block_mean_is_gdals_to_the_bit(tmp_path, window) -> None:
    dem, bed = stored(tmp_path)
    j0, i0, ny, nx, cell, factor = window
    x0, y0 = X0 + i0 * cell, Y0 - j0 * cell
    with bed:
        assert can_average(bed, x0, y0, ny, nx, cell)
        ours = coarse_mean(bed, x0, y0, ny, nx, cell, factor)
        serial = coarse_mean(bed, x0, y0, ny, nx, cell, factor, workers=1)
    gdal = read_coarse(dem, x0, y0, ny, nx, cell, factor)
    assert ours.shape == gdal.shape
    assert np.array_equal(ours, gdal, equal_nan=True)
    assert np.array_equal(serial, gdal, equal_nan=True)


def test_the_two_paths_differ_on_this_ground_so_the_test_can_fail(tmp_path) -> None:
    """GDAL's chunks with holes and without both occur in the whole read, and a mean taken by the wrong path differs."""
    _dem, bed = stored(tmp_path)
    chunks = gdal_chunks(0, 0, NY, NX, NY // 10, NX // 10, (NY, NX))
    assert len(chunks) > 2
    from wadi2d.demstore.coarse import _block_means

    with bed:
        z, mask = bed._window(0, 0, NY, NX)
        k = 10
        plain = np.empty((NY // k, NX // k))
        masked = np.empty_like(plain)
        count = np.empty(plain.shape, np.int32)
        _block_means(z, mask, k, plain, masked, count, 0)
    full = count == k * k
    assert (plain[full] != masked[full]).sum() > 20


def test_a_window_past_the_raster_is_read_by_gdal(tmp_path) -> None:
    dem, bed = stored(tmp_path)
    x0, y0 = X0 - 20.0, Y0 + 20.0
    with bed:
        assert not can_average(bed, x0, y0, 40, 40, 5.0)
        got = read_coarse_from(bed, dem, x0, y0, 40, 40, 5.0, 1)
    assert np.array_equal(got, read_coarse(dem, x0, y0, 40, 40, 5.0, 1), equal_nan=True)
