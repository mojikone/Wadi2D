"""W84: the tables and the domain mask are the same numbers with the chunk store as without."""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.demstore import chunks as chunks_mod
from wadi2d.io.cache import builder_identity
from wadi2d.run import domain_mask, grid_window, prepare_grid
from wadi2d.terrain import RasterBed

K, NX, NY, DX = 4, 90, 70, 2.0


@pytest.fixture(autouse=True)
def small_chunks(monkeypatch):
    monkeypatch.setattr(chunks_mod, "CHUNK", 64)
    monkeypatch.setattr(chunks_mod, "_STORES", {})


def ground(seed: int = 11) -> np.ndarray:
    """Rough ground with holes inside and a strip of no data along the east side."""
    rng = np.random.default_rng(seed)
    x = (np.arange(NX * K) + 0.5) * DX / K
    z = 100.0 - 0.01 * x + rng.random((NY * K, NX * K)) * 1.5
    z[rng.random(z.shape) < 0.03] = np.nan
    z[100:140, 60:130] = np.nan
    z[:, -30:] = np.nan
    return z


def outline(tmp_path):
    """A domain with a slanted side, so cells inside the window lie outside the domain."""
    ring = [
        (X0 + 6.0, Y0 - 5.0),
        (X0 + NX * DX - 20.0, Y0 - 9.0),
        (X0 + NX * DX - 50.0, Y0 - NY * DX + 8.0),
        (X0 + 30.0, Y0 - NY * DX + 20.0),
        (X0 + 6.0, Y0 - 5.0),
    ]
    feature = {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}
    crs = {"type": "name", "properties": {"name": "EPSG:32640"}}
    path = tmp_path / "domain.geojson"
    path.write_text(
        json.dumps({"type": "FeatureCollection", "crs": crs, "features": [feature]}), encoding="utf-8"
    )
    return path


def arrays(tables) -> dict[str, np.ndarray]:
    held = {k: v for k, v in vars(tables).items() if isinstance(v, np.ndarray)}
    held["mask"] = tables.grid.mask
    return held


@pytest.mark.parametrize("conveyance", ["strips", "local_radius"])
@pytest.mark.parametrize("stride", [1, 2])
def test_tables_built_on_the_store_are_the_plain_tables(tmp_path, monkeypatch, conveyance, stride) -> None:
    dem = write_dem(tmp_path / "dem.tif", ground(), DX / K)
    parts = {
        "grid": {"domain": str(outline(tmp_path)), "extent": None},
        "terrain": {"dem": str(dem), "pixel_stride": stride},
        "tables": {"face_conveyance": conveyance},
    }
    cfg = job(dem, NX, NY, DX, **parts)
    identity = builder_identity()
    stored, _crs = prepare_grid(cfg, tmp_path / "with")
    assert list((tmp_path / "with").glob("dem_*/r*.npy"))  # the store was used
    monkeypatch.setenv(chunks_mod.STORE_ENV, "0")
    plain, _crs = prepare_grid(cfg, tmp_path / "without")
    assert not list((tmp_path / "without").glob("dem_*"))
    a, b = arrays(stored), arrays(plain)
    assert a.keys() == b.keys() and len(a) > 15
    for name in a:
        assert a[name].dtype == b[name].dtype, name
        np.testing.assert_array_equal(a[name], b[name], err_msg=name)
    # and the two builds have one key: the store is not part of what a cache is found by
    assert builder_identity() == identity
    assert {p.name for p in (tmp_path / "with").glob("grid_*.h5")} == {
        p.name for p in (tmp_path / "without").glob("grid_*.h5")
    }
    assert {p.name for p in (tmp_path / "with").glob("mask_*.npz")} == {
        p.name for p in (tmp_path / "without").glob("mask_*.npz")
    }


def test_the_domain_mask_reads_only_under_the_outline(tmp_path) -> None:
    dem = write_dem(tmp_path / "dem.tif", ground(), DX / K)
    cfg = job(dem, NX, NY, DX, grid={"domain": str(outline(tmp_path)), "extent": None})
    from wadi2d.demstore import open_bed

    with RasterBed(dem) as plain, open_bed(cfg, tmp_path / "cache") as stored:
        window = grid_window(cfg, plain)
        want = domain_mask(cfg, plain, window)
        assert want.any() and not want.all()
        np.testing.assert_array_equal(domain_mask(cfg, stored, window), want)
        with rasterio.open(dem) as src:
            everything = ((src.height + 63) // 64) * ((src.width + 63) // 64)
        assert 0 < len(list(stored.store.folder.glob("r*"))) < everything
