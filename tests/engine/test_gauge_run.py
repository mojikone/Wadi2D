"""Rain gauges through the whole pipeline, in a closed box where the water must equal the rain (W54)."""

from __future__ import annotations

import json

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.run import job_hash, run_job

SIDE = 32
DX = 4.0
WIDTH = SIDE * DX
AREA = WIDTH**2
QUICK = {"duration_s": 1800.0, "source_every_s": 60.0}


def box(tmp_path):
    return write_dem(tmp_path / "flat.tif", np.full((SIDE * 2, SIDE * 2), 100.0), 2.0)


def record(tmp_path, name: str, mm_per_10min: float) -> str:
    path = tmp_path / f"{name}.csv"
    path.write_text("minute,mm\n" + "".join(f"{m},{mm_per_10min}\n" for m in (10, 20, 30)), encoding="utf-8")
    return str(path)


def gauges(tmp_path, west: float, east: float, **rain) -> dict:
    """A gauge a quarter of the way in from each side, on the box's middle row."""
    y = Y0 - WIDTH / 2.0
    listed = [
        {
            "name": "W",
            "x": X0 + WIDTH / 4.0,
            "y": y,
            "file": record(tmp_path, "W", west),
            "interval_min": 10.0,
        },
        {
            "name": "E",
            "x": X0 + 3.0 * WIDTH / 4.0,
            "y": y,
            "file": record(tmp_path, "E", east),
            "interval_min": 10.0,
        },
    ]
    return {"kind": "gauges", "gauges": {"gauges": listed, **rain}}


def test_one_steady_gauge_runs_as_the_uniform_storm_it_equals(tmp_path) -> None:
    dem = box(tmp_path)
    uniform = run_job(
        job(
            dem, SIDE, SIDE, DX, storm={"kind": "uniform", "depth_mm": 30.0, "duration_min": 30.0}, run=QUICK
        ),
        tmp_path / "u",
    )
    one = {"kind": "gauges", "gauges": {"gauges": [gauges(tmp_path, 10.0, 10.0)["gauges"]["gauges"][0]]}}
    run = run_job(job(dem, SIDE, SIDE, DX, storm=one, run=QUICK), tmp_path / "g")
    assert run.exit_code == uniform.exit_code == 0
    assert run.balance.rain == pytest.approx(uniform.balance.rain, rel=1e-6)
    assert run.balance.storage == pytest.approx(uniform.balance.storage, rel=1e-6)


def test_thiessen_puts_each_gauges_rain_on_its_own_half(tmp_path) -> None:
    cfg = job(box(tmp_path), SIDE, SIDE, DX, storm=gauges(tmp_path, 20.0, 5.0), run=QUICK)
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0
    assert run.balance.rain == pytest.approx(0.5 * AREA * (0.060 + 0.015), rel=1e-6)
    assert abs(run.balance.relative) < 1e-4
    written = json.loads((tmp_path / "out" / "rain_gauges.json").read_text(encoding="utf-8"))
    assert written["cell_shares"] == {"W": 0.5, "E": 0.5}
    assert written["gauges"] == {"W": 60.0, "E": 15.0}


def test_inverse_distance_gives_each_half_some_of_the_other_gauges_rain(tmp_path) -> None:
    """The same volume here by symmetry, the halves no longer sharp: the west half's cells hold less than Thiessen's."""
    dem = box(tmp_path)
    near = run_job(job(dem, SIDE, SIDE, DX, storm=gauges(tmp_path, 20.0, 5.0), run=QUICK), tmp_path / "t")
    idw = run_job(
        job(dem, SIDE, SIDE, DX, storm=gauges(tmp_path, 20.0, 5.0, method="inverse_distance"), run=QUICK),
        tmp_path / "i",
    )
    assert idw.balance.rain == pytest.approx(near.balance.rain, rel=1e-3)
    shares = json.loads((tmp_path / "i" / "rain_gauges.json").read_text(encoding="utf-8"))["cell_shares"]
    assert shares["W"] == pytest.approx(0.5, abs=1e-3)


def test_a_run_compares_its_observed_records_when_it_ends(tmp_path) -> None:
    observed = tmp_path / "obs.csv"
    observed.write_text("minute,depth\n0,0\n10,0.01\n20,0.02\n30,0.03\n", encoding="utf-8")
    outputs = {
        "points": [{"name": "P", "x": X0 + WIDTH / 2.0, "y": Y0 - WIDTH / 2.0}],
        "observed": [
            {"name": "depth", "file": str(observed), "quantity": "depth", "compare": "point", "target": "P"}
        ],
    }
    cfg = job(box(tmp_path), SIDE, SIDE, DX, storm=gauges(tmp_path, 10.0, 10.0), run=QUICK, outputs=outputs)
    assert run_job(cfg, tmp_path / "out").exit_code == 0
    stats = json.loads((tmp_path / "out" / "observed" / "statistics.json").read_text(encoding="utf-8"))
    assert stats["records"][0]["nse"] > 0.99  # 10 mm every 10 min on a flat closed box: the depth is the rain
    assert job_hash(cfg) == job_hash(
        cfg.model_copy(update={"outputs": cfg.outputs.model_copy(update={"observed": []})})
    )


def test_a_changed_gauge_record_changes_the_job_hash(tmp_path) -> None:
    cfg = job(box(tmp_path), SIDE, SIDE, DX, storm=gauges(tmp_path, 20.0, 5.0), run=QUICK)
    before = job_hash(cfg)
    record(tmp_path, "E", 6.0)
    assert job_hash(cfg) != before


def test_a_missing_gauge_record_stops_the_run_before_the_grid(tmp_path) -> None:
    storm = gauges(tmp_path, 20.0, 5.0)
    storm["gauges"]["gauges"][1]["file"] = str(tmp_path / "nowhere.csv")
    run = run_job(job(box(tmp_path), SIDE, SIDE, DX, storm=storm, run=QUICK), tmp_path / "out")
    assert run.exit_code != 0
    assert "record of rain gauge E not found" in run.message
