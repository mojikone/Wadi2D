# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The depth-area study's values, problems, job block and table, without QGIS."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wadi2d_qgis.job_builder import Feature, build_job
from wadi2d_qgis.protocol import STUDY_FILE, next_study_dir, study_args
from wadi2d_qgis.study_rows import (
    ACCUMULATION_WORDS,
    BRACKET,
    LINE_WORDS,
    LISTED,
    SPACED,
    STORM_WORDS,
    TABLE_WORDS,
    areas_text,
    design_lines,
    form_problems,
    on_grid_text,
    parse_areas,
    read_study,
    spaced_areas,
    study_areas,
    study_job,
    study_notes,
    study_problems,
    table_cells,
)

LINE = [[400000.0, 2700000.0], [400100.0, 2700050.0]]


def form(**changes) -> dict:
    base = {
        "spacing": BRACKET, "listed": "", "count": 6, "smallest": 10.0, "largest": 600.0, "composite": False,
        "accumulation": None, "units": "cells",
    }  # fmt: skip
    return {**base, **changes}


def design(*areas) -> list[Feature]:
    lines = [
        Feature("LineString", LINE, {"name": f"L{n}", "drainage_area_km2": a} if a is not None else {"name": f"L{n}"})
        for n, a in enumerate(areas, 1)
    ]
    return [*lines, Feature("Point", [400050.0, 2700010.0], {"name": "P"})]


def values(tmp_path: Path, **changes) -> dict:
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"x")
    base = {
        "dem": str(dem), "crs": "EPSG:32640", "pixel": 0.5, "dx": 20.0, "manning": 0.035,
        "extent": (400000.0, 2699000.0, 401000.0, 2700000.0), "output": str(tmp_path / "out"), "duration_h": 2.0,
        "hms": {"folder": "x", "basin": "b", "met": "m", "control": "c", "modes": {}}, "design": design(20.971),
    }  # fmt: skip
    return {**base, **changes}


def test_typed_areas_read_commas_spaces_and_semicolons() -> None:
    assert parse_areas("10, 30 90;270") == [10.0, 30.0, 90.0, 270.0]
    assert parse_areas("") == []
    assert parse_areas("10, x") is None
    assert parse_areas("10, -5") is None
    assert parse_areas("10, 0") is None
    assert parse_areas("10, inf") is None


def test_log_spacing_includes_both_ends_in_equal_log_steps() -> None:
    assert spaced_areas(10.0, 1000.0, 3) == pytest.approx([10.0, 100.0, 1000.0])
    assert spaced_areas(10.0, 600.0, 2) == pytest.approx([10.0, 600.0])


def test_the_form_is_refused_in_plain_words() -> None:
    assert "numbers above zero" in form_problems(form(spacing=LISTED, listed="10, a"))[0]
    assert "two storm areas" in form_problems(form(spacing=LISTED, listed="10, 10.00001"))[0]
    assert "below the largest" in form_problems(form(spacing=SPACED, smallest=600.0, largest=10.0))[0]
    assert "above zero" in form_problems(form(spacing=SPACED, smallest=0.0))[0]
    assert form_problems(form(composite=True)) == [ACCUMULATION_WORDS]
    assert form_problems(form()) == []
    assert form_problems(form(spacing=LISTED, listed="10, 30")) == []


def test_the_areas_run_are_listed_sorted_once_each_and_bracketing_ones_are_the_engines_to_pick() -> None:
    assert study_areas(form(spacing=LISTED, listed="90, 10, 30, 30")) == [10.0, 30.0, 90.0]
    assert study_areas(form(spacing=SPACED, smallest=10.0, largest=1000.0, count=3)) == [10.0, 100.0, 1000.0]
    assert study_areas(form()) is None


def test_the_job_block_holds_what_the_form_asks_for(tmp_path: Path) -> None:
    assert study_job(form()) == {"bracket": True}
    assert study_job(form(spacing=SPACED)) == {"n_areas": 6, "area_min_km2": 10.0, "area_max_km2": 600.0}
    assert study_job(form(spacing=LISTED, listed="10 30")) == {"areas_km2": [10.0, 30.0]}
    raster = tmp_path / "acc.tif"
    block = study_job(form(composite=True, accumulation=str(raster), units="km2"))
    assert block == {"bracket": True, "accumulation": str(raster.resolve()), "accumulation_units": "km2"}
    assert "accumulation" not in study_job(form(composite=False, accumulation=str(raster)))


def test_a_study_job_carries_its_block_and_a_run_job_never_does(tmp_path: Path) -> None:
    plain = values(tmp_path)
    assert "arf" not in build_job(plain, tmp_path / "out")
    job = build_job({**plain, "study": study_job(form(spacing=LISTED, listed="10, 30"))}, tmp_path / "out")
    assert job["arf"] == {"areas_km2": [10.0, 30.0]}


def test_only_a_line_with_an_area_field_carries_its_area_into_the_job(tmp_path: Path) -> None:
    job = build_job(values(tmp_path, design=design(20.971, None, 0.0)), tmp_path / "out")
    lines = {line["name"]: line for line in job["outputs"]["lines"]}
    assert lines["L1"]["drainage_area_km2"] == 20.971
    assert "drainage_area_km2" not in lines["L2"] and "drainage_area_km2" not in lines["L3"]
    assert job["outputs"]["points"] == [{"name": "P", "x": 400050.0, "y": 2700010.0}]


def test_design_lines_are_named_as_the_job_names_them() -> None:
    features = [Feature("LineString", LINE, {"drainage_area_km2": 5.0}), Feature("LineString", LINE)]
    assert design_lines(features) == ([("P1", 5.0)], ["P2"], 0)
    assert design_lines(design(20.971, None)) == ([("L1", 20.971)], ["L2"], 1)


@pytest.mark.parametrize(
    ("changes", "words"),
    [
        ({"hms": None, "storm": None, "rain_mm_h": 25.0}, STORM_WORDS),
        ({"storm": {"kind": "uniform", "mm_h": 25.0, "hours": 1.0}}, STORM_WORDS),
        ({"storm": {"kind": "gridded", "file": "x"}}, STORM_WORDS),
        ({"storm": {"kind": "hypothetical", "arf": []}}, TABLE_WORDS),
        ({"design": design(None)}, LINE_WORDS),
        ({"design": []}, LINE_WORDS),
    ],
)
def test_what_stops_a_study_is_said(tmp_path: Path, changes: dict, words: str) -> None:
    assert words in study_problems(values(tmp_path, **changes))


def test_an_hms_storm_or_a_design_storm_with_a_table_and_an_area_line_can_start(tmp_path: Path) -> None:
    assert study_problems(values(tmp_path)) == []
    storm = {"kind": "hypothetical", "arf": [(10.0, 0.98), (100.0, 0.9)]}
    assert study_problems(values(tmp_path, hms=None, storm=storm)) == []


def test_notes_name_lines_without_flow_and_lines_outside_the_storm_areas(tmp_path: Path) -> None:
    said = " ".join(study_notes(values(tmp_path, design=design(20.971, None, 500.0)), [30.0, 90.0]))
    assert "no design flow: L2" in said
    assert "Points carry no flow" in said
    assert "L1 drains 20.97 km2, below the smallest storm area of 30 km2" in said
    assert "L3 drains 500 km2, above the largest storm area of 90 km2" in said
    inside = study_notes(values(tmp_path, design=[Feature("LineString", LINE, {"drainage_area_km2": 50.0})]), [30.0, 90.0])
    assert inside == []
    assert study_notes(values(tmp_path, design=[Feature("LineString", LINE, {"drainage_area_km2": 5.0})]), None) == []


def test_the_areas_label_counts_the_runs_or_says_the_rule() -> None:
    assert areas_text([10.0, 30.0, 90.0], 2.0, 6) == "3 runs, one per storm area: 10, 30 and 90 km2."
    said = areas_text(None, 2.0, 6)
    assert said.startswith("Up to 6 runs, picked when the study starts") and "at most 2 x apart" in said
    assert areas_text([], 2.0, 6) == "Set the storm areas."


def test_the_table_is_read_from_the_study_file_and_drawn_row_by_row(tmp_path: Path) -> None:
    rows = [
        {"design_point": "Bidah 03", "drainage_area_km2": 20.971, "storm_area_low_km2": 10.0, "storm_area_high_km2": 30.0,
         "peak_low_m3s": 562.77, "peak_high_m3s": 545.75, "design_peak_m3s": 551.24, "time_of_peak_s": 44670.0,
         "arf_table_type": "fixed-area", "read_as": "design line, 2D runs either side"},
        {"design_point": "S1", "drainage_area_km2": 5.0, "storm_area_low_km2": 5.0, "storm_area_high_km2": 5.0,
         "peak_low_m3s": 100.0, "peak_high_m3s": 100.0, "design_peak_m3s": 100.0, "time_of_peak_s": 3600.0,
         "arf_table_type": "fixed-area", "read_as": "lumped element, rerun lumped at its own area"},
    ]  # fmt: skip
    data = {"areas_km2": [10.0, 30.0], "arf_table_type": "fixed-area", "table": rows, "on_grid": ["J9"]}
    (tmp_path / STUDY_FILE).write_text(json.dumps(data))
    read, kind, on_grid = read_study(tmp_path)
    assert kind == "fixed-area" and len(read) == 2 and on_grid == ["J9"]
    assert table_cells(read[0]) == [
        "Bidah 03", "20.97", "551.2", "10 and 30", "562.8 and 545.8", "12.41", "design line, 2D runs either side",
    ]  # fmt: skip
    assert table_cells(read[1])[:6] == ["S1", "5", "100.0", "5", "100.0", "1.00"]
    assert "J9" in on_grid_text(on_grid) and on_grid_text([]) == ""


def test_an_older_study_file_without_its_newer_keys_still_reads(tmp_path: Path) -> None:
    (tmp_path / STUDY_FILE).write_text(json.dumps({"areas_km2": [10.0], "arf_table_type": "x", "table": []}))
    assert read_study(tmp_path) == ([], "x", [])


def test_a_study_goes_beside_the_output_folder_and_never_over_an_earlier_one(tmp_path: Path) -> None:
    chosen = tmp_path / "bidah"
    assert next_study_dir(chosen) == tmp_path / "bidah_arf"
    (tmp_path / "bidah_arf").mkdir()
    (tmp_path / "bidah_arf" / "progress.jsonl").write_text("")
    assert next_study_dir(chosen) == tmp_path / "bidah_arf_2"
    assert study_args("j.json", "o") == ["arf", "j.json", "--out", "o"]
