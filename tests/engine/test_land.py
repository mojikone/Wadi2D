"""Roughness in four forms and curve numbers overridden by land use, range or subbasin (W96)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import shapely
from pydantic import ValidationError

from tests.engine.conftest import CRS, X0, Y0, job, tilted_box, write_dem
from wadi2d.config.land import CurveOverride, Roughness
from wadi2d.forcing import curve_numbers, manning_grid
from wadi2d.grid.tiles import TileGrid
from wadi2d.hydrology.losses import ScsCurveNumber
from wadi2d.hydrology.model import Basin, Subbasin
from wadi2d.hydrology.transforms import SCS_UH, TRANSFORM_METHODS
from wadi2d.land import polygon_mean, with_curve_overrides
from wadi2d.run import InvalidJob, job_hash, load_job

NX, NY, DX, PIXEL = 20, 12, 8.0, 2.0
"""160 x 96 m of cells on a DEM of 2 m pixels."""


@pytest.fixture
def dem(tmp_path: Path) -> Path:
    return write_dem(tmp_path / "dem.tif", tilted_box(80, 48, PIXEL, 0.01), PIXEL)


@pytest.fixture
def classes(tmp_path: Path) -> Path:
    """Land use: class 1 on the west half, 2 on the east half, nodata on the last column of pixels."""
    codes = np.ones((48, 80))
    codes[:, 40:] = 2.0
    codes[:, -1] = np.nan
    return write_dem(tmp_path / "landuse.tif", codes, PIXEL)


@pytest.fixture
def grid() -> TileGrid:
    return TileGrid.from_mask(np.ones((NY, NX), bool), X0, Y0, DX)


def _west(grid: TileGrid) -> np.ndarray:
    """The active cells west of the middle; the grid's halo and tile padding are no cells."""
    x, _y = grid.xy_of(*np.nonzero(np.ones(grid.shape, bool)))
    return (x < X0 + 80.0).reshape(grid.shape) & grid.mask


def _east(grid: TileGrid) -> np.ndarray:
    return grid.mask & ~_west(grid)


# --- Manning ----------------------------------------------------------------------------------------------------


def test_each_roughness_form_asks_for_its_own_fields_and_refuses_the_rest() -> None:
    assert Roughness(form="uniform", n=0.04).n == 0.04
    for bad in (
        {"form": "uniform"},
        {"form": "split", "n": 0.04},
        {"form": "grid"},
        {"form": "land_use", "land_use": "a.tif"},
        {"form": "uniform", "n": 0.04, "raster": "a.tif"},
        {"form": "split", "n": 0.04, "n_aligned": 0.03, "classes": [{"code": 1, "n": 0.05}]},
        {"form": "land_use", "land_use": "a.tif", "classes": [{"code": 1, "n": 0.05}, {"code": 1, "n": 0.06}]},
    ):
        with pytest.raises(ValidationError):
            Roughness(**bad)


def test_roughness_and_the_old_manning_raster_are_one_or_the_other(dem) -> None:
    with pytest.raises(ValidationError, match="both give the roughness"):
        job(dem, NX, NY, DX, terrain={"manning_raster": "n.tif", "roughness": {"form": "uniform", "n": 0.04}})
    with pytest.raises(ValidationError, match=r"strips\.enabled is off"):
        job(dem, NX, NY, DX, terrain={"roughness": {"form": "split", "n": 0.04, "n_aligned": 0.03}})


def test_one_value_and_two_values_give_the_squares_and_the_aligned_cells_theirs(dem, grid) -> None:
    one = job(dem, NX, NY, DX, terrain={"roughness": {"form": "uniform", "n": 0.045}})
    assert manning_grid(one, grid, CRS) == manning_grid(one, grid, CRS, aligned=True) == 0.045
    two = job(dem, NX, NY, DX, strips={"enabled": True},
              terrain={"roughness": {"form": "split", "n": 0.05, "n_aligned": 0.03}})  # fmt: skip
    assert manning_grid(two, grid, CRS) == 0.05
    assert manning_grid(two, grid, CRS, aligned=True) == 0.03


def test_the_grid_form_reads_as_the_old_manning_raster_did(dem, grid, tmp_path) -> None:
    n = np.full((48, 80), 0.06)
    n[:, -1] = np.nan
    raster = write_dem(tmp_path / "n.tif", n, PIXEL)
    old = manning_grid(job(dem, NX, NY, DX, terrain={"manning_raster": str(raster), "manning": 0.03}), grid, CRS)
    new = manning_grid(job(dem, NX, NY, DX, terrain={"roughness": {"form": "grid", "raster": str(raster)}, "manning": 0.03}), grid, CRS)
    np.testing.assert_array_equal(new, old)
    given = manning_grid(job(dem, NX, NY, DX, terrain={"roughness": {"form": "grid", "raster": str(raster), "n": 0.02}}), grid, CRS)
    np.testing.assert_allclose(given[grid.mask], 0.06, rtol=1e-6)  # no cell centre's nearest pixel is the nodata column
    assert np.all(given[~grid.mask] == 0.02)  # roughness.n, not terrain.manning, where the raster gives nothing


def test_land_use_classes_take_their_n_and_a_class_not_listed_stops_the_run(dem, grid, classes) -> None:
    rows = [{"code": 1, "n": 0.03, "name": "bare"}, {"code": 2, "n": 0.08, "name": "scrub"}]
    cfg = job(dem, NX, NY, DX, terrain={"roughness": {"form": "land_use", "land_use": str(classes), "classes": rows}})
    n = manning_grid(cfg, grid, CRS)
    west = _west(grid)
    assert np.all(n[west] == 0.03) and np.all(n[_east(grid)] == 0.08)
    short = job(dem, NX, NY, DX, terrain={"roughness": {"form": "land_use", "land_use": str(classes), "classes": rows[:1]}})
    with pytest.raises(ValueError, match=r"holds the classes \[2\]"):
        manning_grid(short, grid, CRS)


# --- curve numbers ----------------------------------------------------------------------------------------------


def test_each_override_asks_for_its_own_table_and_refuses_overlapping_ranges() -> None:
    assert CurveOverride(by="range", ranges=[{"low": 60, "high": 70, "curve_number": 65}]).by == "range"
    for bad in (
        {"by": "range"},
        {"by": "land_use", "classes": [{"code": 1, "curve_number": 70}]},
        {"by": "subbasin", "subbasins": [{"name": "S1", "curve_number": 70}], "ranges": [{"low": 1, "high": 2, "curve_number": 3}]},
        {"by": "range", "ranges": [{"low": 60, "high": 70, "curve_number": 65}, {"low": 70, "high": 80, "curve_number": 75}]},
        {"by": "range", "ranges": [{"low": 70, "high": 60, "curve_number": 65}]},
        {"by": "subbasin", "subbasins": [{"name": "S1", "curve_number": 70}, {"name": "S1", "curve_number": 71}]},
    ):
        with pytest.raises(ValidationError):
            CurveOverride(**bad)


def test_a_range_turns_the_cells_values_inside_it_and_leaves_the_rest(dem, grid) -> None:
    ranges = [{"low": 75, "high": 85, "curve_number": 70}]
    hit = job(dem, NX, NY, DX, hydrology={"curve_number": 80.0, "cn_override": {"by": "range", "ranges": ranges}})
    assert np.all(curve_numbers(hit, grid, {}) == 70.0)
    miss = job(dem, NX, NY, DX, hydrology={"curve_number": 90.0, "cn_override": {"by": "range", "ranges": ranges}})
    assert np.all(curve_numbers(miss, grid, {}) == 90.0)


def test_land_use_sets_the_cells_cn_and_keeps_the_grids_where_it_has_none(dem, grid, classes) -> None:
    rows = [{"code": 1, "curve_number": 60.0}, {"code": 2, "curve_number": 90.0}]
    cfg = job(dem, NX, NY, DX, hydrology={"curve_number": 75.0,
              "cn_override": {"by": "land_use", "land_use": str(classes), "classes": rows}})  # fmt: skip
    cn = curve_numbers(cfg, grid, {}, CRS)
    west = _west(grid)
    assert np.all(cn[west] == 60.0) and np.all(cn[_east(grid)] == 90.0)
    short = job(dem, NX, NY, DX, hydrology={"cn_override": {"by": "land_use", "land_use": str(classes), "classes": rows[1:]}})
    with pytest.raises(ValueError, match=r"holds the classes \[1\]"):
        curve_numbers(short, grid, {}, CRS)


def test_a_subbasin_cn_lands_on_its_polygons_cells_and_an_unknown_name_is_refused(dem, grid) -> None:
    west = shapely.box(X0, Y0 - 96.0, X0 + 80.0, Y0)
    cfg = job(dem, NX, NY, DX, hydrology={"curve_number": 75.0,
              "cn_override": {"by": "subbasin", "subbasins": [{"name": "W", "curve_number": 55.0}]}})  # fmt: skip
    cn = curve_numbers(cfg, grid, {"W": west})
    assert np.all(cn[_west(grid)] == 55.0) and np.all(cn[_east(grid)] == 75.0)
    with pytest.raises(ValueError, match=r"names \['W'\]"):
        curve_numbers(cfg, grid, {}, CRS)


def _basin(*names: str, cn: float = 80.0) -> Basin:
    transform = TRANSFORM_METHODS.build(SCS_UH, lag_minutes=30.0)
    return Basin("b", [Subbasin(name=n, downstream=None, area_km2=1.0, loss=ScsCurveNumber(cn), transform=transform) for n in names])


def test_lumped_subbasins_take_the_override_by_name_and_by_range(dem) -> None:
    basin = _basin("S1", "S2")
    named = job(dem, NX, NY, DX, hydrology={"subbasins": [{"name": "S1"}, {"name": "S2"}],
                "cn_override": {"by": "subbasin", "subbasins": [{"name": "S2", "curve_number": 66.0}]}})  # fmt: skip
    assert with_curve_overrides(basin, named) == {"S2": 66.0}
    assert basin.elements["S1"].loss.curve_number == 80.0 and basin.elements["S2"].loss.curve_number == 66.0
    ranged = job(dem, NX, NY, DX, hydrology={"cn_override": {"by": "range", "ranges": [{"low": 79, "high": 81, "curve_number": 85}]}})
    basin = _basin("S1", cn=80.0)
    assert with_curve_overrides(basin, ranged) == {"S1": 85.0}
    stray = job(dem, NX, NY, DX, hydrology={"cn_override": {"by": "subbasin", "subbasins": [{"name": "X", "curve_number": 66.0}]}})
    with pytest.raises(ValueError, match=r"names \['X'\]"):
        with_curve_overrides(_basin("S1"), stray)


def test_a_lumped_subbasin_takes_its_polygons_mean_cn_by_land_use(dem, classes, tmp_path) -> None:
    """S1 covers a quarter of the domain on class 1 and a quarter on class 2: the mean of 60 and 90 is 75."""
    polygons = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"name": "S1"},
                      "geometry": shapely.geometry.mapping(shapely.box(X0 + 40.0, Y0 - 96.0, X0 + 120.0, Y0))}],
    }  # fmt: skip
    path = tmp_path / "subbasins.geojson"
    path.write_text(json.dumps(polygons), encoding="utf-8")
    rows = [{"code": 1, "curve_number": 60.0}, {"code": 2, "curve_number": 90.0}]
    cfg = job(dem, NX, NY, DX, hydrology={"polygons": str(path), "subbasins": [{"name": "S1"}],
              "cn_override": {"by": "land_use", "land_use": str(classes), "classes": rows}})  # fmt: skip
    basin = _basin("S1")
    taken = with_curve_overrides(basin, cfg, CRS)
    assert taken["S1"] == pytest.approx(75.0)
    assert basin.elements["S1"].loss.curve_number == pytest.approx(75.0)
    assert polygon_mean(str(classes), shapely.box(X0 + 500.0, Y0 - 50.0, X0 + 600.0, Y0), "", {1: 60.0}, "x") is None
    with pytest.raises(ValueError, match=r"\['S2'\] have none"):
        with_curve_overrides(_basin("S1", "S2"), cfg, CRS)


# --- the job --------------------------------------------------------------------------------------------------


def test_an_old_job_keeps_its_hash_and_an_override_changes_it(dem, classes) -> None:
    plain = job(dem, NX, NY, DX, hydrology={"curve_number": 80.0})
    ranged = job(dem, NX, NY, DX, hydrology={"curve_number": 80.0,
                 "cn_override": {"by": "range", "ranges": [{"low": 75, "high": 85, "curve_number": 70}]}})  # fmt: skip
    rough = job(dem, NX, NY, DX, hydrology={"curve_number": 80.0}, terrain={"roughness": {"form": "uniform", "n": 0.035}})
    assert len({job_hash(plain), job_hash(ranged), job_hash(rough)}) == 3
    rows = [{"code": 1, "curve_number": 60.0}, {"code": 2, "curve_number": 90.0}]
    used = job(dem, NX, NY, DX, hydrology={"cn_override": {"by": "land_use", "land_use": str(classes), "classes": rows}})
    before = job_hash(used)
    write_dem(classes, np.full((48, 80), 2.0), PIXEL)
    assert job_hash(used) != before  # the land-use raster's content is part of the job


def test_relative_land_use_paths_resolve_from_the_job_file_and_must_exist(dem, classes, tmp_path) -> None:
    data = job(dem, NX, NY, DX).model_dump(mode="json")
    data["terrain"]["roughness"] = {"form": "land_use", "land_use": "landuse.tif", "classes": [{"code": 1, "n": 0.03}]}
    data["hydrology"]["cn_override"] = {"by": "land_use", "land_use": "landuse.tif", "classes": [{"code": 1, "curve_number": 70}]}
    path = tmp_path / "job.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    cfg = load_job(path)
    assert Path(cfg.terrain.roughness.land_use) == classes.resolve()
    assert Path(cfg.hydrology.cn_override.land_use) == classes.resolve()
    from wadi2d.run import InputMissing, check_inputs

    check_inputs(cfg)
    gone = cfg.model_copy(update={"terrain": cfg.terrain.model_copy(update={"roughness": Roughness(
        form="land_use", land_use=str(tmp_path / "none.tif"), classes=[{"code": 1, "n": 0.03}])})})  # fmt: skip
    with pytest.raises(InputMissing, match=r"terrain\.roughness\.land_use"):
        check_inputs(gone)
    assert InvalidJob  # the run wraps the refusals above in InvalidJob (run._curve_overrides)


def _excess(depth: float, cn: float) -> float:
    s = (1000.0 / cn - 10.0) * 25.4
    return (depth - 0.2 * s) ** 2 / (depth + 0.8 * s)


def test_a_run_loses_its_rain_by_the_land_use_override(tmp_path) -> None:
    """A closed flat box keeps every drop: half of it at CN 60 and half at CN 90 keeps the mean of their excess."""
    from wadi2d.run import run_job

    flat = write_dem(tmp_path / "flat.tif", np.full((32, 32), 5.0), 2.0)
    codes = np.ones((32, 32))
    codes[:, 16:] = 2.0
    landuse = write_dem(tmp_path / "lu.tif", codes, 2.0)
    rows = [{"code": 1, "curve_number": 60.0}, {"code": 2, "curve_number": 90.0}]
    depth = 100.0
    cfg = job(flat, 16, 16, 4.0, storm={"kind": "uniform", "depth_mm": depth, "duration_min": 60.0},
              hydrology={"curve_number": 95.0, "cn_override": {"by": "land_use", "land_use": str(landuse), "classes": rows}},
              terrain={"roughness": {"form": "land_use", "land_use": str(landuse), "classes": [{"code": 1, "n": 0.03}, {"code": 2, "n": 0.06}]}},
              run={"duration_s": 3600.0, "source_every_s": 60.0})  # fmt: skip
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0, run.message
    kept = 0.5 * (_excess(depth, 60.0) + _excess(depth, 90.0)) / 1000.0 * (16 * 4.0) ** 2
    assert run.balance.storage == pytest.approx(kept, rel=1e-3)
    short = cfg.model_copy(update={"hydrology": cfg.hydrology.model_copy(update={"cn_override": CurveOverride(
        by="land_use", land_use=str(landuse), classes=rows[:1])})})  # fmt: skip
    refused = run_job(short, tmp_path / "out2")
    assert refused.exit_code == 2 and "holds the classes [2]" in refused.message
