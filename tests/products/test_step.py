"""The step through a real run: what lands on disk, GPU against CPU, stop, skip, the command line, the study."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import h5py
import numpy as np
import pytest
import rasterio

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.config.schema import RunConfig
from wadi2d.engine.cli import main as cli
from wadi2d.engine.estimate import saved_maps
from wadi2d.products import runner, step
from wadi2d.products.pixels import array_module
from wadi2d.products.step import PIXEL_DIR, ProductsStopped, Watch, make_products
from wadi2d.run import job_hash, prepare_grid, run_job


def wadi(nx: int, ny: int, pixel: float) -> np.ndarray:
    """A channel falling east at 2 %, between banks 3 m high."""
    x = (np.arange(nx) + 0.5) * pixel
    y = (np.arange(ny) + 0.5) * pixel
    xx, yy = np.meshgrid(x, y)
    bank = np.clip(np.abs(yy - ny * pixel / 2.0) - 30.0, 0.0, 6.0) * 0.5
    return 200.0 - 0.02 * xx + bank


def wadi_job(tmp: Path, backend: str = "cpu", **outputs) -> RunConfig:
    dem = write_dem(tmp / "wadi.tif", wadi(120, 64, 5.0), 5.0)
    return job(
        dem,
        30,
        16,
        20.0,
        terrain={"manning": 0.04},
        storm={"kind": "uniform", "depth_mm": 120.0, "duration_min": 30.0},
        boundaries=[{"kind": "free", "coordinates": [(X0 + 590.0, Y0), (X0 + 590.0, Y0 - 320.0)]}],
        run={"duration_s": 2400.0, "backend": backend, "source_every_s": 30.0},
        outputs={"map_every_s": 300.0, **outputs},
    )


@pytest.fixture(scope="module")
def finished(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("wadi")
    cfg = wadi_job(tmp)
    summary = run_job(cfg, tmp / "run")
    assert summary.exit_code == 0, summary.message
    return cfg, tmp / "run", summary


def test_a_run_makes_its_pixel_maps_by_default(finished) -> None:
    _cfg, run, summary = finished
    assert summary.products == runner.PRODUCTS_DONE
    folder = run / PIXEL_DIR
    for name in (step.DEPTH_FILE, step.HAZARD_FILE, step.SPEED_FILE, step.DV_FILE, step.STATS_FILE):
        assert (folder / name).exists()
    assert (folder / "map_layers.gpkg").exists()
    assert (folder / "depth_drawing.tif").exists()
    assert (run / "maps" / "hazard.tif").exists()  # the cell hazard stays


def test_the_done_event_comes_last_and_says_what_became_of_them(finished) -> None:
    _cfg, run, _summary = finished
    events = [json.loads(s) for s in (run / "progress.jsonl").read_text("utf-8").splitlines()]
    kinds = [e["ev"] for e in events]
    assert kinds[-1] == "done"
    assert events[-1]["products"] == runner.PRODUCTS_DONE
    assert kinds.index("products") > kinds.index("start")
    shown = [e["percent"] for e in events if e["ev"] == "products"]
    assert shown == sorted(shown)
    assert shown[-1] == pytest.approx(100.0)


def test_pixels_are_wet_only_in_the_wadi(finished) -> None:
    _cfg, run, _summary = finished
    with rasterio.open(run / PIXEL_DIR / step.HAZARD_FILE) as src:
        classes = src.read(1)
        t = src.transform
    assert classes.max() >= 1
    wet = np.nonzero(classes)
    y = t.f + (wet[0] + 0.5) * t.e
    assert np.abs(y - (Y0 - 160.0)).max() < 45.0  # 30 m to the bank toe, and the first metres of its rise


def test_cpu_and_gpu_give_the_same_answer(finished, tmp_path) -> None:
    pytest.importorskip("cupy")
    cp = array_module("auto")
    if cp is np:
        pytest.skip("no GPU")
    cfg, run, _summary = finished
    tables, crs = prepare_grid(cfg, run / "cache")
    (tmp_path / "results.h5").write_bytes((run / "results.h5").read_bytes())
    quiet = Watch(lambda *_a, **_k: None, lambda: False)
    make_products(cfg, tables, crs, tmp_path, quiet, "gpu")
    cpu_dir = tmp_path / "cpu"
    cpu_dir.mkdir()
    (cpu_dir / "results.h5").write_bytes((run / "results.h5").read_bytes())
    make_products(cfg, tables, crs, cpu_dir, quiet, "cpu")
    for name, tolerance in ((step.HAZARD_FILE, 0), (step.DEPTH_FILE, 1e-3), (step.SPEED_FILE, 1e-3)):
        with rasterio.open(tmp_path / PIXEL_DIR / name) as a, rasterio.open(cpu_dir / PIXEL_DIR / name) as b:
            assert np.abs(a.read(1).astype(float) - b.read(1).astype(float)).max() <= tolerance


def test_stop_during_the_step_keeps_the_run_and_leaves_no_half_file(tmp_path) -> None:
    cfg = wadi_job(tmp_path)
    tables, crs = prepare_grid(cfg, tmp_path / "cache")
    summary = run_job(cfg.model_copy(update={"outputs": _pixels_off(cfg)}), tmp_path / "run", tables=(tables, crs))
    assert summary.products == runner.PRODUCTS_NONE
    seen = []

    def stop_soon() -> bool:
        seen.append(1)
        return len(seen) > 12

    with pytest.raises(ProductsStopped):
        make_products(cfg, tables, crs, tmp_path / "run", Watch(lambda *_a, **_k: None, stop_soon), "cpu")
    folder = tmp_path / "run" / PIXEL_DIR
    assert not list(folder.glob("*.tmp.*"))
    assert not (folder / step.STATS_FILE).exists()


def _pixels_off(cfg: RunConfig):
    return cfg.outputs.model_copy(update={"pixels": cfg.outputs.pixels.model_copy(update={"enabled": False})})


def test_a_stop_file_during_the_step_does_not_fail_the_run(tmp_path, monkeypatch) -> None:
    cfg = wadi_job(tmp_path)
    original = step.Watch.tick

    def touch_then_tick(self, stage, done, of):
        if stage == "maps" and done == 2:
            (tmp_path / "run" / "stop").touch()
        original(self, stage, done, of)

    monkeypatch.setattr(step.Watch, "tick", touch_then_tick)
    summary = run_job(cfg, tmp_path / "run")
    assert summary.exit_code == 0
    assert summary.products == runner.PRODUCTS_STOPPED
    assert not (tmp_path / "run" / "stop").exists()
    assert (tmp_path / "run" / "maps" / "max_depth.tif").exists()


def test_a_failure_of_the_step_is_a_warning_on_a_finished_run(tmp_path, monkeypatch) -> None:
    cfg = wadi_job(tmp_path)

    def broken(*_a, **_k):
        raise OSError("no disk")

    monkeypatch.setattr(runner, "make_products", broken)
    summary = run_job(cfg, tmp_path / "run")
    assert summary.exit_code == 0
    assert summary.products == runner.PRODUCTS_FAILED
    text = (tmp_path / "run" / "progress.jsonl").read_text("utf-8")
    assert "no disk" in text


def test_a_stopped_run_makes_none(tmp_path) -> None:
    cfg = wadi_job(tmp_path)
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "stop").touch()
    summary = run_job(cfg, tmp_path / "run")
    assert summary.exit_code == 6
    assert summary.products == runner.PRODUCTS_NONE
    assert not (tmp_path / "run" / PIXEL_DIR).exists()


def test_a_run_without_saved_maps_skips_them_and_says_so(tmp_path) -> None:
    summary = run_job(wadi_job(tmp_path, map_every_s=0.0), tmp_path / "run")
    assert summary.exit_code == 0
    assert summary.products == runner.PRODUCTS_SKIPPED


def test_off_in_the_job_means_off(tmp_path) -> None:
    summary = run_job(wadi_job(tmp_path, pixels={"enabled": False}), tmp_path / "run")
    assert summary.products == runner.PRODUCTS_NONE
    assert not (tmp_path / "run" / PIXEL_DIR).exists()


def test_the_command_line_remakes_them_on_a_run_folder(tmp_path) -> None:
    cfg = wadi_job(tmp_path)
    run_job(cfg.model_copy(update={"outputs": _pixels_off(cfg)}), tmp_path / "run")
    assert not (tmp_path / "run" / PIXEL_DIR).exists()
    assert cli(["products", str(tmp_path / "run"), "--backend", "cpu"]) == 0
    assert (tmp_path / "run" / PIXEL_DIR / step.HAZARD_FILE).exists()
    assert (tmp_path / "run" / runner.PRODUCTS_LOG).exists()


def test_the_command_line_refuses_a_folder_with_no_run(tmp_path) -> None:
    assert cli(["products", str(tmp_path)]) == runner.EXIT_INVALID


def test_peak_depth_does_not_wait_for_a_saved_map(tmp_path) -> None:
    """Maps every 2300 s miss the peak of a short storm; the run's own peak still reaches the pixels."""
    summary = run_job(wadi_job(tmp_path, map_every_s=2300.0), tmp_path / "coarse")
    assert summary.exit_code == 0
    with h5py.File(tmp_path / "coarse" / "results.h5", "r") as f:
        run_peak = float(f["maxima"]["mean_depth"][:].max())
        saved = max(float(f["maps"][name]["mean_depth"][:].max()) for name in f["maps"])
    with rasterio.open(tmp_path / "coarse" / PIXEL_DIR / step.DEPTH_FILE) as src:
        pixel_peak = float(src.read(1, masked=True).max())
    assert run_peak > 1.01 * saved  # the saved maps did miss it
    assert pixel_peak >= 0.99 * run_peak


def test_the_run_s_peak_lifts_depth_times_speed_to_what_the_cell_saw(tmp_path) -> None:
    summary = run_job(wadi_job(tmp_path, map_every_s=2300.0), tmp_path / "coarse")
    assert summary.exit_code == 0
    with h5py.File(tmp_path / "coarse" / "results.h5", "r") as f:
        run_peak = float(f["maxima"]["hazard"][:].max())
        saved = 0.0
        for name in f["maps"]:
            group = f["maps"][name]
            saved = max(saved, float((group["depth"][:] * group["speed"][:]).max()))
    with rasterio.open(tmp_path / "coarse" / PIXEL_DIR / step.DV_FILE) as src:
        lifted = float(src.read(1, masked=True).max())
    assert run_peak > saved
    assert lifted > saved * 0.5  # a pixel reads the sub-grid depth, not the level over the cell's lowest point


def test_a_coarser_pixel_is_a_setting(tmp_path) -> None:
    summary = run_job(wadi_job(tmp_path, pixels={"pixel_m": 10.0}), tmp_path / "run")
    assert summary.products == runner.PRODUCTS_DONE
    with rasterio.open(tmp_path / "run" / PIXEL_DIR / step.DEPTH_FILE) as src:
        assert src.transform.a == 10.0


def test_a_pixel_that_does_not_fit_the_dem_fails_the_step_not_the_run(tmp_path) -> None:
    summary = run_job(wadi_job(tmp_path, pixels={"pixel_m": 7.0}), tmp_path / "run")
    assert summary.exit_code == 0
    assert summary.products == runner.PRODUCTS_FAILED


def test_rasters_of_record_without_the_drawing(tmp_path) -> None:
    summary = run_job(wadi_job(tmp_path, smooth={"enabled": False}), tmp_path / "run")
    assert summary.products == runner.PRODUCTS_DONE
    assert (tmp_path / "run" / PIXEL_DIR / step.HAZARD_FILE).exists()
    assert not (tmp_path / "run" / PIXEL_DIR / "map_layers.gpkg").exists()


def test_the_setup_of_the_run_goes_into_the_geopackage(finished) -> None:
    _cfg, run, _summary = finished
    with sqlite3.connect(run / PIXEL_DIR / "map_layers.gpkg") as db:
        names = {row[0] for row in db.execute("SELECT table_name FROM gpkg_contents")}
    assert {"hazard_classes", "domain", "boundaries"} <= names


def test_products_settings_do_not_refuse_a_checkpoint(tmp_path) -> None:
    cfg = wadi_job(tmp_path)
    other = wadi_job(tmp_path, pixels={"depth_floor": 0.1}, smooth={"sigma_px": 2.0})
    assert job_hash(cfg) == job_hash(other)


def test_the_estimate_says_the_disk_of_the_maps() -> None:
    cfg = RunConfig.model_validate({"run": {"duration_s": 3600.0}, "outputs": {"map_every_s": 900.0}})
    assert saved_maps(cfg, 1_000_000) == (5, 0.05)
    fine = RunConfig.model_validate({"run": {"duration_s": 3600.0}, "outputs": {"map_every_s": 300.0}})
    assert saved_maps(fine, 1_000_000) == (13, 0.13)
    off = RunConfig.model_validate({"outputs": {"map_every_s": 0.0}})
    assert saved_maps(off, 1_000_000) == (0, 0.0)
