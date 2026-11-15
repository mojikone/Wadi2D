"""W84: a bed on the chunk store gives what ``RasterBed`` gives, pixel for pixel and mask for mask."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine

from tests.engine.conftest import CRS, NODATA, X0, Y0, job, write_dem
from wadi2d.demstore import StoredBed, open_bed, store_for
from wadi2d.demstore import chunks as chunks_mod
from wadi2d.terrain import GridWindow, RasterBed

NY, NX, PIXEL = 300, 420, 0.5


@pytest.fixture(autouse=True)
def small_chunks(monkeypatch):
    """Chunks of 64 pixels, so a raster of a few hundred has many, whole and cut, and windows cross them."""
    monkeypatch.setattr(chunks_mod, "CHUNK", 64)
    monkeypatch.setattr(chunks_mod, "_STORES", {})


def rough(seed: int = 3) -> np.ndarray:
    """Ground with scattered holes, a patch of holes wider than a chunk, a hole border, and values no reader may
    take for ground: infinite and absurdly high."""
    rng = np.random.default_rng(seed)
    z = 100.0 + rng.random((NY, NX)) * 5.0
    z[rng.random(z.shape) < 0.05] = np.nan
    z[40:190, 100:260] = np.nan
    z[:, -70:] = np.nan
    z[5, 7], z[6, 7], z[200, 30] = np.inf, -np.inf, 3.0e33
    return z


def lzw_dem(path, z: np.ndarray):
    """The owner's kind of file: LZW, tiled, a nodata value."""
    with rasterio.open(
        path, "w", driver="GTiff", height=z.shape[0], width=z.shape[1], count=1, dtype="float32", nodata=NODATA,
        crs=CRS, transform=Affine(PIXEL, 0.0, X0, 0.0, -PIXEL, Y0), tiled=True, blockxsize=32, blockysize=32,
        compress="lzw",
    ) as dst:  # fmt: skip
        dst.write(np.where(np.isnan(z), NODATA, z).astype(np.float32), 1)
    return path


def beds(tmp_path, stride: int = 1, z: np.ndarray | None = None):
    dem = lzw_dem(tmp_path / "dem.tif", rough() if z is None else z)
    cfg = job(dem, 10, 10, 2.0, grid={"cache_dir": str(tmp_path / "cache")})
    stored = open_bed(cfg, tmp_path / "cache", stride)
    assert isinstance(stored, StoredBed) and stored.store is not None
    return RasterBed(dem, stride), stored


WINDOWS = [
    (0, 0, 64, 64),  # one chunk exactly
    (10, 20, 150, 170),  # across chunks
    (-30, -45, 120, 130),  # past the north-west corner
    (250, 380, 90, 80),  # past the south-east corner
    (-500, 0, 40, 40),  # off the raster
    (40, 100, 150, 160),  # all holes
    (0, 0, NY, NX),  # everything
    (63, 63, 2, 2),  # a chunk corner
]


@pytest.mark.parametrize("stride", [1, 2, 3, 4])
def test_windows_and_masks_are_the_plain_beds(tmp_path, stride) -> None:
    plain, stored = beds(tmp_path, stride)
    with plain, stored:
        for row, col, nrows, ncols in WINDOWS:
            row, col = row * stride, col * stride  # native pixels, as _window takes them
            for a, b in zip(
                plain._window(row, col, nrows, ncols), stored._window(row, col, nrows, ncols), strict=True
            ):
                assert a.dtype == b.dtype
                np.testing.assert_array_equal(a, b)
            for fill in (True, False):
                np.testing.assert_array_equal(
                    plain.read(row // stride, col // stride, nrows, ncols, fill),
                    stored.read(row // stride, col // stride, nrows, ncols, fill),
                )


def test_a_bound_bed_reads_from_the_grid_origin(tmp_path) -> None:
    plain, stored = beds(tmp_path, 2)
    with plain, stored:
        for bed in (plain, stored):
            bed.bind(X0 + 17 * PIXEL, Y0 - 9 * PIXEL)
        np.testing.assert_array_equal(plain.read(-3, 4, 100, 120), stored.read(-3, 4, 100, 120))
        again = stored.reopen()
        assert again.store is stored.store
        np.testing.assert_array_equal(plain.read(-3, 4, 100, 120), again.read(-3, 4, 100, 120))
        again.close()


@pytest.mark.parametrize("stride", [1, 2, 3])
@pytest.mark.parametrize("dx_pixels", [1, 4, 5, 20])
def test_the_active_mask_is_the_plain_beds(tmp_path, stride, dx_pixels) -> None:
    plain, stored = beds(tmp_path, stride)
    dx = dx_pixels * PIXEL * stride
    with plain, stored:
        for extent in (
            None,
            (X0 + 3.0, Y0 - 120.0, X0 + 180.0, Y0 - 2.0),
            (X0 - 50.0, Y0 - 500.0, X0 + 500.0, Y0 + 50.0),  # wider than the raster: clipped to it
        ):
            w = plain.snap(extent, dx)
            np.testing.assert_array_equal(plain.active_mask(w, dx), stored.active_mask(w, dx))
        w = GridWindow(X0 - 40 * dx, Y0 + 30 * dx, 90, 110)  # a window past the raster's corner, not snapped
        np.testing.assert_array_equal(plain.active_mask(w, dx), stored.active_mask(w, dx))


def test_cells_not_wanted_are_not_read(tmp_path) -> None:
    plain, stored = beds(tmp_path)
    with plain, stored:
        dx = 4 * PIXEL
        w = plain.snap(None, dx)
        wanted = np.zeros((w.ny, w.nx), bool)
        wanted[:20, :30] = True
        np.testing.assert_array_equal(stored.active_cells(w, dx, wanted), plain.active_mask(w, dx) & wanted)
        made = {p.name for p in stored.store.folder.glob("r*")}
        assert made and all(
            int(name[1:6]) <= 1 and int(name[8:13]) <= 1 for name in made
        )  # the chunks under them


def test_a_chunk_is_decoded_once_and_found_by_the_next_process(tmp_path) -> None:
    plain, stored = beds(tmp_path)
    with plain, stored:
        first = stored.read(0, 0, NY, NX)
        made = stored.store.filled
        assert made == len(list(stored.store.folder.glob("r*")))
        assert any(stored.store.folder.glob("*.void"))  # the hole border: chunks with no data hold no pixels
        stored.read(0, 0, NY, NX)
        assert stored.store.filled == made
        chunks_mod._STORES.clear()  # as a new process finds the folder
        with rasterio.open(plain.path) as src:
            later = store_for(plain.path, src, tmp_path / "cache", 64.0)
        assert later is not stored.store and later.folder == stored.store.folder
        fresh = StoredBed(plain.path, 1, later)
        np.testing.assert_array_equal(fresh.read(0, 0, NY, NX), first)
        np.testing.assert_array_equal(fresh.read(0, 0, NY, NX), plain.read(0, 0, NY, NX))
        assert later.filled == 0
        fresh.close()


def test_threads_share_the_store(tmp_path) -> None:
    plain, stored = beds(tmp_path)
    with plain, stored:
        boxes = [(r, c, 90, 110) for r in range(-20, 260, 37) for c in range(-20, 380, 41)]

        def read(box):
            bed = stored.reopen()
            try:
                return bed.read(*box)
            finally:
                bed.close()

        with ThreadPoolExecutor(8) as pool:
            got = list(pool.map(read, boxes))
        for box, z in zip(boxes, got, strict=True):
            np.testing.assert_array_equal(z, plain.read(*box))
        chunks = (NY + 63) // 64 * ((NX + 63) // 64)
        assert stored.store.filled <= chunks  # no chunk made twice


def test_a_chunk_cut_short_is_made_again(tmp_path) -> None:
    plain, stored = beds(tmp_path)
    with plain, stored:
        want = plain.read(0, 0, 64, 64)
        np.testing.assert_array_equal(stored.read(0, 0, 64, 64), want)
        path, _void = stored.store._paths((0, 0))
        stored.store._open.clear()  # nothing holds the file
        import gc

        gc.collect()
        path.write_bytes(path.read_bytes()[:1000])
        np.testing.assert_array_equal(stored.read(0, 0, 64, 64), want)
        assert np.load(path).shape == (64, 64)


def test_a_changed_file_gets_a_new_store(tmp_path) -> None:
    plain, stored = beds(tmp_path)
    old = stored.store.folder
    plain.close()
    stored.close()
    z = rough()
    z[0, 0] += 1.0
    plain, stored = beds(tmp_path, z=z)
    with plain, stored:
        assert stored.store.folder != old
        np.testing.assert_array_equal(stored.read(0, 0, 10, 10), plain.read(0, 0, 10, 10))


def test_no_cache_folder_or_switched_off_reads_through_gdal(tmp_path, monkeypatch) -> None:
    dem = write_dem(tmp_path / "dem.tif", rough(), PIXEL)
    cfg = job(dem, 10, 10, 2.0)
    with open_bed(cfg, None) as bed, RasterBed(dem) as plain:
        assert bed.store is None
        np.testing.assert_array_equal(bed.read(3, 4, 50, 60), plain.read(3, 4, 50, 60))
    monkeypatch.setenv(chunks_mod.STORE_ENV, "0")
    with open_bed(cfg, tmp_path / "cache") as bed:
        assert bed.store is None
    assert not (tmp_path / "cache").exists()


def test_a_raster_with_overviews_keeps_gdals_decimated_read(tmp_path) -> None:
    """GDAL answers a decimated read from an overview, which holds other numbers than the full raster's pixels."""
    dem = lzw_dem(tmp_path / "dem.tif", rough())
    with rasterio.open(dem, "r+") as dst:
        dst.build_overviews([2, 4], Resampling.average)
    cfg = job(dem, 10, 10, 2.0)
    with RasterBed(dem, 2) as plain, open_bed(cfg, tmp_path / "cache", 2) as stored:
        assert stored.store is not None and not stored.whole_pixels
        np.testing.assert_array_equal(plain.read(3, 4, 100, 120), stored.read(3, 4, 100, 120))
        w = plain.snap(None, 4.0)
        np.testing.assert_array_equal(plain.active_mask(w, 4.0), stored.active_mask(w, 4.0))
    with (
        RasterBed(dem) as plain,
        open_bed(cfg, tmp_path / "cache") as stored,
    ):  # the full pixels are the store's
        np.testing.assert_array_equal(plain.read(3, 4, 100, 120), stored.read(3, 4, 100, 120))
