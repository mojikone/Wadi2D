# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Simulation section (W99 step 4): what the job takes of it, the run's one start, and a saved model of the
format before it brought up in words."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wadi2d_qgis import model_doc, section_status
from wadi2d_qgis import simulation_rows as s
from wadi2d_qgis.gauge_rows import FLOW, GRIDDED, GaugeRow, joined_gauges
from wadi2d_qgis.job_builder import Feature, build_job, merge_notes, problems
from wadi2d_qgis.storm_rows import KIND_GRID

DEFAULTS = {"cfl": 0.45, "dt_max": 5.0, "dt_min": 0.001}
START = "2021-10-04 00:00"


def values(**more) -> dict:
    base = {
        "dem": "dem.tif", "crs": "EPSG:32640", "pixel": 5.0, "dx": 30.0, "manning": 0.045, "duration_h": 2.0,
        "output": "out", "rain_mm_h": 40.0, "rain_hours": 0.5, "map_every_s": 900.0,
        "design": [Feature("LineString", [[10.0, 0.0], [10.0, 90.0]], {"name": "dam"})],
    }  # fmt: skip
    return {**base, **more}


def test_a_model_at_the_defaults_writes_the_job_it_wrote_before(tmp_path: Path) -> None:
    before = build_job(values(), tmp_path)
    assert s.numerics_of(s.STEP_AUTO, 0.5, dict(DEFAULTS), DEFAULTS) == {}
    now = build_job(values(start="", step_bounds=(0.001, 5.0)), tmp_path)
    assert json.dumps(now) == json.dumps(before)  # to the character, key order with it
    assert (
        "numerics" not in now
        and "time_step_min" not in now["hydrology"]
        and "series_every_s" not in now["outputs"]
    )


def test_only_what_left_the_defaults_reaches_the_job(tmp_path: Path) -> None:
    moved = s.numerics_of(s.STEP_AUTO, 0.5, {**DEFAULTS, "cfl": 0.3}, DEFAULTS)
    assert moved == {"cfl": 0.3}
    job = build_job(
        values(numerics=moved, lumped_step_min=2.0, series_every_s=30.0, local_steps=True), tmp_path
    )
    assert job["numerics"] == {"local_time_stepping": True, "cfl": 0.3}
    assert job["hydrology"]["time_step_min"] == 2.0 and job["outputs"]["series_every_s"] == 30.0
    assert (
        job["outputs"]["lines"][0]["name"] == "dam"
    )  # the series interval sits beside the lines, not over them


def test_a_fixed_step_is_both_of_the_engines_bounds(tmp_path: Path) -> None:
    fixed = s.numerics_of(s.STEP_FIXED, 0.25, dict(DEFAULTS), DEFAULTS)
    assert fixed == {"dt_max": 0.25, "dt_min": 0.25} and s.fixed_step(fixed) == 0.25
    assert s.fixed_step({"dt_max": 5.0}) is None and s.fixed_step({"dt_max": 2.0, "dt_min": 0.01}) is None
    assert build_job(values(numerics=fixed), tmp_path)["numerics"] == fixed


def test_the_engine_takes_the_fixed_step_and_refuses_one_over_its_bound(tmp_path: Path) -> None:
    schema = pytest.importorskip("wadi2d.config.schema")
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"")
    domain = [Feature("Polygon", [[[0.0, 0.0], [90.0, 0.0], [90.0, 90.0], [0.0, 0.0]]])]
    fixed = s.numerics_of(s.STEP_FIXED, 0.25, dict(DEFAULTS), DEFAULTS)
    job = build_job(values(dem=str(dem), domain=domain, numerics=fixed), tmp_path / "run")
    numerics = schema.RunConfig.model_validate(job).numerics
    assert (numerics.dt_max, numerics.dt_min) == (0.25, 0.25)
    low, high = (
        schema.Numerics.model_fields["dt_max"].metadata,
        schema.Numerics.model_fields["dt_min"].metadata,
    )
    assert low and high  # the bounds the fixed step's note quotes are the schema's own
    job["numerics"] = {"dt_max": 2.0, "dt_min": 2.0}
    with pytest.raises(
        ValueError, match="dt_min"
    ):  # the engine's own refusal: a smallest step of at most 1 s
        schema.RunConfig.model_validate(job)
    assert (DEFAULTS["cfl"], DEFAULTS["dt_max"], DEFAULTS["dt_min"]) == (
        schema.Numerics().cfl, schema.Numerics().dt_max, schema.Numerics().dt_min,
    )  # fmt: skip


def test_what_stops_a_run_is_said() -> None:
    assert (
        s.start_problem("") == ""
        and s.start_problem(START) == ""
        and s.start_problem("2021-10-04T06:30:00") == ""
    )
    assert s.start_problem("4 October") == s.BAD_START
    assert s.BAD_START in problems(values(start="tomorrow"))
    assert s.STEPS_REVERSED in problems(values(step_bounds=(2.0, 1.0)))
    assert s.simulation_problems(values(start=START, step_bounds=(0.001, 5.0))) == []


def test_the_status_of_the_simulation_section() -> None:
    ready = section_status.simulation(START, 2.25, None, 0.45, 15.0, 5.0, (0.001, 5.0))
    assert ready == (
        section_status.READY,
        f"Starts {START} \N{MIDDLE DOT} 2.25 h \N{MIDDLE DOT} automatic step, Courant 0.45 \N{MIDDLE DOT} maps every 15 min"
        " \N{MIDDLE DOT} lumped step 5 min",
    )
    assert "fixed step 0.25 s" in section_status.simulation("", 1.0, 0.25, 0.45, 5.0, None).words
    lumped_only = section_status.simulation("", 24.0, None, 0.45, None, 5.0)
    assert lumped_only == (section_status.READY, "24 h \N{MIDDLE DOT} lumped step 5 min")
    assert section_status.simulation("soon", 1.0, None, 0.45, 15.0, None) == (
        section_status.MISSING,
        s.BAD_START,
    )
    assert (
        section_status.simulation("", 1.0, None, 0.45, 15.0, None, (2.0, 1.0)).state == section_status.MISSING
    )


def test_the_lumped_step_of_the_form_over_the_hms_control_files_is_said() -> None:
    job = {"run": {"duration_s": 3600.0}, "hydrology": {"time_step_min": 2.0}}
    merged = {"run": {"duration_s": 3600.0}, "hydrology": {"time_step_min": 2.0}}
    said = merge_notes(job, merged, {"hydrology": {"time_step_min": 5.0}})
    assert said == [s.LUMPED_REPLACES.format(own=2.0, theirs=5.0)]
    assert (
        merge_notes(
            {"run": {"duration_s": 3600.0}, "hydrology": {}}, merged, {"hydrology": {"time_step_min": 5.0}}
        )
        == []
    )
    assert merge_notes(job, merged) == []


# The run's one start, where three were


def observed(start: str) -> dict:
    return {"rows": [GaugeRow("g", FLOW, file="q.csv", at="dam")], "start": start}


def test_the_observed_records_read_the_runs_start() -> None:
    assert GRIDDED == KIND_GRID
    plain = joined_gauges({"observed_gauges": observed(START)})
    assert plain["gauges"]["settings"]["observed_start"] == START
    rain = {"rows": [], "settings": {"start": START}}
    gauged = joined_gauges(
        {"storm": {"kind": "gauges"}, "rain_gauges": rain, "observed_gauges": observed(START)}
    )
    assert gauged["gauges"]["settings"]["observed_start"] == START
    gridded = joined_gauges(
        {"storm": {"kind": KIND_GRID, "start": START}, "observed_gauges": observed(START)}
    )
    assert (
        gridded["gauges"]["settings"]["observed_start"] == ""
    )  # the rain file's start carries it: the job as before


# A saved model of format 1 brought up to format 2


def old_doc(kind: str, start: str = "", gauge_start: str = "", observed_start: str = "") -> dict:
    return {
        "format": "wadi2d-model",
        "version": 1,
        "model_type": None,
        "sections": {
            "storm": {"widgets": {"kind": {"data": kind, "text": kind}, "start": start, "gauge_start": gauge_start}},
            "gauges": {"widgets": {"start": observed_start}, "rows": {"gauges": []}},
            "run": {"widgets": {"folder": "out", "duration": 2.25, "maps": {"data": 300.0, "text": "x"},
                                "backend": {"data": "cpu", "text": "CPU only"}, "pixels": False}},
        },
    }  # fmt: skip


def brought_up(doc: dict) -> tuple[dict, list[str]]:
    new = model_doc.loads(json.dumps(doc))
    return {key: section["widgets"] for key, section in new["sections"].items()}, new.get(
        model_doc.MIGRATED, []
    )


def test_runs_three_fields_move_to_simulation_as_they_are() -> None:
    widgets, words = brought_up(old_doc("single"))
    assert widgets["simulation"] == {
        "duration": 2.25,
        "maps": {"data": 300.0, "text": "x"},
        "backend": {"data": "cpu", "text": "CPU only"},
    }
    assert widgets["run"] == {"folder": "out", "pixels": False}
    assert (
        "start" not in widgets["storm"]
        and "gauge_start" not in widgets["storm"]
        and "start" not in widgets["gauges"]
    )
    assert words == []  # nothing of the job changed: nothing to say
    assert model_doc.loads(json.dumps(old_doc("single")))["version"] == model_doc.VERSION == 2


@pytest.mark.parametrize(
    ("kind", "starts", "taken", "said"),
    [
        ("hypothetical", {"observed_start": START}, START, ["took", "observed gauges"]),
        ("gridded", {"start": START}, START, ["took", "the rain"]),
        ("gauges", {"gauge_start": START}, START, ["took", "the rain"]),
        ("gauges", {"gauge_start": START, "observed_start": START}, START, ["took"]),
        (
            "gridded",
            {"start": START, "observed_start": "2021-10-05 00:00"},
            START,
            ["2021-10-05 00:00", "is dropped"],
        ),
        ("gridded", {"observed_start": START}, START, ["The rain now starts there too"]),
        ("hypothetical", {"start": "2020-01-01 00:00"}, None, ["not in use", "2020-01-01 00:00"]),
    ],
)
def test_the_three_starts_become_one_in_words(
    kind: str, starts: dict, taken: str | None, said: list[str]
) -> None:
    widgets, words = brought_up(old_doc(kind, **starts))
    assert widgets["simulation"].get("start") == taken
    text = " ".join(words)
    assert all(part in text for part in said), text
