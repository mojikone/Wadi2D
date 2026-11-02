"""Hyetograph and gridded rain through the whole pipeline: closed boxes, where the water must equal the rain."""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from tests.engine.conftest import CRS, X0, Y0, job, write_dem
from tests.engine.test_mesh_paths import MESH, NX, NY, flat
from tests.hydrology.test_network import GRID, small_basin
from wadi2d.forcing import build_storm
from wadi2d.hydrology.network import LumpedEngine
from wadi2d.run import job_hash, run_job
from wadi2d.storm import UniformStorm
from wadi2d.storm.gridded import GriddedStorm
from wadi2d.storm.rain_frames import RainFrames

SIDE = 32
DX = 4.0
AREA = (SIDE * DX) ** 2
QUICK = {"duration_s": 1800.0, "source_every_s": 60.0}
MINUTES = 30.0


def box(tmp_path):
    return write_dem(tmp_path / "flat.tif", np.full((SIDE * 2, SIDE * 2), 100.0), 2.0)


def stack(tmp_path, west_mm: float, east_mm: float, frames: int = 3, width: float = SIDE * DX):
    """One GeoTIFF per period over the box, the western half and the eastern half raining differently."""
    folder = tmp_path / "rain"
    folder.mkdir(exist_ok=True)
    for n in range(frames):
        data = np.array([[west_mm, east_mm]], np.float32) / frames
        with rasterio.open(
            folder / f"r{n}.tif", "w", driver="GTiff", height=1, width=2, count=1, dtype="float32", crs=CRS,
            transform=from_origin(X0, Y0, width / 2.0, width),
        ) as dst:  # fmt: skip
            dst.write(data, 1)
    return str(folder)


def gridded(folder: str, **extra) -> dict:
    return {"kind": "gridded", "rain_file": folder, "rain_interval_min": MINUTES / 3.0, **extra}


def test_a_flat_hyetograph_runs_as_the_uniform_storm_it_equals(tmp_path) -> None:
    dem = box(tmp_path)
    uniform = job(dem, SIDE, SIDE, DX, storm={"kind": "uniform", "depth_mm": 30.0, "duration_min": MINUTES}, run=QUICK)
    table = {"kind": "hyetograph", "hyetograph_min": [10.0, 20.0, 30.0], "hyetograph_mm": [10.0, 10.0, 10.0]}
    hyetograph = job(dem, SIDE, SIDE, DX, storm=table, run=QUICK)
    a = run_job(uniform, tmp_path / "uniform")
    b = run_job(hyetograph, tmp_path / "hyetograph")
    assert a.exit_code == b.exit_code == 0
    assert b.balance.rain == pytest.approx(0.03 * AREA, rel=1e-6)
    assert b.balance.storage == pytest.approx(a.balance.storage, rel=1e-6)


def test_gridded_rain_falls_where_the_grid_says(tmp_path) -> None:
    cfg = job(box(tmp_path), SIDE, SIDE, DX, storm=gridded(stack(tmp_path, 40.0, 10.0)), run=QUICK)
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0
    assert run.balance.rain == pytest.approx(0.5 * AREA * 0.05, rel=1e-5)
    assert abs(run.balance.relative) < 1e-4


def test_gridded_rain_takes_each_cells_own_losses(tmp_path) -> None:
    cn = 80.0
    cfg = job(
        box(tmp_path), SIDE, SIDE, DX, storm=gridded(stack(tmp_path, 80.0, 40.0)),
        hydrology={"curve_number": cn}, run=QUICK,
    )  # fmt: skip
    run = run_job(cfg, tmp_path / "out")
    s = (1000.0 / cn - 10.0) * 25.4
    ia = 0.2 * s
    excess = [(p - ia) ** 2 / (p - ia + s) for p in (80.0, 40.0)]
    assert run.balance.rain == pytest.approx(sum(excess) / 2.0 / 1000.0 * AREA, rel=1e-4)


def test_refreshing_often_or_rarely_gives_the_same_gridded_rain(tmp_path) -> None:
    dem, folder = box(tmp_path), stack(tmp_path, 40.0, 10.0)
    volumes = []
    for every in (30.0, 300.0):
        cfg = job(dem, SIDE, SIDE, DX, storm=gridded(folder), run={**QUICK, "source_every_s": every})
        volumes.append(run_job(cfg, tmp_path / f"out{every:g}").balance.rain)
    assert volumes[0] == pytest.approx(volumes[1], rel=1e-5)


def test_gridded_rain_on_a_mesh_keeps_its_volume(tmp_path) -> None:
    width = NX * DX
    folder = stack(tmp_path, 40.0, 40.0, width=width)
    dem = flat(tmp_path)
    uniform = {"kind": "uniform", "depth_mm": 40.0, "duration_min": MINUTES}
    plain = run_job(job(dem, NX, NY, DX, mesh=MESH, storm=uniform, run=QUICK), tmp_path / "uniform")
    run = run_job(job(dem, NX, NY, DX, mesh=MESH, storm=gridded(folder), run=QUICK), tmp_path / "out")
    assert run.exit_code == plain.exit_code == 0
    assert run.balance.rain == pytest.approx(plain.balance.rain, rel=1e-5)
    assert abs(run.balance.relative) < 1e-4


def test_a_grid_that_misses_the_domain_stops_the_run(tmp_path) -> None:
    cfg = job(box(tmp_path), SIDE, SIDE, DX, storm=gridded(stack(tmp_path, 40.0, 10.0, width=SIDE * DX / 2.0)), run=QUICK)
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 2
    assert "does not cover the domain" in run.message


def test_gridded_rain_warns_when_it_outlasts_the_run(tmp_path) -> None:
    run_cfg = {"duration_s": 300.0, "source_every_s": 60.0}
    cfg = job(box(tmp_path), SIDE, SIDE, DX, storm=gridded(stack(tmp_path, 40.0, 10.0)), run=run_cfg)
    assert run_job(cfg, tmp_path / "out").exit_code == 0
    events = [json.loads(line) for line in (tmp_path / "out" / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e.get("ev") == "warn" and "stops at 5" in e["message"] for e in events)


def test_a_changed_rain_file_changes_the_job_hash(tmp_path) -> None:
    dem, folder = box(tmp_path), stack(tmp_path, 40.0, 10.0)
    cfg = job(dem, SIDE, SIDE, DX, storm=gridded(folder), run=QUICK)
    before = job_hash(cfg)
    stack(tmp_path, 50.0, 10.0)
    assert job_hash(cfg) != before


def test_storm_builders_give_the_new_kinds(tmp_path) -> None:
    table = {"kind": "hyetograph", "hyetograph_min": [30.0], "hyetograph_mm": [10.0]}
    assert build_storm(job("x.tif", 8, 8, 4.0, storm=table)).total_depth == 10.0
    storm = build_storm(job("x.tif", 8, 8, 4.0, storm=gridded(stack(tmp_path, 40.0, 10.0))))
    assert isinstance(storm, GriddedStorm)
    assert storm.total_depth == pytest.approx(25.0)


def test_lumped_subbasins_read_the_rain_under_their_own_polygons() -> None:
    """The same depth and timing under every polygon must give the uniform storm's hydrographs, to the digit."""
    from shapely.geometry import box as rectangle

    steps = 12
    starts = 5.0 * np.arange(steps)
    depths = np.full((steps, 1, 3), 10.0 / steps)
    frames = RainFrames(depths, starts, starts + 5.0, 0.0, 3000.0, 1000.0, 3000.0, CRS)
    polygons = {name: rectangle(100.0, 100.0, 2500.0, 2500.0) for name in ("A", "B", "C")}
    rain = GriddedStorm(frames).bind(polygons, CRS)
    plain = LumpedEngine(small_basin()).run(UniformStorm(10.0, 60.0), GRID)
    run = LumpedEngine(small_basin()).run(rain, GRID)
    assert run.outflow["OUT"] == pytest.approx(plain.outflow["OUT"], rel=1e-9)
