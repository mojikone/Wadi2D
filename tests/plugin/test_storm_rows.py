"""The dock's storm as plain values: the job it writes, what it refuses, what it says about a rain file."""

from __future__ import annotations

import pytest
from wadi2d_qgis.job_builder import build_job, merge_hms, notes, preview_job, problems
from wadi2d_qgis.storm_rows import (
    pasted_rows,
    rain_args,
    rain_reply,
    rain_text,
    storm_job,
    storm_notes,
    storm_problems,
)

from wadi2d.config.schema import RunConfig, Storm

TABLE = {"kind": "hyetograph", "rows": [(30.0, 10.0), (60.0, 25.0)]}
DESIGN = {
    "kind": "hypothetical", "depth_mm": 100.0, "hours": 24.0, "pattern": [(0.0, 0.0), (50.0, 70.0), (100.0, 100.0)],
    "area_km2": 200.0, "arf": [(10.0, 0.95), (1000.0, 0.7)],
}  # fmt: skip


def grid(tmp_path, **extra) -> dict:
    path = tmp_path / "rain.nc"
    path.write_bytes(b"x")
    return {"kind": "gridded", "file": str(path), "units": "auto", "interval_min": 0.0, "stamp": "end", **extra}


def test_pasted_rows_take_tabs_commas_and_spaces_and_leave_headings_out() -> None:
    text = "Time\tDepth\n30\t10\n60,25\n90 5.5\nbad line\n120\n"
    assert pasted_rows(text) == [(30.0, 10.0), (60.0, 25.0), (90.0, 5.5)]


def test_a_hyetograph_goes_into_the_job_the_engine_takes() -> None:
    job = storm_job(TABLE)
    assert job == {"kind": "hyetograph", "hyetograph_min": [30.0, 60.0], "hyetograph_mm": [10.0, 25.0]}
    assert Storm(**job).kind == "hyetograph"


def test_a_design_storm_carries_its_pattern_and_area_reduction() -> None:
    job = storm_job(DESIGN)
    storm = Storm(**job)
    assert storm.duration_min == 1440.0
    assert storm.storm_area_km2 == 200.0
    assert storm.arf.factors == [0.95, 0.7]


def test_a_design_storm_without_a_table_has_no_area() -> None:
    job = storm_job({**DESIGN, "arf": []})
    assert "arf" not in job and "storm_area_km2" not in job


def test_gridded_rain_writes_only_what_the_user_set(tmp_path) -> None:
    job = storm_job(grid(tmp_path))
    assert set(job) == {"kind", "rain_file", "rain_units", "rain_stamp"}
    full = storm_job(grid(tmp_path, variable="pr", interval_min=30.0, start="2021-10-03 06:00"))
    assert full["rain_variable"] == "pr"
    assert full["rain_interval_min"] == 30.0
    assert Storm(**full).rain_start == "2021-10-03 06:00"


def test_problems_are_said_in_plain_words(tmp_path) -> None:
    assert storm_problems({"kind": "hyetograph", "rows": []}) == ["Fill the hyetograph table."]
    assert "rise" in storm_problems({"kind": "hyetograph", "rows": [(30.0, 1.0), (30.0, 1.0)]})[0]
    assert "some rain" in storm_problems({"kind": "hyetograph", "rows": [(30.0, 0.0)]})[0]
    assert storm_problems(DESIGN) == []
    assert "depth and a duration" in storm_problems({**DESIGN, "depth_mm": 0.0})[0]
    assert "0 to 100" in storm_problems({**DESIGN, "pattern": [(0.0, 0.0), (90.0, 100.0)]})[0]
    assert "storm area" in storm_problems({**DESIGN, "area_km2": 0.0})[0]
    assert "must rise" in storm_problems({**DESIGN, "arf": [(10.0, 0.9), (5.0, 0.8)]})[0]
    assert storm_problems(grid(tmp_path)) == []
    assert "Choose the rain file" in storm_problems({**grid(tmp_path), "file": ""})[0]
    assert "not there" in storm_problems({**grid(tmp_path), "file": str(tmp_path / "no.nc")})[0]
    assert "length of each period" in storm_problems({**grid(tmp_path), "file": str(tmp_path)})[0]
    assert "which series" in storm_problems(grid(tmp_path, choices=["a", "b"]))[0]


def test_rain_past_the_end_of_the_run_gets_a_note() -> None:
    assert storm_notes(TABLE, 0.5)
    assert not storm_notes(TABLE, 2.0)
    assert storm_notes(DESIGN, 12.0)


def test_rain_args_say_how_to_read_the_file(tmp_path) -> None:
    args = rain_args(grid(tmp_path, variable="pr", interval_min=30.0, start="2021-10-03"))
    assert args[0] == "rain"
    assert args[args.index("--variable") + 1] == "pr"
    assert args[args.index("--interval-min") + 1] == "30"
    assert args[args.index("--start") + 1] == "2021-10-03"
    assert "--variable" not in rain_args(grid(tmp_path))


def test_the_rain_answer_is_found_among_the_dss_library_log() -> None:
    log = "12:01:00 -----DSS---zopen File"
    assert rain_reply(f'{log}\n{{"frames": 4}}\n{log}\n') == {"frames": 4}
    with pytest.raises(ValueError, match="no answer"):
        rain_reply(f"{log}\n")


def test_rain_text_warns_about_what_matters() -> None:
    info = {
        "frames": 48, "period_min": 30.0, "duration_min": 1440.0, "start": "2021-10-03T00:00:00", "columns": 12,
        "rows": 9, "mean_mm": 80.04, "max_mm": 233.2, "crs": "", "missing": 0.02, "cumulative": True,
    }  # fmt: skip
    text = rain_text(info)
    assert "48 frames of 30 min, 24 h, from 2021-10-03 00:00:00" in text
    assert "80.0 mm on average" in text
    assert "in the DEM's" in text
    assert "2.0%" in text
    assert "start of a forecast" in text
    assert "choose one" in rain_text({"frames": 0, "choices": ["a", "b"]})


def values(tmp_path, **extra) -> dict:
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"x")
    return {
        "dem": str(dem), "crs": "EPSG:32640", "dx": 10.0, "manning": 0.04, "duration_h": 2.0, "output": str(tmp_path),
        "extent": (0.0, 0.0, 100.0, 100.0), **extra,
    }  # fmt: skip


def test_build_job_writes_the_storm_section_and_the_engine_validates_it(tmp_path) -> None:
    job = build_job(values(tmp_path, storm=TABLE), tmp_path / "run")
    assert RunConfig.model_validate(job).storm.kind == "hyetograph"
    assert problems(values(tmp_path, storm=TABLE)) == []


def test_steady_rain_writes_the_same_job_as_before(tmp_path) -> None:
    job = build_job(values(tmp_path, rain_mm_h=10.0, rain_hours=2.0), tmp_path / "run")
    assert job["storm"] == {"kind": "uniform", "depth_mm": 20.0, "duration_min": 120.0}


def test_an_hms_project_keeps_its_storm_unless_the_section_replaced_it(tmp_path) -> None:
    hms = {"basin": "b", "met": "m", "control": "c", "folder": "f", "modes": {}}
    imported = {"storm": {"kind": "hypothetical"}, "run": {"duration_s": 3600.0}, "hydrology": {}}
    own = build_job(values(tmp_path, hms=hms), tmp_path / "a")
    assert "storm" not in own
    assert merge_hms(own, imported, hms)["storm"] == {"kind": "hypothetical"}
    assert problems(values(tmp_path, hms=hms)) == []
    replaced = build_job(values(tmp_path, hms=hms, storm=TABLE), tmp_path / "b")
    assert merge_hms(replaced, imported, hms)["storm"]["kind"] == "hyetograph"
    steady = {"kind": "uniform", "mm_h": 5.0, "hours": 2.0}
    merged = merge_hms(build_job(values(tmp_path, hms=hms, storm=steady), tmp_path / "c"), imported, hms)
    assert merged["storm"] == {"kind": "uniform", "depth_mm": 10.0, "duration_min": 120.0}


def test_no_rain_at_all_is_still_refused_in_the_old_words(tmp_path) -> None:
    assert "Set the rain, or choose an HMS project." in problems(values(tmp_path))
    assert "Set how many hours the rain lasts." in problems(values(tmp_path, rain_mm_h=5.0))


def test_notes_follow_the_storm_section(tmp_path) -> None:
    found = notes(values(tmp_path, duration_h=0.5, storm=TABLE))
    assert any("outlasts" in note for note in found)


def test_a_preview_carries_no_storm(tmp_path) -> None:
    assert "storm" not in preview_job(values(tmp_path, storm=TABLE), tmp_path / "p")
