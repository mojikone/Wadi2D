# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Basin points layer's rows without Qt (W73)."""

from __future__ import annotations

from pathlib import Path

from wadi2d_qgis.basin_point_rows import (
    DIVERSION_METHODS,
    absolute_files,
    apply_delineate,
    default_ticks,
    delineate_field,
    diversion_rows,
    needs_words,
    next_name,
    point_fields,
)
from wadi2d_qgis.job_builder import Feature


def test_a_new_point_takes_the_next_free_name() -> None:
    assert next_name("outfall", set()) == "Outfall 1"
    assert next_name("outfall", {"Outfall 1", "Outfall 2"}) == "Outfall 3"
    assert next_name("remove_junction", {"Outfall 1"}) == "Remove 1"


def test_the_fields_are_found_in_any_case() -> None:
    assert point_fields(["NAME", "Kind", "file", "other"]) == {"name": "NAME", "kind": "Kind", "file": "file"}
    assert point_fields(["Name"]) == {"name": "Name"}


def test_a_source_file_beside_its_layer_is_made_absolute(tmp_path: Path) -> None:
    points = [
        Feature("Point", [1.0, 2.0], {"kind": "source", "file": "inflow.csv"}),
        Feature("Point", [1.0, 2.0], {"kind": "source", "file": str(tmp_path / "abs.csv")}),
        Feature("Point", [1.0, 2.0], {"kind": "junction"}),
    ]
    out = absolute_files(points, tmp_path)
    assert out[0].properties["file"] == str(tmp_path / "inflow.csv")
    assert out[1].properties["file"] == str(tmp_path / "abs.csv")
    assert out[2].properties == {"kind": "junction"}
    assert absolute_files(points, None) is points


def test_a_tick_is_written_only_where_it_differs_from_the_default() -> None:
    objects = [{"kind": "wall"}, {"kind": "burn_line"}, {"kind": "crest_line"}, {"kind": "wall", "delineate": True}]
    ticks = {**default_ticks(), "wall": False, "crest_line": True}
    apply_delineate(objects, ticks)
    assert objects == [
        {"kind": "wall", "delineate": False},
        {"kind": "burn_line"},
        {"kind": "crest_line", "delineate": True},
        {"kind": "wall", "delineate": True},  # the line's own field outranks its kind's tick
    ]
    assert apply_delineate([{"kind": "wall"}], None) == [{"kind": "wall"}]


def test_a_delineate_field_reads_yes_no_or_nothing() -> None:
    assert delineate_field(None) is None and delineate_field("") is None
    assert delineate_field(1) is True and delineate_field("yes") is True
    assert delineate_field(0) is False and delineate_field("false") is False


def test_the_diversion_points_become_rows_and_their_tables_are_made_absolute(tmp_path: Path) -> None:
    """W75: the table lists the layer's diversion points; relative tables beside the layer reach the engine whole."""
    features = [
        {"fid": 1, "name": "Div 1", "kind": "diversion", "method": "Lateral Weir", "table": "rating.csv",
         "parameters": None, "limits": "NULL"},
        {"fid": 2, "name": "Out", "kind": "outfall"},
    ]  # fmt: skip
    (row,) = diversion_rows(features)
    assert row == {"fid": 1, "name": "Div 1", "method": "Lateral Weir", "divert_to": "", "table": "rating.csv",
                   "parameters": "", "limits": ""}  # fmt: skip
    assert "crest_m" in needs_words("Lateral Weir") and DIVERSION_METHODS[0] in needs_words("weir")
    point = Feature("Point", [0.0, 0.0], {"kind": "diversion", "table": "rating.csv",
                                          "parameters": '{"crest_m": 1, "tailwater": "tw.csv"}'})  # fmt: skip
    inline = Feature("Point", [0.0, 0.0], {"kind": "diversion", "table": "[[0, 0], [1, 1]]"})
    made, kept = absolute_files([point, inline], tmp_path)
    assert made.properties["table"] == str(tmp_path / "rating.csv")
    assert '"tailwater": "' in made.properties["parameters"] and "tw.csv" in made.properties["parameters"]
    assert str(tmp_path).replace("\\", "\\\\") in made.properties["parameters"]
    assert kept.properties["table"] == "[[0, 0], [1, 1]]"
