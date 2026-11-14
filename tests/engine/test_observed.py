"""Observed records beside a run's series: the statistics against hand numbers, and the comparison on a run folder."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from wadi2d.config.gauges import Observed
from wadi2d.config.schema import RunConfig
from wadi2d.engine.agreement import agreement
from wadi2d.engine.cli import main
from wadi2d.engine.observed import compare_run
from wadi2d.io.results import write_series_csv

T = np.array([0.0, 60.0, 120.0, 180.0])
OBS = np.array([1.0, 3.0, 5.0, 3.0])
SIM = np.array([1.0, 4.0, 4.0, 3.0])


def test_the_statistics_by_hand() -> None:
    found = agreement(T, OBS, T, SIM)
    # errors 0, 1, -1, 0; mean of o is 3, spread 4 + 0 + 4 + 0 = 8
    assert found.nse == pytest.approx(1.0 - 2.0 / 8.0)
    assert found.rsr == pytest.approx(np.sqrt(2.0 / 8.0))
    assert found.rmse == pytest.approx(np.sqrt(2.0 / 4.0))
    assert found.pbias_percent == pytest.approx(0.0)
    assert (found.observed_peak, found.observed_peak_t_s) == (5.0, 120.0)
    assert (found.simulated_peak, found.simulated_peak_t_s) == (4.0, 60.0)  # a tie: the first
    assert found.peak_shift_s == -60.0
    # trapezoids: (1+3)/2 + (3+5)/2 + (5+3)/2 = 10 per 60 s; (1+4)/2 + 4 + (4+3)/2 = 10
    assert found.observed_volume_m3 == pytest.approx(600.0)
    assert found.simulated_volume_m3 == pytest.approx(600.0)
    assert found.volume_ratio == pytest.approx(1.0)


def test_a_model_twice_too_high_has_a_bias_of_plus_100() -> None:
    found = agreement(T, OBS, T, 2.0 * OBS)
    assert found.pbias_percent == pytest.approx(100.0)
    assert found.peak_ratio == pytest.approx(2.0)


def test_the_simulated_series_is_read_at_the_observed_instants() -> None:
    # simulated every 30 s, a straight rise: at 45 s it reads 4.5
    t_sim = np.arange(0.0, 181.0, 30.0)
    found = agreement(np.array([45.0, 105.0, 165.0]), np.array([4.5, 10.5, 16.5]), t_sim, t_sim / 10.0)
    assert found.rmse == pytest.approx(0.0, abs=1e-12)
    assert found.window_s == (45.0, 165.0)
    assert found.simulated_peak == pytest.approx(16.5)  # cut at the window's end, not the run's


def test_observed_instants_outside_the_run_and_gaps_are_left_out() -> None:
    found = agreement(
        np.array([-60.0, 0.0, 60.0, 120.0, 600.0]), np.array([9.0, 1.0, np.nan, 5.0, 9.0]), T, OBS
    )
    assert found.points == 2
    with pytest.raises(ValueError, match="only 1 observed values"):
        agreement(np.array([0.0, 900.0]), np.array([1.0, 1.0]), T, OBS)


def test_a_level_has_no_volume() -> None:
    found = agreement(T, OBS + 100.0, T, SIM + 100.0, volumes=False)
    assert found.observed_volume_m3 is None
    assert found.nse == pytest.approx(0.75)


def run_folder(tmp_path: Path, observed: list[dict], **storm) -> Path:
    run = tmp_path / "run"
    cfg = RunConfig.model_validate(
        {
            "grid": {"dx": 10.0, "extent": (0.0, 0.0, 100.0, 100.0)},
            "terrain": {"dem": "dem.tif"},
            "storm": storm or {"kind": "none"},
            "outputs": {
                "lines": [{"name": "gauge line", "coordinates": [[0, 0], [10, 10]]}],
                "points": [{"name": "P", "x": 5.0, "y": 5.0}],
                "observed": observed,
            },
        }
    )
    run.mkdir()
    (run / "config.resolved.json").write_text(cfg.model_dump_json(), encoding="utf-8")
    write_series_csv(run / "series" / "line_gauge_line.csv", T, {"discharge_m3s": -SIM})
    write_series_csv(
        run / "series" / "point_P.csv", T, {"depth_m": SIM, "mean_depth_m": SIM, "level_m": SIM + 50.0}
    )
    write_series_csv(run / "series" / "network_S1.csv", T, {"inflow_m3s": SIM, "outflow_m3s": 2.0 * SIM})
    return run


def test_a_run_folder_compares_a_line_a_point_and_an_element(tmp_path) -> None:
    flow = tmp_path / "flow.csv"
    flow.write_text("minute,Q\n0,1\n1,3\n2,5\n3,3\n", encoding="utf-8")
    level = tmp_path / "level.csv"
    level.write_text("minute,H\n0,1\n1,3\n2,5\n3,3\n", encoding="utf-8")
    observed = [
        {"name": "Q at the line", "file": str(flow), "target": "gauge line"},
        {
            "name": "H",
            "file": str(level),
            "quantity": "level",
            "compare": "point",
            "target": "P",
            "offset": 50.0,
        },
        {"name": "Q of S1", "file": str(flow), "compare": "element", "target": "S1"},
        {"name": "broken", "file": str(flow), "target": "no such line"},
    ]
    run = run_folder(tmp_path, observed)
    report = compare_run(run)
    by_name = {r["name"]: r for r in report["records"]}
    assert by_name["Q at the line"]["nse"] == pytest.approx(0.75)  # the line's negative sign read as a size
    assert by_name["H"]["nse"] == pytest.approx(0.75) and by_name["H"]["observed_volume_m3"] is None
    assert by_name["Q of S1"]["peak_ratio"] == pytest.approx(8.0 / 5.0)
    assert report["failed"][0]["name"] == "broken"
    written = json.loads((run / "observed" / "statistics.json").read_text(encoding="utf-8"))
    assert "nse" in written["formulas"] and len(written["records"]) == 3
    pair = (run / "observed" / "Q_at_the_line.csv").read_text(encoding="utf-8").splitlines()
    assert pair[0] == "t_s,date,observed,simulated" and pair[2].endswith(",3,4")


def test_dates_need_the_runs_start_and_take_it_from_the_record_or_the_storm(tmp_path) -> None:
    flow = tmp_path / "flow.csv"
    flow.write_text(
        "time,Q\n2021-10-04 06:00,1\n2021-10-04 06:01,3\n2021-10-04 06:02,5\n2021-10-04 06:03,3\n",
        encoding="utf-8",
    )
    run = run_folder(tmp_path, [{"name": "Q", "file": str(flow), "target": "gauge line"}])
    assert "has dates and the run's start has none" in compare_run(run)["failed"][0]["reason"]
    (run / "rain_gauges.json").write_text(json.dumps({"start": "2021-10-04T06:00:00"}), encoding="utf-8")
    record = compare_run(run)["records"][0]
    assert record["nse"] == pytest.approx(0.75) and record["start"] == "2021-10-04T06:00:00"
    late = Observed(name="Q", file=str(flow), target="gauge line", start="2021-10-04 06:01")
    assert compare_run(run, [late])["records"][0]["points"] == 3  # 06:00 is now a minute before the run


def test_the_command_compares_a_new_observed_file_with_no_rerun(tmp_path, capsys) -> None:
    run = run_folder(tmp_path, [])
    (tmp_path / "flow.csv").write_text("0,1\n1,3\n2,5\n3,3\n", encoding="utf-8")
    listing = tmp_path / "observed.json"
    listing.write_text(
        json.dumps([{"name": "Q", "file": "flow.csv", "target": "gauge line"}]), encoding="utf-8"
    )
    assert main(["compare", str(run), "--observed", str(listing)]) == 0
    assert json.loads(capsys.readouterr().out)["records"] == 1
    assert json.loads((run / "observed" / "statistics.json").read_text(encoding="utf-8"))["records"][0][
        "nse"
    ] == pytest.approx(0.75)
