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
from wadi2d.io.cache import cache_key, cache_path, load_mask, load_tables, mask_path, save_mask, save_tables
from wadi2d.io.geopackage import LINES, VectorLayer, add_layer, layer_names, write_geopackage
from wadi2d.io.geotiff import BLOCK, NODATA, BandWriter, LiveRaster, raster_profile, write_band, write_map
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


def test_a_mask_is_kept_by_its_key(tmp_path):
    mask = np.random.default_rng(1).random((40, 70)) > 0.3
    key = cache_key({"domain": 1})
    path = save_mask(mask_path(tmp_path, key), mask, key)
    back = load_mask(path, key)
    assert back.dtype == bool
    np.testing.assert_array_equal(back, mask)
    assert load_mask(path, cache_key({"domain": 2})) is None
    assert load_mask(tmp_path / "missing.npz", key) is None
    path.write_bytes(b"not a mask")
    assert load_mask(path, key) is None


def test_a_band_written_by_windows_reads_as_the_whole_band_and_is_smaller(tmp_path):
    """W50: only the windows that hold something are written; the rest reads back as nodata and takes no room."""
    rng = np.random.default_rng(2)
    band = np.full((5 * BLOCK + 40, 6 * BLOCK + 9), NODATA, np.float32)
    band[BLOCK : 2 * BLOCK, 3 * BLOCK : 5 * BLOCK] = rng.random((BLOCK, 2 * BLOCK))
    band[4 * BLOCK :, 5 * BLOCK :] = rng.random((BLOCK + 40, BLOCK + 9))
    profile = raster_profile(band.shape, 0.5, X0, Y0, CRS)
    whole = write_band(tmp_path / "whole.tif", band, {**profile, "sparse_ok": False}, NODATA, {"a": "1"})
    with BandWriter(tmp_path / "parts.tif", profile, np.float32, NODATA, {"a": "1"}) as out:
        out.write(band[BLOCK : 2 * BLOCK, 3 * BLOCK : 5 * BLOCK], BLOCK, 3 * BLOCK)
        out.write(band[4 * BLOCK :, 5 * BLOCK :], 4 * BLOCK, 5 * BLOCK)
    assert not list(tmp_path.glob("*.tmp.*"))
    with rasterio.open(whole) as a, rasterio.open(tmp_path / "parts.tif") as b:
        np.testing.assert_array_equal(a.read(1), b.read(1))
        assert a.profile["transform"] == b.profile["transform"] and a.crs == b.crs and a.nodata == b.nodata
        assert a.tags() == b.tags()
    assert (tmp_path / "parts.tif").stat().st_size < whole.stat().st_size


def test_a_band_writer_leaves_nothing_behind_on_an_error(tmp_path):
    profile = raster_profile((2 * BLOCK, 2 * BLOCK), 0.5, X0, Y0, CRS)
    with pytest.raises(RuntimeError), BandWriter(tmp_path / "a.tif", profile, np.uint8, 0) as out:
        out.write(np.ones((BLOCK, BLOCK), np.uint8), 0, 0)
        raise RuntimeError("stopped")
    assert not list(tmp_path.iterdir())


def test_a_layer_is_added_to_a_geopackage_that_is_open_elsewhere(tmp_path):
    """W50: the class polygons made after the run go into the file QGIS holds open for the run's other layers."""
    wkt = rasterio.crs.CRS.from_epsg(32640).to_wkt()
    line = shapely.LineString([(X0, Y0), (X0 + 5.0, Y0 - 5.0)])
    path = write_geopackage(tmp_path / "m.gpkg", [VectorLayer("lines", {"n": int}, [(1,)], [line], LINES)], wkt)
    reader = sqlite3.connect(path)
    assert reader.execute("SELECT count(*) FROM lines").fetchone()[0] == 1
    box = shapely.box(X0, Y0 - 10.0, X0 + 10.0, Y0)
    add_layer(path, VectorLayer("areas", {"name": str}, [("a",)], [box]), wkt)
    add_layer(path, VectorLayer("areas", {"name": str}, [("b",), ("c",)], [box, box]), wkt)  # in place of itself
    assert sorted(layer_names(path)) == ["areas", "lines"]
    assert [row[0] for row in reader.execute("SELECT name FROM areas")] == ["b", "c"]
    assert reader.execute("SELECT count(*) FROM gpkg_geometry_columns").fetchone()[0] == 2
    assert reader.execute("SELECT srs_id FROM gpkg_contents WHERE table_name = 'areas'").fetchone()[0] == 32640
    assert reader.execute("SELECT count(*) FROM gpkg_spatial_ref_sys").fetchone()[0] == 3
    reader.close()
    assert layer_names(tmp_path / "missing.gpkg") == []
