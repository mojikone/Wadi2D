# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The rows of the generated basin: what the file says, what the run adds, what the job takes. No Qt."""

from __future__ import annotations

from pathlib import Path

from wadi2d_qgis.sections.basin_rows import (
    HandbackRow,
    basin_problems,
    basin_settings,
    element_choices,
    handback_properties,
    hms_elements,
    junction_rows,
    merge_event,
    merge_handbacks,
    route_words,
    set_element,
    subbasin_rows,
    summary_text,
)


def element(kind: str, name: str, downstream: str | None, missing: list[str] | None = None) -> dict:
    return {"kind": kind, "name": name, "downstream": downstream, "missing": missing or [], "parameters": {}}


MODEL = {
    "elements": [
        element("subbasin", "S1", "J1"),
        element("subbasin", "S2", "J2", ["curve_number", "lag_minutes"]),
        element("reach", "R1", "J1"),
        element("junction", "J1", None),
        element("junction", "J2", "R1"),
        element("reservoir", "Z", "J2", ["spillways", "initial_elevation_m"]),
    ],
    "routes": [
        {"junction": "J1", "route": "none", "reach": None, "next_junction": None, "reach_missing": []},
        {"junction": "J2", "route": "reach", "reach": "R1", "next_junction": "J1", "reach_missing": []},
        {"junction": "Z", "route": "none", "reach": None, "next_junction": "J2", "reach_missing": []},
    ],
    "analysis": {"unassigned_km2": 1.5},
    "notes": ["open ground, no channel in the sections: ['R1']"],
}


def test_subbasins_are_lumped_by_default_2d_where_asked_and_2d_whatever_was_asked_where_a_parameter_is_missing() -> None:
    rows = subbasin_rows(MODEL, {"S1": "2d", "S2": "lumped"})
    assert [(r.name, r.mode) for r in rows] == [("S1", "2d"), ("S2", "2d")]
    assert subbasin_rows(MODEL)[0].mode == "lumped"
    assert "curve_number" in rows[1].tip and "rain-on-grid" in rows[1].tip
    assert rows[1].missing == ["curve_number", "lag_minutes"]


def test_junction_rows_read_the_file_and_the_run_completes_them() -> None:
    rows = junction_rows(MODEL)
    assert [r["junction"] for r in rows] == ["J1", "J2", "Z"]
    assert rows[2]["kind"] == "reservoir"
    assert route_words(rows[1]) == ["J2", "reach R1", "J1", "routed; a line is built here if 2D water reaches it"]
    assert route_words(rows[0]) == ["J1", "no reach: over the ground", "leaves the model", "water enters the 2D grid here"]
    event = {
        "junctions": [
            {"junction": "J2", "kind": "junction", "route": "reach", "reach": "R1", "next_junction": "J1",
             "reach_missing": [], "enters_2d": False, "handback": True, "two_d_sources": ["S2"]},
            {"junction": "J1", "kind": "junction", "route": "none", "reach": None, "next_junction": None,
             "reach_missing": [], "enters_2d": True, "handback": False, "two_d_sources": ["J2"]},
        ]
    }  # fmt: skip
    merged = {r["junction"]: r for r in merge_event(rows, event)}
    assert route_words(merged["J2"])[3] == "hand-back line: 2D flow from S2 enters the reach"
    assert route_words(merged["J1"])[3] == "water enters the 2D grid here"
    assert route_words(merged["Z"])[3] == "water enters the 2D grid here"


def test_a_junction_above_an_incomplete_reach_says_what_the_reach_lacks() -> None:
    row = {"junction": "J3", "route": "none", "reach": "R9", "next_junction": "J1", "reach_missing": ["manning_n"]}
    assert route_words(row)[1] == "no reach: R9 lacks manning_n"


def test_the_summary_counts_and_names_what_lacks() -> None:
    text = summary_text(MODEL, subbasin_rows(MODEL))
    assert text.startswith("2 subbasins, 1 reaches, 2 junctions, 1 reservoirs; 1.5 km2 reach the edge")
    assert "Rain-on-grid for lack of a parameter: S2 (curve_number, lag_minutes)" in text
    assert "Z (spillways, initial_elevation_m)" in text
    assert "open ground" in text


def test_hand_back_choices_are_the_reaches_junctions_and_reservoirs(tmp_path: Path) -> None:
    assert element_choices(MODEL) == ["R1", "J1", "J2", "Z"]
    basin = tmp_path / "x.basin"
    basin.write_text("Subbasin: S1\nEnd:\nReach: R1\nEnd:\nJunction: J1\nEnd:\nReservoir: Dam 1\nEnd:\n", encoding="utf-8")
    assert hms_elements(basin) == ["R1", "J1", "Dam 1"]


def test_hand_back_rows_follow_the_layer_and_keep_what_the_user_set() -> None:
    lines = [{"fid": 1, "label": "Line 1"}, {"fid": 2, "label": "Wadi", "element": "J1"}]
    rows = merge_handbacks(lines, [], ["R1", "J1"])
    assert [(r.element, r.pinned) for r in rows] == [("R1", False), ("J1", True)]
    set_element(rows[0], "J1")
    rows = merge_handbacks(lines[:1], rows, ["R1", "J1"])
    assert [(r.fid, r.element, r.pinned) for r in rows] == [(1, "J1", True)]
    rows = merge_handbacks([{"fid": 3, "label": "New"}], rows, ["Z"])
    assert rows[0].element == "Z"
    assert handback_properties(HandbackRow(3, "New", "Z")) == {"name": "New", "element": "Z"}
    assert merge_handbacks(lines[:1], [], [])[0].element == ""


def test_the_basin_part_of_a_job_and_what_stops_a_generation() -> None:
    assert basin_settings(10.0, "hms_kirpich") == {"stream_threshold_km2": 10.0, "lag_method": "hms_kirpich"}
    assert basin_settings(0.0, "nrcs")["stream_threshold_km2"] is None
    assert basin_problems({}) == ["Choose a DEM layer backed by a file."]
    assert basin_problems({"dem": "x", "geographic": True}) == [
        "The DEM must be in a projected CRS, in metres.",
        "Choose an output folder first: the basin files are kept beside the runs.",
    ]
    assert basin_problems({"dem": "x", "output": "y"}) == []
