"""The step through a real run: what lands on disk, GPU against CPU, stop, skip, the command line, the study."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import threading
from contextlib import closing
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
from wadi2d.products.frames import frame_names
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


@pytest.fixture(scope="module")
def drawn(tmp_path_factory):
    """The same run with the smooth polygons and the depth drawing asked for."""
    tmp = tmp_path_factory.mktemp("drawn")
    cfg = wadi_job(tmp, smooth={"enabled": True})
    summary = run_job(cfg, tmp / "run")
    assert summary.exit_code == 0, summary.message
    return cfg, tmp / "run", summary


def _layers(run: Path) -> set[str]:
    with closing(sqlite3.connect(run / PIXEL_DIR / "map_layers.gpkg")) as db:
        return {row[0] for row in db.execute("SELECT table_name FROM gpkg_contents")}


def test_a_run_makes_its_pixel_maps_by_default(finished) -> None:
    _cfg, run, summary = finished
    assert summary.products == runner.PRODUCTS_DONE
    folder = run / PIXEL_DIR
    for name in (step.DEPTH_FILE, step.HAZARD_FILE, step.SPEED_FILE, step.STATS_FILE):
        assert (folder / name).exists()
    assert not (folder / step.DV_FILE).exists()  # W100: written only when asked; the hazard classes hold it
    assert (folder / "map_layers.gpkg").exists()
    assert (run / "maps" / "hazard.tif").exists()  # the cell hazard stays


def test_the_highest_water_level_is_the_ground_plus_the_highest_depth(finished) -> None:
    """His question of 2026-11-16, the water surface map: wet where the depth raster is, and the level less the depth
    reads the synthetic ground at each pixel's centre."""
    _cfg, run, _summary = finished
    with rasterio.open(run / PIXEL_DIR / step.LEVEL_FILE) as src:
        level, t, nodata = src.read(1), src.transform, src.nodata
    with rasterio.open(run / PIXEL_DIR / step.DEPTH_FILE) as src:
        depth = src.read(1)
    wet = depth != step.NO_DEPTH
    assert wet.sum() > 100
    np.testing.assert_array_equal(level != nodata, wet)
    rows, cols = np.nonzero(wet)
    x = t.c + (cols + 0.5) * t.a - X0
    y = (Y0 - (t.f + (rows + 0.5) * t.e))  # metres south of the DEM's north edge
    ground = 200.0 - 0.02 * x + np.clip(np.abs(y - 64 * 5.0 / 2.0) - 30.0, 0.0, 6.0) * 0.5
    off = np.abs(level[wet] - depth[wet] - ground)
    assert float(np.median(off)) < 0.01 and float(np.percentile(off, 99)) < 0.1, (np.median(off), off.max())


def test_the_polygons_and_the_depth_drawing_are_not_made_unless_asked(finished, drawn) -> None:
    """W50: they are several times the rasters' time, so a run makes them only when its job says so."""
    assert RunConfig().outputs.smooth.enabled is False
    plain, asked = finished[1] / PIXEL_DIR, drawn[1] / PIXEL_DIR
    assert not (plain / "depth_drawing.tif").exists()
    assert "hazard_classes" not in _layers(finished[1])
    assert "smooth" not in json.loads((plain / step.STATS_FILE).read_text("utf-8"))
    assert (asked / "depth_drawing.tif").exists()
    assert "hazard_classes" in _layers(drawn[1])
    assert "smooth" in json.loads((asked / step.STATS_FILE).read_text("utf-8"))
    for name in (step.DEPTH_FILE, step.HAZARD_FILE, step.SPEED_FILE):  # the record does not depend on it
        with rasterio.open(plain / name) as a, rasterio.open(asked / name) as b:
            assert np.array_equal(a.read(1), b.read(1))


def test_the_layers_of_a_run_are_written_without_the_drawing(finished, drawn) -> None:
    """Make map and the layers a run loads read the outline and the setup: every run keeps them."""
    assert {"domain", "boundaries"} <= _layers(finished[1])
    assert _layers(drawn[1]) - _layers(finished[1]) == {"hazard_classes"}
    for name in ("domain", "boundaries"):
        with closing(sqlite3.connect(finished[1] / PIXEL_DIR / "map_layers.gpkg")) as a:
            plain = a.execute(f"SELECT geom FROM {name}").fetchall()
        with closing(sqlite3.connect(drawn[1] / PIXEL_DIR / "map_layers.gpkg")) as b:
            assert plain == b.execute(f"SELECT geom FROM {name}").fetchall()


def test_drawings_asked_for_after_the_run_are_the_run_s_own(finished, drawn, tmp_path) -> None:
    """``wadi2d drawings`` on a run without them gives what a run with the tick gives: same polygons, same picture."""
    later = tmp_path / "run"
    shutil.copytree(finished[1], later)
    assert cli(["drawings", str(later), "--backend", "cpu"]) == 0
    assert _layers(later) == _layers(drawn[1])
    with closing(sqlite3.connect(later / PIXEL_DIR / "map_layers.gpkg")) as a:
        mine = a.execute('SELECT "class", block, geom FROM hazard_classes ORDER BY block, "class"').fetchall()
    with closing(sqlite3.connect(drawn[1] / PIXEL_DIR / "map_layers.gpkg")) as b:
        theirs = b.execute('SELECT "class", block, geom FROM hazard_classes ORDER BY block, "class"').fetchall()
    assert mine and mine == theirs
    with rasterio.open(later / PIXEL_DIR / "depth_drawing.tif") as a, rasterio.open(drawn[1] / PIXEL_DIR / "depth_drawing.tif") as b:
        assert a.transform == b.transform and np.array_equal(a.read(1), b.read(1))
        assert a.overviews(1) == b.overviews(1)
    mine, theirs = (json.loads((run / PIXEL_DIR / step.STATS_FILE).read_text("utf-8")) for run in (later, drawn[1]))
    assert mine == theirs
    events = [json.loads(s) for s in (later / runner.PRODUCTS_LOG).read_text("utf-8").splitlines()]
    shown = [e["percent"] for e in events if e["ev"] == "products"]
    assert shown == sorted(shown) and shown[0] == 0.0 and shown[-1] == pytest.approx(100.0)
    assert events[-1]["ev"] == "done" and events[-1]["code"] == 0


def test_drawings_refuse_a_run_with_no_rasters_and_stop_on_the_stop_file(finished, tmp_path) -> None:
    assert cli(["drawings", str(tmp_path)]) == runner.EXIT_INVALID
    later = tmp_path / "run"
    shutil.copytree(finished[1], later)
    (later / "stop").touch()
    assert cli(["drawings", str(later), "--backend", "cpu"]) == runner.EXIT_STOPPED
    assert not (later / "stop").exists()
    assert not (later / PIXEL_DIR / "depth_drawing.tif").exists()
    assert "hazard_classes" not in _layers(later)
    assert not list((later / PIXEL_DIR).glob("*.tmp.*"))


def test_drawings_make_the_layers_too_on_a_run_that_has_none(finished, drawn, tmp_path) -> None:
    """A run made before every run kept its layers: the outline and the setup come with the polygons."""
    later = tmp_path / "run"
    shutil.copytree(finished[1], later)
    (later / PIXEL_DIR / "map_layers.gpkg").unlink()
    assert cli(["drawings", str(later), "--backend", "cpu"]) == 0
    assert _layers(later) == _layers(drawn[1])


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
    """The wadi is wet over its width; on the flat bank tops the rain's own sheet (4.9 cm a cell at its peak in the
    run) shows only where the ground dips under it. W100 changed this on purpose: before, no cell under 5 cm of mean
    depth was mapped, so every wet pixel lay in the wadi; now no cell is cut and a pixel is wet by its own depth."""
    _cfg, run, _summary = finished
    with rasterio.open(run / PIXEL_DIR / step.HAZARD_FILE) as src:
        classes = src.read(1)
        t = src.transform
    with rasterio.open(run / PIXEL_DIR / step.DEPTH_FILE) as src:
        depth = src.read(1)
    assert classes.max() >= 1
    y = t.f + (np.arange(classes.shape[0]) + 0.5) * t.e
    off = np.abs(y - (Y0 - 160.0)) >= 45.0  # 30 m to the bank toe, and the first metres of its rise
    wet = depth != step.NO_DEPTH  # wet by the depth raster: the hazard map leaves water under 0.1 m out (2026-11-16)
    assert wet[~off].mean() > 0.5
    assert wet[off].mean() < 0.05
    assert depth[off][wet[off]].max(initial=0.0) < 0.15
    assert not (classes[off] > 0).any() or depth[off][classes[off] > 0].min() >= 0.1


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
    lossy = 2.0 * cfg.outputs.pixels.max_error_m  # each side within the compression's bound (W100)
    for name, tolerance in ((step.HAZARD_FILE, 0), (step.DEPTH_FILE, 1e-3 + lossy), (step.SPEED_FILE, 1e-3 + lossy)):
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


def test_stop_ends_the_process_at_once(tmp_path) -> None:
    """The dock kills an engine that lingers: a reader thread left behind kept the process from exiting."""
    cfg = wadi_job(tmp_path, map_every_s=60.0)
    run_job(cfg.model_copy(update={"outputs": _pixels_off(cfg)}), tmp_path / "run")
    (tmp_path / "run" / "stop").touch()
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[2])!r})\n"
        "from wadi2d.engine.cli import main\n"
        "sys.exit(main(sys.argv[1:]))\n"
    )
    arguments = ("products", str(tmp_path / "run"), "--backend", "cpu")
    done = subprocess.run((sys.executable, "-c", code, *arguments), capture_output=True, timeout=60, check=False)
    assert done.returncode == runner.EXIT_STOPPED, done.stderr


def test_stopping_between_maps_lets_the_reader_go(tmp_path) -> None:
    cfg = wadi_job(tmp_path, map_every_s=60.0)
    tables, crs = prepare_grid(cfg, tmp_path / "cache")
    run_job(cfg.model_copy(update={"outputs": _pixels_off(cfg)}), tmp_path / "run", tables=(tables, crs))
    before = threading.active_count()
    calls = []

    def after_three_maps() -> bool:
        calls.append(1)
        return len(calls) > len(frame_names(tmp_path / "run" / "results.h5")) // 2

    with pytest.raises(ProductsStopped):
        make_products(cfg, tables, crs, tmp_path / "run", Watch(lambda *_a, **_k: None, after_three_maps), "cpu")
    assert threading.active_count() == before


def test_the_command_line_refuses_a_folder_with_no_run(tmp_path) -> None:
    assert cli(["products", str(tmp_path)]) == runner.EXIT_INVALID


def test_a_window_at_the_dem_pixel_from_the_command_line(finished, tmp_path) -> None:
    """W100, ``wadi2d window``: a drawn window's rasters at the DEM's pixel, into a folder of its own; the run's own
    pixel maps untouched."""
    _cfg, run, _summary = finished
    before = {p.name: p.stat().st_mtime for p in (run / PIXEL_DIR).glob("*.tif")}
    box = [str(v) for v in (X0 + 100.0, Y0 - 250.0, X0 + 400.0, Y0 - 80.0)]
    out = tmp_path / "w"
    assert cli(["window", str(run), *box, "--pixel", "5", "--out", str(out), "--backend", "cpu"]) == 0
    with rasterio.open(out / step.DEPTH_FILE) as src:
        assert src.transform.a == 5.0 and src.width <= 60 and src.height <= 34
        assert (src.read(1) != step.NO_DEPTH).any()
    assert json.loads((out / step.STATS_FILE).read_text("utf-8"))["window"] == [float(v) for v in box]
    assert {p.name: p.stat().st_mtime for p in (run / PIXEL_DIR).glob("*.tif")} == before
    wrong = [box[2], box[1], box[0], box[3]]  # east before west
    assert cli(["window", str(run), *wrong, "--out", str(tmp_path / "x")]) == runner.EXIT_INVALID


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
    summary = run_job(wadi_job(tmp_path, map_every_s=2300.0, pixels={"dv_raster": True}), tmp_path / "coarse")
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


def test_the_setup_of_the_run_goes_into_the_geopackage(drawn) -> None:
    assert {"hazard_classes", "domain", "boundaries"} <= _layers(drawn[1])


def test_products_settings_do_not_refuse_a_checkpoint(tmp_path) -> None:
    cfg = wadi_job(tmp_path)
    other = wadi_job(tmp_path, pixels={"depth_floor": 0.1}, smooth={"sigma_px": 2.0})
    assert job_hash(cfg) == job_hash(other)


def test_the_estimate_says_the_disk_of_the_maps() -> None:
    plain = {"face_discharge": False}
    cfg = RunConfig.model_validate({"run": {"duration_s": 3600.0}, "outputs": {"map_every_s": 900.0, **plain}})
    assert saved_maps(cfg, 1_000_000) == (5, 0.05)
    fine = RunConfig.model_validate({"run": {"duration_s": 3600.0}, "outputs": {"map_every_s": 300.0, **plain}})
    assert saved_maps(fine, 1_000_000) == (13, 0.13)
    faces = RunConfig.model_validate({"run": {"duration_s": 3600.0}, "outputs": {"map_every_s": 900.0}})
    assert saved_maps(faces, 1_000_000) == (5, 0.08)  # the faces, on by default, add 0.6 of a map
    off = RunConfig.model_validate({"outputs": {"map_every_s": 0.0}})
    assert saved_maps(off, 1_000_000) == (0, 0.0)


@pytest.mark.parametrize("size", [8, 13, 64])
def test_windows_paint_what_the_whole_band_paints(size: int) -> None:
    """W50: the rasters are written window by window over the wet ground; together the windows hold exactly what
    the old whole-band spread held, cells cut by a window edge, strip pixels over the cells, empty windows skipped."""
    from wadi2d.products.ground import CellPixels
    from wadi2d.strips.pixels import StripPixelResult

    rng = np.random.default_rng(5)
    k = 5
    rows = np.array([0, 0, 1, 3, 9, 9, 10, 2], np.int32)
    cols = np.array([0, 1, 1, 7, 2, 3, 12, 11], np.int32)
    cells = CellPixels(rows, cols, k, 0.5, 0.0, np.zeros((rows.size, k * k), np.float32))
    values = rng.random((rows.size, k * k)).astype(np.float32)
    sr = np.array([4, 5, 12, 60, 61], np.int64)
    sc = np.array([4, 4, 33, 70, 2], np.int64)
    strip = StripPixelResult(sr, sc, *(np.zeros(sr.size),) * 4)
    dots = rng.random(sr.size).astype(np.float32)
    box = step.pixel_box(cells, strip)
    whole = step.spread(cells, values, -1.0, np.float32, box, strip, dots)
    painted = np.full(whole.shape, -1.0, np.float32)
    seen = 0
    for part in step.window_parts(cells, box, strip, size):
        assert part.row % size == 0 and part.col % size == 0
        tile = part.paint(values[part.cells], dots[part.strip], -1.0, np.float32)
        assert tile.shape == part.shape
        painted[part.row : part.row + tile.shape[0], part.col : part.col + tile.shape[1]] = tile
        seen += 1
    np.testing.assert_array_equal(painted, whole)
    every = -(-box[2] // size) * -(-box[3] // size)
    assert seen < every or size >= box[2]  # the empty windows are not made
