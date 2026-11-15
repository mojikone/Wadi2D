"""W84: the products' ground is the same numbers with the chunk store as without."""

from __future__ import annotations

import numpy as np
import pytest

from tests.demstore.test_wiring import DX, NX, NY, K, ground
from tests.engine.conftest import job, write_dem
from wadi2d.demstore import chunks as chunks_mod
from wadi2d.products.ground import read_cells
from wadi2d.run import prepare_grid


@pytest.fixture(autouse=True)
def small_chunks(monkeypatch):
    monkeypatch.setattr(chunks_mod, "CHUNK", 64)
    monkeypatch.setattr(chunks_mod, "_STORES", {})


@pytest.mark.parametrize("pixel_m", [0.0, 1.0, 1.5])
def test_the_products_ground_is_the_plain_ground(tmp_path, monkeypatch, pixel_m) -> None:
    """At the DEM's pixel, at a stride of 2 and of 3: holes, their fill from the strip, and the threads."""
    dem = write_dem(tmp_path / "dem.tif", ground(), DX / K)
    cfg = job(
        dem, NX // 3, NY // 3, DX * 3, outputs={"pixels": {"pixel_m": pixel_m}}
    )  # cells of 12 DEM pixels
    tables, _crs = prepare_grid(cfg, tmp_path / "tables")
    rng = np.random.default_rng(5)
    keep = (rng.random(tables.grid.mask.shape) > 0.5) & tables.grid.mask
    stored = read_cells(cfg, tables, keep, cache=tmp_path / "store")
    assert list((tmp_path / "store").glob("dem_*/r*.npy"))
    monkeypatch.setenv(chunks_mod.STORE_ENV, "0")
    plain = read_cells(cfg, tables, keep, cache=tmp_path / "nothing")
    assert not (tmp_path / "nothing").exists()
    assert stored.k == plain.k and stored.datum == plain.datum and stored.rows.size > 20
    np.testing.assert_array_equal(stored.rows, plain.rows)
    np.testing.assert_array_equal(stored.cols, plain.cols)
    np.testing.assert_array_equal(stored.ground, plain.ground)
