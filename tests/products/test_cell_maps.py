"""W86: the run's cell maps hold the cells an aligned strip replaced, each with its strip cell's own value."""

from __future__ import annotations

import h5py
import numpy as np
import pytest
import rasterio

from tests.engine.conftest import tilted_dem  # noqa: F401
from tests.engine.test_strips_run import corridor, plane_job
from wadi2d.engine.cli import main as cli
from wadi2d.io.geotiff import NODATA, write_map
from wadi2d.products.cell_maps import STRIP_FIELDS, strip_on_lattice
from wadi2d.run import prepare_grid, run_job


@pytest.fixture(scope="module")
def striped(tmp_path_factory):
    from tests.engine.conftest import tilted_box, write_dem

    tmp = tmp_path_factory.mktemp("cellmaps")
    dem = write_dem(tmp / "tilted.tif", tilted_box(100, 48, 2.0, 0.01), 2.0)
    cfg = plane_job(dem, corridor())
    tables, crs = prepare_grid(cfg, tmp / "cache")
    summary = run_job(cfg, tmp / "run", tables=(tables, crs))
    assert summary.exit_code == 0, summary.message
    return cfg, tables, crs, tmp / "run"


def _read(path) -> np.ndarray:
    with rasterio.open(path) as src:
        return src.read(1)


def test_every_replaced_square_reads_the_strip_cell_at_its_centre(striped) -> None:
    _cfg, tables, _crs, run = striped
    rows, cols, cell = strip_on_lattice(tables)
    replaced = tables.strip.strip.masked
    assert rows.size == np.asarray(replaced[0]).size > 0  # the strip's cells cover the squares they replaced
    geo = tables.strip.strip.geometry
    x = tables.grid.x0 + (cols + 0.5) * tables.grid.dx
    y = tables.grid.y0 - (rows + 0.5) * tables.grid.dx
    for k in range(0, rows.size, 37):  # a square's centre lies in the ring of its strip cell
        ring = geo.ring(int(cell[k]))
        assert geo.x[ring].min() <= x[k] <= geo.x[ring].max() and geo.y[ring].min() <= y[k] <= geo.y[ring].max()
    with h5py.File(run / "results.h5", "r") as f:
        maxima = {name: f["maxima"][name][:] for name in f["maxima"]}
    for name, field in STRIP_FIELDS.items():
        band = _read(run / "maps" / f"{name}.tif")
        np.testing.assert_array_equal(band[rows, cols], maxima[field][0][cell].astype(np.float32), err_msg=name)
        own = tables.grid.mask
        lattice = {"max_depth": "depth", "max_speed": "speed", "hazard": "hazard", "max_mean_depth": "mean_depth"}[name]
        np.testing.assert_array_equal(band[own], maxima[lattice][own].astype(np.float32), err_msg=name)
    depth = maxima["strip_depth"][0][cell]
    level = _read(run / "maps" / "max_level.tif")[rows, cols]
    wet = depth > 0.0
    assert wet.any()
    np.testing.assert_allclose(level[wet], (tables.strip.mesh.zmin[cell] + depth)[wet], rtol=0, atol=1e-4)
    assert (level[~wet] == NODATA).all()
    assert (_read(run / "maps" / "arrival.tif")[rows, cols] == NODATA).all()  # a strip keeps no arrival time


def test_a_remake_fills_the_maps_of_a_run_made_before(striped, tmp_path) -> None:
    """``wadi2d products`` on a run whose cell maps are blank on the strip writes them again, filled."""
    import shutil

    _cfg, tables, crs, run = striped
    later = tmp_path / "run"
    shutil.copytree(run, later)
    want = _read(run / "maps" / "max_depth.tif")
    with h5py.File(run / "results.h5", "r") as f:
        write_map(later / "maps" / "max_depth.tif", f["maxima"]["depth"][:], tables.grid, crs)  # as it was: blank
    rows, cols, _cell = strip_on_lattice(tables)
    assert (_read(later / "maps" / "max_depth.tif")[rows, cols] == NODATA).all()
    assert cli(["products", str(later), "--backend", "cpu"]) == 0
    np.testing.assert_array_equal(_read(later / "maps" / "max_depth.tif"), want)
    assert '"cell_maps"' in (later / "products.jsonl").read_text("utf-8")


def test_a_run_without_a_strip_keeps_its_maps(tmp_path, tilted_dem) -> None:  # noqa: F811
    cfg = plane_job(tilted_dem, None)
    tables, crs = prepare_grid(cfg, tmp_path / "cache")
    assert strip_on_lattice(tables) is None
    assert run_job(cfg, tmp_path / "run", tables=(tables, crs)).exit_code == 0
    band = _read(tmp_path / "run" / "maps" / "max_depth.tif")
    with h5py.File(tmp_path / "run" / "results.h5", "r") as f:
        np.testing.assert_array_equal(band, np.where(tables.grid.mask, f["maxima"]["depth"][:], NODATA).astype(np.float32))
