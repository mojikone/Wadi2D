# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The fake engine speaks the protocol, and the plugin's pure half reads it, without QGIS."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from wadi2d_qgis.progress import ProgressTail, RunState, read_state
from wadi2d_qgis.protocol import (
    EXIT_FINISHED,
    PROGRESS_FILE,
    STOP_FILE,
    engine_error_text,
    estimate_text,
    parse_estimate,
    run_args,
)

JOB = {"grid": {"dx": 20.0}, "run": {"duration_s": 3600.0}}


def engine(fake: Path, args: list[str], mode: str = "ok") -> subprocess.CompletedProcess:
    env = {**os.environ, "WADI2D_FAKE_MODE": mode, "WADI2D_FAKE_STEP_S": "0.001"}
    return subprocess.run([sys.executable, str(fake), *args], env=env, capture_output=True, text=True)


@pytest.fixture
def job(tmp_path: Path) -> Path:
    path = tmp_path / "job.json"
    path.write_text(json.dumps(JOB), "utf-8")
    return path


def test_schema_and_doctor_answer_json(fake_engine: Path) -> None:
    assert "properties" in json.loads(engine(fake_engine, ["schema"]).stdout)
    assert json.loads(engine(fake_engine, ["doctor"]).stdout)["engine"] == "fake"


def test_a_good_run_ends_at_100_percent_with_maps(fake_engine: Path, job: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = engine(fake_engine, run_args(job, out))
    assert result.returncode == EXIT_FINISHED
    state = read_state(out)
    assert state.finished
    assert state.succeeded
    assert state.percent == 100
    assert state.wet_cells == 24
    assert state.warnings
    with rasterio.open(out / "maps" / "max_depth.tif") as raster:
        assert raster.crs.to_epsg() == 32640
        assert raster.bounds.left == 400000.0
        assert raster.read(1).dtype == np.float32
    assert sorted(p.stem for p in (out / "maps").glob("*.tif"))[0] == "arrival"


def test_the_live_raster_is_rewritten_in_place_and_stays_readable(
    fake_engine: Path, job: Path, tmp_path: Path
) -> None:
    out = tmp_path / "run"
    engine(fake_engine, run_args(job, out))
    with rasterio.open(out / "live" / "depth.tif") as raster:
        assert raster.read(1)[0, 0] == 8.0


def test_a_dry_run_gives_cells_memory_and_time(fake_engine: Path, job: Path, tmp_path: Path) -> None:
    result = engine(fake_engine, run_args(job, tmp_path / "run", dry_run=True))
    assert estimate_text(parse_estimate(result.stdout)) == "48 cells, 1.25 GB, about 4 min"


def test_an_invalid_job_exits_2_with_the_reason(fake_engine: Path, job: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = engine(fake_engine, run_args(job, out), "refuse")
    assert result.returncode == 2
    assert not (out / PROGRESS_FILE).exists()
    assert "multiple of the DEM pixel" in engine_error_text(result.stderr)


def test_a_numerical_failure_names_the_cell(fake_engine: Path, job: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    assert engine(fake_engine, run_args(job, out), "error").returncode == 5
    state = read_state(out)
    assert state.finished
    assert state.error_xy == (400070.0, 2699950.0)


def test_a_crash_leaves_no_progress_file_and_exit_1(fake_engine: Path, job: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = engine(fake_engine, run_args(job, out), "crash")
    assert result.returncode == 1
    assert "before the first event" in result.stderr
    assert not (out / PROGRESS_FILE).exists()


def test_the_stop_file_stops_the_run_with_exit_6(fake_engine: Path, job: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    out.mkdir()
    (out / STOP_FILE).touch()
    assert engine(fake_engine, run_args(job, out)).returncode == 6
    assert not (out / STOP_FILE).exists()
    assert read_state(out).exit_code == 6


def test_the_tail_follows_a_run_while_it_runs(fake_engine: Path, job: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    env = {**os.environ, "WADI2D_FAKE_STEP_S": "0.02"}
    process = subprocess.Popen([sys.executable, str(fake_engine), *run_args(job, out)], env=env)
    tail = ProgressTail(out / PROGRESS_FILE)
    state = RunState()
    kinds: list[str] = []
    while process.poll() is None or not state.finished:
        for event in tail.poll():
            state.apply(event)
            kinds.append(event["ev"])
    assert kinds[0] == "start"
    assert kinds[-1] == "done"
    assert kinds.count("step") == 8
