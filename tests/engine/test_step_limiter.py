"""``outputs.step_limiter`` through a whole run (W85): the progress lines, the layer, and nothing when it is off."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
import rasterio

from tests.engine.conftest import X0, Y0, write_dem
from tests.engine.test_run import full_job, valley
from wadi2d.engine.step_limiter import FILE, LAYER
from wadi2d.run import job_hash, run_job

PIT_X, PIT_Y = X0 + 256.0, Y0 - 188.0
DEEP = 12.0
"""A pit 4 m by 8 m and this deep on the valley floor, a pixel column either side of a cell face."""


@pytest.fixture
def pit_dem(tmp_path: Path) -> Path:
    z = valley(256, 192, 2.0)
    z[92:96, 127:129] -= DEEP
    return write_dem(tmp_path / "pit.tif", z, 2.0)


def asking(dem: Path, how: str):
    """The valley job of ``test_run`` with the limiter asked for."""
    cfg = full_job(dem, "cpu", duration=1800.0)
    return cfg.model_copy(update={"outputs": cfg.outputs.model_copy(update={"step_limiter": how})})


def events(out: Path, kind: str) -> list[dict]:
    lines = (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    return [e for e in map(json.loads, lines) if e["ev"] == kind]


def test_the_pit_is_named_in_the_progress_and_in_the_layer(pit_dem, tmp_path):
    out = tmp_path / "on"
    summary = run_job(asking(pit_dem, "layer"), out)
    assert summary.exit_code == 0, summary.message
    named = events(out, "limiter")
    assert named and len(named) <= len(events(out, "step"))
    late = [e for e in named if e["t"] > 1200.0]
    assert late and all(abs(e["x"] - PIT_X) <= 8.0 and abs(e["y"] - PIT_Y) <= 8.0 for e in late)
    assert all(e["dt_without_tile"] >= e["dt_tile"] for e in named)
    made = [e for e in events(out, "output") if e.get("kind") == "step_limiter"]
    assert made and Path(made[0]["path"]) == out / FILE
    with sqlite3.connect(out / FILE) as db:
        rows = db.execute(
            f'SELECT ticks, dt_min_s, depth, bed, hydraulic_depth FROM "{LAYER}" ORDER BY dt_min_s'
        ).fetchall()
    assert sum(r[0] for r in rows) == len(named)
    _ticks, dt_min, depth, bed, hydraulic = rows[0]
    assert dt_min == pytest.approx(min(e["dt_tile"] for e in named))
    assert bed == pytest.approx(
        float(valley(256, 192, 2.0)[92:96, 127:129].min()) - DEEP, abs=0.05
    )  # either cell of the pit
    assert depth > 0.6 * DEEP and hydraulic > 0.0


def test_off_writes_nothing_and_on_changes_no_water(pit_dem, tmp_path):
    off, on = tmp_path / "off", tmp_path / "progress"
    plain = full_job(pit_dem, "cpu", duration=1800.0)
    asked = asking(pit_dem, "progress")
    assert job_hash(plain) == job_hash(asked)
    assert run_job(plain, off).exit_code == 0
    assert run_job(asked, on).exit_code == 0
    assert not events(off, "limiter") and not (off / FILE).exists()
    assert events(on, "limiter") and not (on / FILE).exists()  # 'progress' names the cell and writes no layer
    for name in ("max_depth", "max_speed"):
        with (
            rasterio.open(off / "maps" / f"{name}.tif") as a,
            rasterio.open(on / "maps" / f"{name}.tif") as b,
        ):
            assert np.array_equal(a.read(1), b.read(1)), name
