# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""W105: the last points of the lumped model as the dock holds them: the dams found in the basin, each ticked, and
junctions added; written only off the engine's default; read back from a job; saved with the model (format 6); and the
Block 2 dock way with HAT-J4 added writes the five dams and HAT-J4."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wadi2d_qgis import last_point_rows, model_doc
from wadi2d_qgis.job_builder import build_job, problems
from wadi2d_qgis.job_states import job_states
from wadi2d_qgis.last_point_rows import DAM, JUNCTION
from wadi2d_qgis.model_types import TWO_D, apply_type

from tests.plugin.test_entry_rows import values

BASIN = """Basin: Two dams
     Version: 4.12
End:

Subbasin: S1
     Canvas X: 10
     Canvas Y: 20
     Downstream: D1
End:

Reservoir: D1
     Canvas X: 100.5
     Canvas Y: 200.25
     Downstream: J1
End:

Junction: J1
     Canvas X: 300
     Canvas Y: 400
     Downstream: D2
End:

Reservoir: D2
     Canvas X: 500
     Canvas Y: 600
     Downstream: J2
End:

Junction: J2
     Canvas X: 900
     Canvas Y: 900
End:
"""
BLOCK2_BASIN = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\Basin_3.basin")
BLOCK2_DAMS = ["Bidah 03 Reservoir", "Faydh 01 Reservoir", "R5A Reservoir", "R2A Reservoir", "Z4C Reservoir"]


def basin(tmp_path: Path) -> Path:
    path = tmp_path / "two.basin"
    path.write_text(BASIN, encoding="utf-8")
    return path


def test_the_dams_and_junctions_of_a_basin_file_with_their_icons(tmp_path: Path) -> None:
    dams, junctions, icons = last_point_rows.hms_candidates(basin(tmp_path))
    assert dams == ["D1", "D2"] and junctions == ["J1", "J2"]
    assert icons == {"D1": (100.5, 200.25), "J1": (300.0, 400.0), "D2": (500.0, 600.0), "J2": (900.0, 900.0)}
    model = {"elements": [
        {"kind": "reservoir", "name": "Dam", "outlet": [1.0, 2.0]}, {"kind": "junction", "name": "J", "outlet": [3.0, 4.0]},
        {"kind": "subbasin", "name": "S", "outlet": [5.0, 6.0]},
    ]}  # fmt: skip
    assert last_point_rows.model_candidates(model) == (["Dam"], ["J"], {"Dam": (1.0, 2.0), "J": (3.0, 4.0)})


def test_every_dam_ticked_and_no_junction_writes_nothing_and_anything_else_the_list() -> None:
    dams = ["D1", "D2"]
    rows = last_point_rows.default_rows(dams)
    assert rows == [("D1", DAM, True), ("D2", DAM, True)] and last_point_rows.job_value(rows, dams) is None
    assert last_point_rows.job_value([*rows, ("J1", JUNCTION, True)], dams) == ["D1", "D2", "J1"]
    assert last_point_rows.job_value([("D1", DAM, False), ("D2", DAM, True)], dams) == ["D2"]
    assert last_point_rows.job_value([("D1", DAM, False), ("D2", DAM, False)], dams) == []
    assert last_point_rows.job_value([], []) is None, "a basin with no dam and nothing added: the default"


def test_a_jobs_list_comes_back_as_rows_and_writes_itself_again() -> None:
    dams, junctions = ["D1", "D2"], ["J1", "J2"]
    for given in (None, [], ["D2"], ["D1", "D2", "J1"], ["D1", "J2"]):
        rows = last_point_rows.rows_from_job(given, dams, junctions)
        assert last_point_rows.job_value(rows, dams) == given, given
    assert last_point_rows.rows_from_job(["D1", "J1"], dams, junctions) == [
        ("D1", DAM, True), ("D2", DAM, False), ("J1", JUNCTION, True),
    ]  # fmt: skip
    held = [("D1", DAM, False), ("Gone", DAM, True), ("J1", JUNCTION, True)]
    assert last_point_rows.merge(held, ["D1", "D2"]) == [
        ("D1", DAM, False),
        ("D2", DAM, True),
        ("J1", JUNCTION, True),
    ]


def test_problems_words_and_the_nearest_junction() -> None:
    rows = [("D1", DAM, True), ("D2", DAM, False), ("J9", JUNCTION, True), ("J1", JUNCTION, True)]
    (said,) = last_point_rows.problems(rows, ["D1", "D2", "J1"])
    assert "J9 are not junctions of the basin" in said
    assert last_point_rows.words(rows) == "the lumped model ends at 1 dam + J9 + J1 (1 dam not)"
    assert last_point_rows.words(
        last_point_rows.default_rows(BLOCK2_DAMS) + [("HAT-J4", JUNCTION, True)]
    ) == ("the lumped model ends at 5 dams + HAT-J4")
    assert "no last point" in last_point_rows.words([("D1", DAM, False)])
    icons = {"J1": (300.0, 400.0), "J2": (900.0, 900.0), "D1": (301.0, 401.0)}
    name, distance = last_point_rows.nearest_junction(icons, ["J1", "J2"], 310.0, 400.0)
    assert name == "J1" and distance == pytest.approx(10.0)
    assert last_point_rows.nearest_junction({}, ["J1"], 0.0, 0.0) is None


def test_the_list_reaches_the_job_only_when_set_and_a_2d_model_drops_it(tmp_path: Path) -> None:
    plain = build_job(values(tmp_path, last_points=None), tmp_path / "out")
    assert "last_points" not in plain["hydrology"]
    named = build_job(values(tmp_path, last_points=["D1", "D2", "J1"]), tmp_path / "out")
    assert named["hydrology"]["last_points"] == ["D1", "D2", "J1"]
    none = build_job(values(tmp_path, last_points=[]), tmp_path / "out")
    assert none["hydrology"]["last_points"] == []
    two_d = apply_type(values(tmp_path, last_points=["J1"], last_point_problems=["x"]), TWO_D)
    assert "last_points" not in two_d and "last_point_problems" not in two_d
    said = problems(
        values(tmp_path, last_points=["J9"], last_point_problems=["Last points J9 are not junctions"])
    )
    assert "Last points J9 are not junctions" in said


def test_a_jobs_last_points_are_read_back_over_its_basins_dams(tmp_path: Path) -> None:
    path = basin(tmp_path)
    job = {"hydrology": {"hms_basin": str(path), "subbasins": [], "last_points": ["D2", "J1"]}}
    rows = job_states(job, tmp_path)["hydrology"]["widgets"]["last_points"]
    assert rows == [["D1", DAM, False], ["D2", DAM, True], ["J1", JUNCTION, True]]
    default = {"hydrology": {"hms_basin": str(path), "subbasins": []}}
    assert "last_points" not in job_states(default, tmp_path)["hydrology"]["widgets"], (
        "the table's own default"
    )
    gone = {
        "hydrology": {"hms_basin": str(tmp_path / "gone.basin"), "subbasins": [], "last_points": ["D2", "J1"]}
    }
    rows = [tuple(r) for r in job_states(gone, tmp_path)["hydrology"]["widgets"]["last_points"]]
    assert last_point_rows.job_value(rows, []) == ["D2", "J1"], "with no basin file the same list is written"


def _doc(version: int, model_type: str | None, lumped_form: str | None, entry: str | None) -> dict:
    hydrology = {"folder": "D:/hms"}
    if entry:
        hydrology["lumped_entry"] = {"data": entry, "text": entry}
    reduction = {"lumped.form": {"data": lumped_form, "text": lumped_form or ""}} if lumped_form else {}
    return {
        "format": model_doc.FORMAT, "version": version, "model_type": model_type,
        "sections": {"hydrology": {"widgets": hydrology}, "reduction": {"widgets": reduction}},
    }  # fmt: skip


@pytest.mark.parametrize(
    ("model_type", "form", "entry", "said"),
    [
        ("hybrid_2d", "curve", "outlet", model_doc.LAST_POINTS_CURVE),
        ("hybrid_lumped", "curve", "network", model_doc.LAST_POINTS_NETWORK),
        ("hybrid_lumped", "area", "network", model_doc.LAST_POINTS_NETWORK),
        (None, "curve", None, model_doc.LAST_POINTS_CURVE),
        ("lumped", "curve", None, None),
        ("2d", "curve", None, None),
        ("hybrid_2d", "area", "outlet", None),
    ],
)
def test_a_model_of_format_5_comes_up_with_the_dams_and_says_what_moves(
    model_type, form, entry, said
) -> None:
    doc = model_doc.loads(json.dumps(_doc(5, model_type, form, entry)))
    assert doc["version"] == model_doc.VERSION == 6
    assert doc.get(model_doc.MIGRATED, []) == ([said] if said else [])
    assert "last_points" not in doc["sections"]["hydrology"]["widgets"], (
        "the table comes up with every dam ticked"
    )


@pytest.mark.skipif(not BLOCK2_BASIN.is_file(), reason="his Block 2 HMS project is not on this machine")
def test_block_2_s_dams_and_hat_j4(tmp_path: Path) -> None:
    """The dock finds the five dams of Basin 3; HAT-J4 added writes W105's list, which the engine takes."""
    from wadi2d.config.schema import RunConfig

    dams, junctions, icons = last_point_rows.hms_candidates(BLOCK2_BASIN)
    assert sorted(dams) == sorted(BLOCK2_DAMS) and "HAT-J4" in junctions and "HAT-J4" in icons
    rows = last_point_rows.default_rows(dams) + [("HAT-J4", JUNCTION, True)]
    value = last_point_rows.job_value(rows, dams)
    assert value == [*dams, "HAT-J4"] and last_point_rows.problems(rows, dams + junctions) == []
    job = build_job(values(tmp_path, last_points=value), tmp_path / "out")
    assert RunConfig.model_validate(job).hydrology.last_points == value
