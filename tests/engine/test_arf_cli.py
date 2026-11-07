"""The depth-area study and the command line."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

from tests.engine.conftest import CRS, X0, Y0, job, tilted_box, write_dem
from wadi2d.arf import arf_study, composite_map, interpolate_peak, storm_areas
from wadi2d.config.schema import RunConfig
from wadi2d.engine.cli import main


def test_log_interpolation_between_runs():
    areas = np.array([10.0, 100.0])
    peaks = np.array([1000.0, 100.0])
    assert interpolate_peak(areas, peaks, 31.6227766) == pytest.approx(316.22776, rel=1e-4)
    assert interpolate_peak(areas, peaks, 5.0) == pytest.approx(1000.0)
    assert interpolate_peak(areas, peaks, 500.0) == pytest.approx(100.0)
    assert interpolate_peak(areas, np.zeros(2), 50.0) == 0.0


def test_storm_areas_log_spaced_and_exact_members():
    cfg = job("x.tif", 8, 8, 4.0, arf={"n_areas": 3, "area_min_km2": 10.0, "area_max_km2": 1000.0})
    assert storm_areas(cfg) == pytest.approx([10.0, 100.0, 1000.0])
    exact = job(
        "x.tif", 8, 8, 4.0, arf={"areas_km2": [10.0, 100.0], "exact_points": True},
        outputs={"lines": [{"name": "a", "coordinates": [(0.0, 0.0), (1.0, 0.0)], "drainage_area_km2": 33.0}]},
    )  # fmt: skip
    assert storm_areas(exact) == [10.0, 33.0, 100.0]


def test_composite_reads_each_cell_between_its_runs():
    maps = [np.full((1, 3), 2.0), np.full((1, 3), 1.0)]
    out = composite_map(maps, np.array([10.0, 1000.0]), np.array([[1.0, 100.0, 5000.0]]))
    np.testing.assert_allclose(out, [[2.0, 1.5, 1.0]])


@pytest.fixture
def arf_job(tmp_path) -> RunConfig:
    dem = write_dem(tmp_path / "t.tif", tilted_box(64, 32, 2.0, 0.02), 2.0)
    with rasterio.open(
        tmp_path / "accum.tif", "w", driver="GTiff", height=8, width=16, count=1, dtype="float32", nodata=-1.0,
        crs=CRS, transform=Affine(8.0, 0.0, X0, 0.0, -8.0, Y0),
    ) as dst:  # fmt: skip
        a = np.tile(np.linspace(1e4, 2e7, 16, dtype=np.float32), (8, 1))
        dst.write(a, 1)
    return job(
        dem,
        32,
        16,
        4.0,
        storm={
            "kind": "uniform", "depth_mm": 60.0, "duration_min": 10.0,
            "arf": {"areas_km2": [1.0, 1000.0], "factors": [1.0, 0.5], "table_type": "storm-centred ratio"},
        },
        boundaries=[{"kind": "free", "coordinates": [(X0 + 126.0, Y0), (X0 + 126.0, Y0 - 64.0)]}],
        run={"duration_s": 1500.0, "source_every_s": 30.0},
        arf={"areas_km2": [10.0, 900.0], "accumulation": str(tmp_path / "accum.tif")},
        outputs={
            "lines": [
                {"name": "Outlet", "coordinates": [(X0 + 100.0, Y0), (X0 + 100.0, Y0 - 64.0)], "drainage_area_km2": 100.0}
            ],
            "series_every_s": 10.0,
        },
    )  # fmt: skip


def test_arf_study_end_to_end(arf_job, tmp_path):
    out = tmp_path / "study"
    study = arf_study(arf_job, out)
    assert study.exit_code == 0, [r.message for r in study.runs]
    assert study.areas_km2 == [10.0, 900.0]
    assert len(list((out / "runs").iterdir())) == 2
    for run in (out / "runs").iterdir():
        assert (run / "maps" / "max_depth.tif").is_file()
    assert not any((run / "cache").exists() for run in (out / "runs").iterdir()), "the grid is shared"

    rows = list(csv.DictReader((out / "design_points.csv").open(encoding="utf-8")))
    assert len(rows) == 1
    row = rows[0]
    assert row["arf_table_type"] == "storm-centred ratio"
    low, high = float(row["peak_low_m3s"]), float(row["peak_high_m3s"])
    assert low > high > 0.0, "a larger storm area rains less"
    assert high < float(row["design_peak_m3s"]) < low

    assert study.composite["max_depth"].is_file()
    with rasterio.open(study.composite["max_depth"]) as src:
        assert src.tags()["arf_table_type"] == "storm-centred ratio"
        depth = src.read(1, masked=True)
    assert depth.max() > 0.0


def test_a_study_names_each_run_and_its_folder_before_it_starts(arf_job, tmp_path):
    """The dock follows the run in progress through its own progress file, so the study says where it is."""
    out = tmp_path / "study"
    arf_study(arf_job, out)
    events = [json.loads(s) for s in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    kinds = [(e["ev"], e.get("kind")) for e in events]
    runs = [e for e in events if e["ev"] == "run"]
    assert [(e["index"], e["of"], e["area_km2"]) for e in runs] == [(1, 2, 10.0), (2, 2, 900.0)]
    for event in runs:
        assert (out / event["folder"] / "progress.jsonl").is_file()
    first = kinds.index(("run", None))
    assert kinds.index(("start", None)) < first < kinds.index(("output", "run"))


def test_a_study_stopped_before_its_first_run_writes_no_table(arf_job, tmp_path):
    out = tmp_path / "study"
    out.mkdir()
    (out / "stop").touch()
    study = arf_study(arf_job, out)
    assert study.exit_code == 6
    assert not (out / "design_points.csv").exists()
    assert not (out / "stop").exists()
    done = json.loads((out / "progress.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert done["ev"] == "done" and done["status"] == "stopped" and done["runs"] == 0


def test_schema_prints_json(capsys):
    assert main(["schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert "storm" in schema["properties"]


def test_light_commands_never_import_cupy(tmp_path):
    code = (
        "import sys, json, io, contextlib\n"
        "from wadi2d.engine.cli import main\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    assert main(['schema']) == 0\n"
        "    assert main(['doctor']) == 0\n"
        "print('cupy' in sys.modules)\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert done.stdout.strip() == "False"


def test_run_and_dry_run_through_the_cli(tilted_dem, tmp_path, capsys):
    data = job(
        tilted_dem, 50, 24, 4.0, storm={"kind": "uniform", "depth_mm": 10.0, "duration_min": 2.0},
        run={"duration_s": 200.0},
    ).model_dump(mode="json")  # fmt: skip
    path = tmp_path / "job.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert main(["run", str(path), "--out", str(tmp_path / "dry"), "--backend", "cpu", "--dry-run"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["cells"] == 50 * 24
    assert report["wall_s"] > 0.0
    assert report["ns_per_cell_step"] > 0.0
    assert report["device_gb"] > 0.0
    assert not (tmp_path / "dry").exists()
    assert main(["run", str(path), "--out", str(tmp_path / "run"), "--backend", "cpu"]) == 0
    events = [json.loads(s) for s in capsys.readouterr().out.splitlines()]
    assert events[-1]["ev"] == "done"


def test_cli_exit_codes(tmp_path, capsys):
    missing = tmp_path / "none.json"
    assert main(["run", str(missing), "--out", str(tmp_path / "o")]) == 3
    bad = tmp_path / "bad.json"
    bad.write_text('{"nonsense": 1}', encoding="utf-8")
    assert main(["run", str(bad), "--out", str(tmp_path / "o")]) == 2
    capsys.readouterr()


@pytest.mark.data
def test_hms_import_makes_a_valid_job(hms_project_dir: Path, tmp_path):
    out = tmp_path / "job.json"
    assert main(
        ["hms-import", str(hms_project_dir), "--basin", "Basin_1.basin", "--met", "FM_100yr.met",
         "--control", "Control_1.control", "--out", str(out)]
    ) == 0  # fmt: skip
    cfg = RunConfig.model_validate_json(out.read_text(encoding="utf-8"))
    assert cfg.storm.kind == "hypothetical"
    assert len(cfg.hydrology.subbasins) == 18
    assert cfg.storm.arf is not None
    assert cfg.run.duration_s > 3600.0


def test_a_study_runs_without_pixel_maps_even_when_its_job_has_them_on(arf_job, tmp_path):
    """Its runs are many and it reads the cell maps: the pixel maps belong to the run chosen after it."""
    outputs = arf_job.outputs.model_copy(update={"map_every_s": 600.0})
    arf_study(arf_job.model_copy(update={"outputs": outputs}), tmp_path / "study")
    runs = list((tmp_path / "study" / "runs").iterdir())
    assert runs
    assert not any((run / "pixels").exists() for run in runs)
