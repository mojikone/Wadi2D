"""The run folder: every output, the water balance, the exit codes, stop and resume, the grid cache."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import h5py
import numpy as np
import pytest
import rasterio

from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem
from wadi2d.config.schema import RunConfig
from wadi2d.run import load_job, prepare_grid, run_job

MAPS = ("max_depth", "max_speed", "hazard", "arrival")


def valley(nx: int, ny: int, pixel: float) -> np.ndarray:
    """A V valley falling east: 2 % along it, 5 % on the banks."""
    x = (np.arange(nx) + 0.5) * pixel
    y = (np.arange(ny) + 0.5) * pixel
    xx, yy = np.meshgrid(x, y)
    return 200.0 - 0.02 * xx + 0.05 * np.abs(yy - ny * pixel / 2.0)


def full_job(dem: Path, backend: str, duration: float = 2400.0, **parts) -> RunConfig:
    return job(
        dem,
        64,
        48,
        8.0,
        terrain={"manning": 0.04},
        storm={"kind": "uniform", "depth_mm": 40.0, "duration_min": 20.0},
        hydrology={"curve_number": 85.0},
        boundaries=[{"kind": "free", "coordinates": [(X0 + 508.0, Y0), (X0 + 508.0, Y0 - 384.0)]}],
        run={"duration_s": duration, "backend": backend, "source_every_s": 30.0},
        outputs={
            "map_every_s": 600.0,
            "live_every_s": 0.05,
            "series_every_s": 30.0,
            "points": [{"name": "Mid point", "x": X0 + 256.0, "y": Y0 - 192.0}],
            "lines": [{"name": "Cross", "coordinates": [(X0 + 300.0, Y0 - 4.0), (X0 + 300.0, Y0 - 380.0)]}],
        },
        **parts,
    )


@pytest.fixture
def valley_dem(tmp_path: Path) -> Path:
    return write_dem(tmp_path / "valley.tif", valley(256, 192, 2.0), 2.0)


def check_outputs(out: Path, summary) -> None:
    assert summary.exit_code == 0, summary.message
    resolved = RunConfig.model_validate_json((out / "config.resolved.json").read_text(encoding="utf-8"))
    assert resolved.storm.kind == "uniform"
    events = [json.loads(line) for line in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    kinds = {e["ev"] for e in events}
    assert {"start", "step", "output", "done"} <= kinds
    assert events[-1]["ev"] == "done"
    assert events[-1]["status"] == "finished"
    for name in MAPS:
        with rasterio.open(out / "maps" / f"{name}.tif") as src:
            assert src.crs.to_epsg() == 32640
            assert src.dtypes == ("float32",)
            assert src.nodata == -9999.0
            assert src.compression.name == "deflate"
    with rasterio.open(out / "maps" / "max_depth.tif") as src:
        depth = src.read(1, masked=True)
        assert depth.max() > 0.05
    with rasterio.open(out / "live" / "depth.tif") as src:
        assert src.read(1, masked=True).max() >= 0.0
    assert (out / "series" / "point_Mid_point.csv").is_file()
    lines = (out / "series" / "line_Cross.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "t_s,discharge_m3s"
    assert len(lines) > 40
    with h5py.File(out / "results.h5", "r") as f:
        assert f.attrs["status"] == "finished"
        assert RunConfig.model_validate_json(f.attrs["config"]).project.format_version == "1.0"
        assert f["maxima/depth"].shape == f["mask"].shape
        assert len(f["maps"]) >= 3
        assert f["series/lines/Cross/discharge_m3s"].size == len(lines) - 1
        assert abs(f.attrs["relative_error"]) < 1e-3
    assert abs(summary.balance.relative) < 1e-3
    assert summary.balance.outflow > 0.0
    assert summary.peaks["Cross"][0] > 0.1


def test_end_to_end_cpu(valley_dem, tmp_path):
    out = tmp_path / "run"
    check_outputs(out, run_job(full_job(valley_dem, "cpu"), out))


@pytest.mark.gpu
def test_end_to_end_gpu(valley_dem, tmp_path):
    out = tmp_path / "run"
    summary = run_job(full_job(valley_dem, "gpu"), out)
    assert summary.backend == "gpu"
    check_outputs(out, summary)


@pytest.mark.gpu
def test_gpu_and_cpu_agree_on_the_maxima(valley_dem, tmp_path):
    a = run_job(full_job(valley_dem, "cpu", 900.0), tmp_path / "a")
    b = run_job(full_job(valley_dem, "gpu", 900.0), tmp_path / "b")
    assert a.steps == pytest.approx(b.steps, rel=0.01)
    with (
        h5py.File(tmp_path / "a" / "results.h5", "r") as f,
        h5py.File(tmp_path / "b" / "results.h5", "r") as g,
    ):
        for name in ("depth", "speed", "hazard"):
            np.testing.assert_allclose(f["maxima"][name][()], g["maxima"][name][()], atol=0.05, rtol=0.05)


def test_losses_follow_the_curve_number(tmp_path):
    # a closed flat box keeps every drop: its storage is the SCS excess of the depth that fell
    dem = write_dem(tmp_path / "f.tif", np.full((32, 32), 5.0), 2.0)
    depth, cn = 100.0, 80.0
    cfg = job(
        dem,
        16,
        16,
        4.0,
        storm={"kind": "uniform", "depth_mm": depth, "duration_min": 60.0},
        hydrology={"curve_number": cn},
        run={"duration_s": 3600.0, "source_every_s": 60.0},
    )
    run = run_job(cfg, tmp_path / "out")
    s = (1000.0 / cn - 10.0) * 25.4
    ia = 0.2 * s
    excess = (depth - ia) ** 2 / (depth - ia + s)
    assert run.balance.storage == pytest.approx(excess / 1000.0 * (16 * 4.0) ** 2, rel=1e-3)


def test_lumped_polygon_masks_the_rain_and_hydrograph_enters(tmp_path):
    dem = write_dem(tmp_path / "f.tif", tilted_box(64, 64, 2.0, 0.0), 2.0)
    polygon = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "West"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[X0, Y0], [X0 + 64.0, Y0], [X0 + 64.0, Y0 - 128.0], [X0, Y0 - 128.0], [X0, Y0]]
                    ],
                },
            }
        ],
    }
    path = tmp_path / "subs.geojson"
    path.write_text(json.dumps(polygon), encoding="utf-8")
    flow = 2.0
    cfg = job(
        dem,
        32,
        32,
        4.0,
        storm={"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0},
        hydrology={
            "polygons": str(path),
            "subbasins": [{"name": "West", "mode": "lumped"}],
            "inflows": [
                {
                    "name": "q",
                    "x": X0 + 100.0,
                    "y": Y0 - 60.0,
                    "times_s": [0.0, 1200.0],
                    "flows": [flow, flow],
                }
            ],
        },
        run={"duration_s": 1800.0, "source_every_s": 30.0},
    )
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0
    assert run.balance.rain == pytest.approx(0.02 * 128.0 * 64.0, rel=1e-3)
    assert run.balance.inflow == pytest.approx(flow * 1200.0, rel=1e-3)
    assert abs(run.balance.relative) < 1e-3


def test_invalid_job_gives_exit_2(tmp_path):
    bad = tmp_path / "job.json"
    bad.write_text(json.dumps({"grid": {"dxx": 3}}), encoding="utf-8")
    with pytest.raises(Exception) as caught:
        load_job(bad)
    assert caught.value.code == 2


def test_missing_input_gives_exit_3(tmp_path):
    cfg = job(tmp_path / "nothing.tif", 8, 8, 4.0, run={"duration_s": 10.0})
    summary = run_job(cfg, tmp_path / "out")
    assert summary.exit_code == 3
    assert json.loads((tmp_path / "out" / "progress.jsonl").read_text(encoding="utf-8").splitlines()[-1]) == {
        "ev": "error",
        "code": 3,
        "message": summary.message,
    }


def test_collapsing_step_gives_exit_5_with_the_cell(tilted_dem, tmp_path):
    cfg = job(
        tilted_dem,
        50,
        24,
        4.0,
        hydrology={
            "inflows": [
                {"name": "q", "x": X0 + 50.0, "y": Y0 - 48.0, "times_s": [0.0, 1e6], "flows": [500.0, 500.0]}
            ]
        },
        numerics={"dt_min": 1.0, "dt_every": 1},
        run={"duration_s": 300.0, "source_every_s": 10.0},
    )
    summary = run_job(cfg, tmp_path / "out")
    assert summary.exit_code == 5
    events = [json.loads(s) for s in (tmp_path / "out" / "progress.jsonl").read_text("utf-8").splitlines()]
    cell = next(e for e in events if e["ev"] == "error")["cell"]
    assert {"j", "i", "x", "y"} <= set(cell)


def test_no_backend_gives_exit_4(tilted_dem, tmp_path, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise RuntimeError("no CUDA device available")

    monkeypatch.setattr("wadi2d.run.Model", refuse)
    cfg = job(tilted_dem, 50, 24, 4.0, run={"duration_s": 10.0})
    assert run_job(cfg, tmp_path / "out").exit_code == 4


def test_out_of_memory_gives_exit_7(tilted_dem, tmp_path, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise MemoryError("device memory")

    monkeypatch.setattr("wadi2d.run.Model", refuse)
    cfg = job(tilted_dem, 50, 24, 4.0, run={"duration_s": 10.0})
    assert run_job(cfg, tmp_path / "out").exit_code == 7


def test_curve_number_raster_beats_the_default(tmp_path):
    dem = write_dem(tmp_path / "f.tif", np.full((32, 32), 5.0), 2.0)
    raster = write_dem(tmp_path / "cn.tif", np.full((32, 32), 60.0), 2.0)
    depth = 100.0
    cfg = job(
        dem,
        16,
        16,
        4.0,
        terrain={"cn_raster": str(raster)},
        storm={"kind": "uniform", "depth_mm": depth, "duration_min": 60.0},
        hydrology={"curve_number": 95.0},
        run={"duration_s": 3600.0, "source_every_s": 60.0},
    )
    run = run_job(cfg, tmp_path / "out")
    s = (1000.0 / 60.0 - 10.0) * 25.4
    excess = (depth - 0.2 * s) ** 2 / (depth + 0.8 * s)
    assert run.balance.storage == pytest.approx(excess / 1000.0 * (16 * 4.0) ** 2, rel=1e-3)


def test_stop_file_ends_the_run_with_exit_6_and_resume_finishes_it(valley_dem, tmp_path):
    out = tmp_path / "run"
    cfg = full_job(valley_dem, "cpu", 2400.0)

    def stop_soon() -> None:
        while not (out / "results.h5").exists():
            time.sleep(0.02)
        time.sleep(0.3)
        (out / "stop").touch()

    thread = threading.Thread(target=stop_soon)
    thread.start()
    summary = run_job(cfg, out)
    thread.join()
    assert summary.exit_code == 6
    assert 0.0 < summary.t_end < 2400.0
    assert not (out / "stop").exists()
    assert (out / "maps" / "max_depth.tif").is_file()
    assert (out / "checkpoint.h5").is_file()

    done = run_job(cfg, out, resume=True)
    assert done.exit_code == 0
    assert done.t_end == pytest.approx(2400.0)
    assert abs(done.balance.relative) < 2e-3
    whole = run_job(cfg, tmp_path / "whole")
    assert done.balance.outflow == pytest.approx(whole.balance.outflow, rel=0.02)


def test_grid_cache_hit_and_stale_rebuild(tilted_dem, tmp_path):
    cfg = job(tilted_dem, 50, 24, 4.0, run={"duration_s": 10.0})
    cache = tmp_path / "cache"
    first, _ = prepare_grid(cfg, cache)
    files = sorted(cache.glob("grid_*.h5"))
    assert len(files) == 1
    second, _ = prepare_grid(cfg, cache)
    for a, b in ((first.dtab, second.dtab), (first.ftabx, second.ftabx), (first.zmin, second.zmin)):
        np.testing.assert_array_equal(a, b)
    assert sorted(cache.glob("grid_*.h5")) == files

    # another crest gives another key
    other = cfg.model_copy(update={"tables": cfg.tables.model_copy(update={"rows": 12})})
    assert prepare_grid(other, cache)[0].rows == 12
    assert len(list(cache.glob("grid_*.h5"))) == 2

    # the DEM changed under the same name: stale, rebuilt, and the new ground shows
    write_dem(tilted_dem, tilted_box(100, 48, 2.0, 0.01, base=150.0), 2.0)
    third, _ = prepare_grid(cfg, cache)
    assert third.zmin.max() > first.zmin.max() + 40.0

    # a damaged file under the right name is a miss, never a wrong grid
    victim = next(iter(sorted(cache.glob("grid_*.h5"), key=lambda p: p.stat().st_mtime, reverse=True)))
    victim.write_bytes(b"not hdf5")
    assert prepare_grid(cfg, cache)[0].zmin.max() == pytest.approx(third.zmin.max())


def test_relative_paths_resolve_against_the_job_file(tilted_dem, tmp_path):
    path = tmp_path / "job.json"
    path.write_text(
        json.dumps(
            {"grid": {"dx": 4.0, "extent": [X0, Y0 - 96.0, X0 + 200.0, Y0]}, "terrain": {"dem": "tilted.tif"}}
        ),
        encoding="utf-8",
    )
    assert Path(load_job(path).terrain.dem) == tilted_dem.resolve()
