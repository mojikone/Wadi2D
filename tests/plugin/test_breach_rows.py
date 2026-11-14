"""The dam breach table of the dock, without Qt, and the job it makes (W63 in the dock, W68)."""

from __future__ import annotations

from pathlib import Path

from wadi2d_qgis.breach_rows import (
    REFUSAL,
    TRIGGER_HELD,
    TRIGGER_TIME,
    BreachRow,
    breach_jobs,
    breach_problems,
)
from wadi2d_qgis.dam_rows import DamRow
from wadi2d_qgis.job_builder import Feature, build_job, problems

from tests.plugin.test_contract import full_values
from wadi2d.config import schema as config

LINE = [[400000.0, 2700000.0], [400100.0, 2700050.0]]


def _row(**changes) -> BreachRow:
    base = {"dam": "Dam A", "bottom_z": 498.0, "width_m": 16.0, "slope": 1.0, "formation_min": 5.0, "value": 503.0}
    return BreachRow(**{**base, **changes})


def _values(tmp_path: Path, rows: list[BreachRow], **changes) -> dict:
    crest = [Feature("LineString", LINE, {"crest_z": 512.0, "name": "Dam A"})]
    structures = {"crest_line": crest}
    return full_values(tmp_path, structures=structures, dam_rows=[DamRow("Dam A")], breach_rows=rows, **changes)


def test_a_row_reaches_the_job_in_the_engines_units_and_the_engine_takes_it(tmp_path: Path) -> None:
    rows = [_row(), _row(trigger=TRIGGER_TIME, value=2.5, progression="sine"), _row(trigger=TRIGGER_HELD, held_min=30.0)]
    rows.append(_row(mode="piping", piping_z=500.0))
    job = build_job(_values(tmp_path, rows), tmp_path / "out")
    parsed = config.RunConfig.model_validate(job)
    first, timed, held, pipe = parsed.breaches
    assert first.dam == "Dam A" and first.trigger == "level" and first.trigger_level == 503.0
    assert first.formation_time_s == 300.0 and first.left_slope == first.right_slope == 1.0
    assert first.bottom_width_m == 16.0 and first.station_m is None and first.estimator is None
    assert timed.trigger_time_s == 9000.0 and timed.progression == "sine" and timed.trigger_level is None
    assert held.trigger_duration_s == 1800.0
    assert pipe.mode == "piping" and pipe.piping_z == 500.0
    plain = config.RunConfig.model_validate(build_job(full_values(tmp_path), tmp_path / "plain"))
    assert plain.breaches == []


def test_what_is_missing_stops_the_run_in_words() -> None:
    dams = ["Dam A"]
    assert breach_problems([], dams, {"mesh": {"x": 1}}) == []
    assert breach_problems([_row(dam="Gone")], dams, {}) == [
        "Breach Gone: choose a named crest line or embankment of the Structures layers."
    ]
    (said,) = breach_problems([_row(bottom_z=None, trigger=TRIGGER_HELD, mode="piping")], dams, {})
    assert said == "Breach of Dam A: type the final bottom, how long the level is held, the pipe's centre."
    assert breach_problems([_row(mode="piping", piping_z=490.0)], dams, {}) == [
        "Breach of Dam A: the pipe's centre lies below the final bottom."
    ]
    assert breach_jobs([_row(trigger=TRIGGER_TIME, value=None)])[0]["trigger_time_s"] is None


def test_the_mesh_the_corridors_and_local_steps_are_refused_before_the_run(tmp_path: Path) -> None:
    rows = [_row()]
    found = breach_problems(rows, ["Dam A"], {"mesh": {"near": 1}, "strips": {"banks": "b"}, "local_steps": True})
    assert found == [REFUSAL["mesh"], REFUSAL["strips"], REFUSAL["local_steps"]]
    assert REFUSAL["local_steps"] in problems(_values(tmp_path, rows, output="o", local_steps=True))
    assert not [text for text in problems(_values(tmp_path, rows, output="o")) if "breach" in text.lower()]
