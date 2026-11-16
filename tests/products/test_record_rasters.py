"""The rasters of record are light (W100): a bounded error on the floats, reduced copies inside the file."""

from __future__ import annotations

import numpy as np
import pytest
import rasterio

from wadi2d.io.geotiff import BandWriter, float_record, overview_levels, raster_profile

NODATA = -9999.0


def _depth(n: int) -> np.ndarray:
    rng = np.random.default_rng(1)
    rows, cols = np.mgrid[0:n, 0:n]
    wet = (np.sin(cols / 40.0) + np.cos(rows / 30.0)) > 0.3
    values = 0.05 + 3.0 * np.abs(np.sin(cols / 15.0)) + rng.normal(0.0, 0.01, (n, n))
    return np.where(wet, values, NODATA).astype(np.float32)


@pytest.mark.parametrize("error", [0.001, 0.0])
def test_a_float_raster_keeps_every_value_within_its_bound_and_every_dry_pixel(tmp_path, error: float) -> None:
    band = _depth(700)
    profile = float_record(raster_profile(band.shape, 0.5, 400000.0, 2700000.0, "EPSG:32640"), error)
    with BandWriter(tmp_path / "depth.tif", profile, np.float32, NODATA, None, "average") as out:
        out.write(band[:300], 0, 0)
        out.write(band[300:], 300, 0)
    with rasterio.open(tmp_path / "depth.tif") as src:
        back = src.read(1)
        assert src.overviews(1) == [2, 4]
        assert src.profile["compress"].lower() == ("lerc_deflate" if error else "deflate")
        far = src.read(1, out_shape=(175, 175))  # what a map seen whole reads: the reduced copy
    wet = band != NODATA
    assert np.array_equal(back != NODATA, wet)
    assert float(np.abs(back[wet] - band[wet]).max()) <= error * 1.0001 + 1e-7
    assert np.isfinite(far).all() and (far[far != NODATA] > 0.0).all()


def test_bounded_error_makes_a_float_raster_smaller(tmp_path) -> None:
    band = _depth(1024)
    sizes = {}
    for error in (0.0, 0.001):
        path = tmp_path / f"d{error}.tif"
        profile = float_record(raster_profile(band.shape, 0.5, 0.0, 0.0, "EPSG:32640"), error)
        with BandWriter(path, profile, np.float32, NODATA) as out:
            out.write(band, 0, 0)
        sizes[error] = path.stat().st_size
    assert sizes[0.001] < 0.6 * sizes[0.0]


def test_class_overviews_take_the_class_most_pixels_hold(tmp_path) -> None:
    classes = np.zeros((512, 512), np.uint8)
    classes[:, :256] = 2
    classes[::2, :256] = 5  # half the pixels of the west half, by rows: the mode of each 2 x 2 is a tie
    classes[:, 256:] = 3
    with BandWriter(tmp_path / "c.tif", raster_profile(classes.shape, 1.0, 0.0, 0.0, "EPSG:32640"), np.uint8, 0, None, "mode") as out:
        out.write(classes, 0, 0)
    with rasterio.open(tmp_path / "c.tif") as src:
        assert src.overviews(1) == [2]
        half = src.read(1, out_shape=(256, 256))
    assert set(np.unique(half[:, 128:]).tolist()) == {3}
    assert set(np.unique(half[:, :128]).tolist()) <= {2, 5}


@pytest.mark.parametrize("shape, levels", [((200, 200), []), ((300, 100), [2]), ((8192, 4000), [2, 4, 8, 16, 32])])
def test_overviews_stop_at_one_block(shape, levels) -> None:
    assert overview_levels(shape) == levels
