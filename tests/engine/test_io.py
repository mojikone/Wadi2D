"""The file writers on their own: every result must read back exactly as written."""

from __future__ import annotations

import json
import sqlite3

import h5py
import numpy as np
import pytest
import rasterio
import shapely

from tests.engine.conftest import CRS, X0, Y0
from wadi2d.config.schema import Tables
from wadi2d.grid import TileGrid
from wadi2d.io.cache import cache_key, cache_path, load_tables, save_tables
from wadi2d.io.geopackage import LINES, VectorLayer, write_geopackage
from wadi2d.io.geotiff import NODATA, LiveRaster, write_map
from wadi2d.io.progress import Progress
from wadi2d.io.results import Results, safe_name, write_series_csv
from wadi2d.tables import ArrayBed, build_tables


@pytest.fixture
def grid() -> TileGrid:
    mask = np.ones((30, 62), bool)
    mask[:5, :5] = False
    return TileGrid.from_mask(mask, X0, Y0, 8.0)


def test_map_round_trip_with_nodata_and_georeference(grid, tmp_path):
    data = np.arange(grid.shape[0] * grid.shape[1], dtype=np.float32).reshape(grid.shape)
    path = write_map(tmp_path / "m" / "a.tif", data, grid, CRS, valid=data > 100.0)
    with rasterio.open(path) as src:
        band = src.read(1)
        assert src.transform.c == grid.x0
        assert src.transform.f == grid.y0
        assert src.transform.a == 8.0
        assert src.crs.to_epsg() == 32640
    keep = grid.mask & (data > 100.0)
    np.testing.assert_array_equal(band[keep], data[keep])
    assert (band[~keep] == NODATA).all()


def test_live_raster_rewrites_in_place(grid, tmp_path):
    live = LiveRaster(tmp_path / "live" / "depth.tif", grid, CRS, stride=2)
    ino = (tmp_path / "live" / "depth.tif").stat().st_size
    depth = np.full(grid.shape, 3.0, np.float32)
    assert live.write(depth)
    assert live.write(depth * 2.0)
    assert (tmp_path / "live" / "depth.tif").stat().st_size == ino
    with rasterio.open(tmp_path / "live" / "depth.tif") as src:
        assert src.width == grid.shape[1] // 2
        band = src.read(1, masked=True)
    assert band.max() == 6.0


def test_results_file_layout(grid, tmp_path):
    r = Results(tmp_path / "r.h5", grid, "wkt", '{"a": 1}')
    field = np.ones(grid.shape, np.float32)
    r.snapshot(300.0, {"depth": field})
    r.maxima({"depth": field * 2.0})
    r.maxima({"depth": field * 3.0})
    r.series("lines", "Faydh 01", np.array([0.0, 1.0]), {"discharge_m3s": np.array([2.0, 3.0])})
    r.attributes({"status": "finished"})
    r.close()
    with h5py.File(tmp_path / "r.h5", "r") as f:
        assert json.loads(f.attrs["config"]) == {"a": 1}
        assert f.attrs["dx"] == 8.0
        assert f["maps/t000000300/depth"].attrs is not None
        assert f["maxima/depth"][0, 0] == 3.0
        np.testing.assert_array_equal(f["series/lines/Faydh_01/discharge_m3s"][()], [2.0, 3.0])
        assert f["series/lines/Faydh_01"].attrs["name"] == "Faydh 01"


def test_series_csv_and_names(tmp_path):
    path = write_series_csv(tmp_path / "s" / "x.csv", np.array([0.0, 60.0]), {"q": np.array([1.5, 2.5])})
    assert path.read_text(encoding="utf-8").splitlines() == ["t_s,q", "0.000,1.5", "60.000,2.5"]
    assert safe_name("Bidah 03 / dam") == "Bidah_03_dam"


def test_progress_lines_are_flushed_json(tmp_path):
    p = Progress(tmp_path / "progress.jsonl")
    p.emit("start", cells=3)
    assert json.loads((tmp_path / "progress.jsonl").read_text(encoding="utf-8")) == {
        "ev": "start",
        "cells": 3,
    }
    p.close()


def test_cache_round_trip_and_key(grid, tmp_path):
    ny, nx = grid.shape
    z = np.fromfunction(lambda r, c: 0.01 * c + np.sin(r * 0.3), (ny * 2, nx * 2))
    tables = build_tables(grid, ArrayBed(z, 4.0), Tables(), 0.04)
    key = cache_key({"a": 1})
    assert key == cache_key({"a": 1})
    assert key != cache_key({"a": 2})
    path = cache_path(tmp_path, key)
    save_tables(path, tables, key)
    back = load_tables(path, key)
    assert back is not None
    assert load_tables(path, cache_key({"a": 2})) is None
    assert load_tables(tmp_path / "missing.h5", key) is None
    np.testing.assert_array_equal(back.grid.mask, grid.mask)
    assert (back.grid.x0, back.grid.y0, back.grid.dx) == (grid.x0, grid.y0, grid.dx)
    for name in ("zmin", "hc", "dtab", "flx", "cwy", "ftaby"):
        np.testing.assert_array_equal(getattr(back, name), getattr(tables, name))


def test_a_geopackage_layer_can_carry_z(tmp_path):
    line = shapely.LineString([(0.0, 0.0, 10.0), (5.0, 5.0, 12.0)])
    flat = VectorLayer("flat", {"n": int}, [(1,)], [line], LINES)
    tall = VectorLayer("tall", {"n": int}, [(1,)], [line], LINES, has_z=True)
    path = write_geopackage(tmp_path / "z.gpkg", [flat, tall], "")
    db = sqlite3.connect(path)
    assert dict(db.execute("SELECT table_name, z FROM gpkg_geometry_columns")) == {"flat": 0, "tall": 1}
    flat_blob = db.execute("SELECT geom FROM flat").fetchone()[0]
    tall_blob = db.execute("SELECT geom FROM tall").fetchone()[0]
    assert not shapely.from_wkb(flat_blob[40:]).has_z
    assert list(shapely.from_wkb(tall_blob[40:]).geoms[0].coords) == [(0.0, 0.0, 10.0), (5.0, 5.0, 12.0)]
