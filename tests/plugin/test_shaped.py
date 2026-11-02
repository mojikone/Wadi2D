# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Embankments and channels from feature to job, without QGIS."""

from __future__ import annotations

from pathlib import Path

import pytest
from wadi2d_qgis.job_builder import Feature, build_job, preview_job, preview_problems, problems
from wadi2d_qgis.progress import RunState
from wadi2d_qgis.protocol import terrain_args
from wadi2d_qgis.shaped import parse_openings, shaped_object, shaped_problems, volumes_text

LINE = [[400000.0, 2700000.0], [400100.0, 2700050.0]]


def line(**properties) -> Feature:
    return Feature("LineString", LINE, properties)


def values(tmp_path: Path, **changes) -> dict:
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"x")
    base = {
        "dem": str(dem), "crs": "EPSG:32640", "geographic": False, "pixel": 5.0, "dx": 20.0,
        "extent": (400000.0, 2699000.0, 401000.0, 2700000.0), "manning": 0.035, "rain_mm_h": 25.0, "rain_hours": 6.0,
        "structures": {}, "boundaries": [], "design": [], "output": str(tmp_path / "out"), "duration_h": 12.0,
    }  # fmt: skip
    return {**base, **changes}


@pytest.mark.parametrize(
    "text, expected",
    [
        ("120-180", [{"start": 120.0, "end": 180.0, "side": "both"}]),
        ("120-180 left; 600.5 to 650 R", [
            {"start": 120.0, "end": 180.0, "side": "left"}, {"start": 600.5, "end": 650.0, "side": "right"},
        ]),
        ("  ", []),
        (None, []),
    ],
)  # fmt: skip
def test_openings_are_read_from_text(text, expected) -> None:
    assert parse_openings(text) == expected


@pytest.mark.parametrize("text, words", [("abc", "is not a range"), ("180-120", "ends before it starts")])
def test_a_bad_opening_is_said_in_words(text, words) -> None:
    with pytest.raises(ValueError, match=words):
        parse_openings(text)
    assert words in shaped_problems({"embankment": [line(crest_z=5.0, openings=text)]})[0]


def test_an_embankment_entry() -> None:
    feature = line(crest_z=110.0, width=6.0, left_slope=2.0, right_slope=3.0, openings="10-20", name="D1")
    entry = shaped_object("embankment", feature)
    assert entry["kind"] == "embankment"
    assert entry["name"] == "D1"
    assert entry["z_constant"] == 110.0
    assert entry["section"] == {"width": 6.0, "left_slope": 2.0, "right_slope": 3.0}
    assert entry["openings"] == [{"start": 10.0, "end": 20.0, "side": "both"}]
    assert "lining_n" not in entry


def test_a_channel_with_dykes_entry_takes_vertex_z_tops_lining_and_ends() -> None:
    feature = Feature(
        "LineString",
        [[0.0, 0.0, 100.0], [10.0, 0.0, 99.0]],
        {
            "left_top_z": 103.0,
            "right_top_z": 102.0,
            "lining_n": 0.02,
            "start_end": "taper",
            "taper_length": 40.0,
        },
    )
    entry = shaped_object("channel_dyke", feature)
    assert entry["z"] == [100.0, 99.0]
    assert entry["coordinates"] == [[0.0, 0.0], [10.0, 0.0]]
    assert entry["section"] == {"left_top_z": 103.0, "right_top_z": 102.0}
    assert entry["lining_n"] == 0.02
    assert entry["start_end"] == "taper"
    assert entry["taper_length"] == 40.0


def test_a_zero_lining_means_no_lining() -> None:
    assert "lining_n" not in shaped_object("channel", line(crest_z=1.0, lining_n=0.0))


def test_one_top_for_both_banks() -> None:
    assert shaped_object("channel_dyke", line(crest_z=1.0, top_z=4.0))["section"]["crest_z"] == 4.0


@pytest.mark.parametrize(
    "kind, properties, words",
    [
        ("embankment", {}, "needs a crest"),
        ("channel", {}, "needs a bed"),
        ("channel_dyke", {"crest_z": 1.0}, "needs a top"),
        ("channel_dyke", {"top_z": 1.0}, "needs a bed"),
        ("channel_dyke", {"crest_z": 1.0, "left_top_z": 3.0}, "needs a top"),
    ],
)
def test_what_is_missing_is_said_once_in_words(kind, properties, words) -> None:
    said = shaped_problems({kind: [line(**properties), line(**properties)]})
    assert len(said) == 1
    assert words in said[0]


def test_the_design_rule_and_a_table_each_stand_in_for_the_levels(tmp_path) -> None:
    table = tmp_path / "s.csv"
    table.write_text("station,bed_z\n0,1\n", encoding="utf-8")
    good = {
        "channel": [line(bed_start_z=100.0, bed_slope=0.01)],
        "channel_dyke": [
            line(bed_start_z=100.0, bed_slope=0.01, freeboard=0.5, water_depth=2.0),
            line(table=str(table)),
        ],
        "embankment": [line(table=str(table))],
    }
    assert shaped_problems(good) == []


def test_a_table_that_is_not_there_is_said(tmp_path) -> None:
    said = shaped_problems({"channel": [line(table=str(tmp_path / "none.csv"))]})
    assert "section table of a channel is not there" in said[0]


def test_a_table_is_copied_into_the_run_folder_and_named_in_the_job(tmp_path) -> None:
    table = tmp_path / "sections.csv"
    table.write_text("station,bed_z\n0,100\n", encoding="utf-8")
    data = values(tmp_path, structures={"channel": [line(table=str(table))]})
    job = build_job(data, tmp_path / "out")
    named = Path(job["terrain"]["objects"][0]["section"]["table"])
    assert named.parent == (tmp_path / "out" / "inputs").resolve()
    assert named.read_text(encoding="utf-8") == table.read_text(encoding="utf-8")
    assert (tmp_path / "out" / "inputs" / "channel.geojson").is_file()


def test_a_run_refuses_what_is_missing(tmp_path) -> None:
    assert any("needs a bed" in text for text in problems(values(tmp_path, structures={"channel": [line()]})))


def test_the_terrain_map_is_asked_for_in_the_job(tmp_path) -> None:
    assert build_job(values(tmp_path), tmp_path / "out")["outputs"] == {}
    assert build_job(values(tmp_path, terrain_map=True), tmp_path / "out")["outputs"]["terrain_map"] is True


def test_a_preview_needs_no_rain_no_boundary_and_no_folder(tmp_path) -> None:
    data = values(
        tmp_path, structures={"embankment": [line(crest_z=5.0)]}, output="", rain_mm_h=0.0, rain_hours=0.0
    )
    assert preview_problems(data) == []
    job = preview_job(data, tmp_path / "p")
    assert "storm" not in job
    assert job["boundaries"] == []
    assert job["run"] == {}
    assert job["terrain"]["objects"][0]["kind"] == "embankment"


@pytest.mark.parametrize(
    "changes, words",
    [
        ({"dem": None}, "Choose a DEM"),
        ({"geographic": True}, "projected CRS"),
        ({"structures": {"wall": [line()]}}, "to preview"),
        ({"structures": {"channel": [line()]}}, "needs a bed"),
    ],
)
def test_what_stops_a_preview(tmp_path, changes, words) -> None:
    assert any(words in text for text in preview_problems(values(tmp_path, **changes)))


def test_the_terrain_command() -> None:
    assert terrain_args("a/job.json", "b") == ["terrain", "a/job.json", "--out", "b"]


def test_volumes_read_as_a_sentence_and_objects_that_moved_nothing_are_left_out() -> None:
    rows = [
        {"object": "C1", "cut_m3": 1234.4, "fill_m3": 0.0},
        {"object": "D1", "cut_m3": 0.0, "fill_m3": 56.7},
        {"object": "Nil", "cut_m3": 0.0, "fill_m3": 0.0},
    ]
    assert volumes_text(rows) == "Earthworks. C1: cut 1,234 m3; D1: fill 57 m3."
    assert volumes_text([]) == ""


def test_the_final_message_carries_the_volumes() -> None:
    state = RunState()
    state.apply({"ev": "terrain", "volumes": [{"object": "C1", "cut_m3": 10.0, "fill_m3": 0.0}]})
    state.apply({"ev": "done", "code": 0, "status": "finished"})
    assert "Earthworks. C1: cut 10 m3." in state.outcome()
    assert "Earthworks" not in RunState().outcome()
