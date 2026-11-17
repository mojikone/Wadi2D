# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""W103: each subbasin's own storm area, entry and outlet, and the point inflows of lumped elements, as the dock holds
them: written only when set, taken by the engine's schema, read back from a job, refused in words; and the Block 2
Hybrid jobs of W79 held field by field."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wadi2d_qgis import entry_rows, model_doc
from wadi2d_qgis.entry_rows import NO_OUTLET
from wadi2d_qgis.job_builder import SchemaView, build_job, merge_hms, problems
from wadi2d_qgis.job_import import not_held, strip_defaults
from wadi2d_qgis.job_states import job_states
from wadi2d_qgis.reduction_rows import AREA, COEFFICIENT, CURVE, NONE, lumped_form, part

from wadi2d.config.schema import RunConfig

W79 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways\jobs")
W102 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W102 Block 2 models in the dock\rebuilt")
ARF = {"areas_km2": [10.0, 100.0, 1000.0], "factors": [0.99, 0.913, 0.694]}
IMPORTED = {
    "storm": {
        "kind": "uniform",
        "depth_mm": 120.0,
        "duration_min": 1440.0,
        "storm_area_km2": 100.0,
        "arf": ARF,
    },
    "hydrology": {
        "hms_basin": "b.basin",
        "subbasins": [
            {"name": "S1", "mode": "lumped", "outlet": [1.0, 2.0], "entry": "wadi"},
            {"name": "S2", "mode": "lumped", "outlet": [3.0, 4.0], "entry": "wadi"},
        ],
    },
    "run": {"duration_s": 7200.0},
}
ROWS = [
    ("Dam outflow", "Dam Reservoir", 400100.5, 2700020.25, "point", True),
    ("Sink", "J9", 1.0, 2.0, "wadi", False),
]


def values(tmp_path: Path, **changes) -> dict:
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"x")
    base = {
        "dem": str(dem), "crs": "EPSG:32640", "geographic": False, "pixel": 0.5, "dx": 20.0,
        "extent": (400000.0, 2699000.0, 401000.0, 2700000.0), "manning": 0.035, "manning_raster": None,
        "rain_mm_h": 25.0, "rain_hours": 6.0, "curve_number": None, "cn_raster": None,
        "structures": {}, "boundaries": [], "design": [], "output": str(tmp_path / "out"), "duration_h": 12.0,
    }  # fmt: skip
    return {**base, **changes}


def hms(**edits) -> dict:
    return {
        "folder": "x",
        "basin": "b.basin",
        "met": "m.met",
        "control": "c.control",
        "modes": {"S1": "lumped", "S2": "2d"},
        "edits": edits,
    }


def test_an_outlet_cell_reads_a_point_none_or_the_basins_and_refuses_the_rest_in_words() -> None:
    assert entry_rows.parse_outlet("") is None and entry_rows.parse_outlet("  ") is None
    assert entry_rows.parse_outlet("None") == NO_OUTLET
    assert entry_rows.parse_outlet("438748.49, 2727147.89") == [438748.49, 2727147.89]
    assert entry_rows.parse_outlet("438748.49 2727147.89") == [438748.49, 2727147.89]
    with pytest.raises(ValueError, match='Subbasin S1: the outlet "here" is not a point'):
        entry_rows.parse_outlet("here", "S1")
    assert entry_rows.outlet_text([438748.48973783385, 2727147.893463373]) == "438748.490, 2727147.893"
    assert entry_rows.outlet_text(NO_OUTLET) == "none" and entry_rows.outlet_text(None) == ""


def test_no_edit_and_no_inflow_is_the_job_of_before(tmp_path: Path) -> None:
    plain = build_job(values(tmp_path), tmp_path / "out")
    assert build_job(values(tmp_path, inflows=[], entry_problems=[]), tmp_path / "out") == plain
    assert "inflows" not in plain["hydrology"]
    old = {key: value for key, value in hms().items() if key != "edits"}
    assert merge_hms(plain, IMPORTED, hms()) == merge_hms(plain, IMPORTED, old)
    assert merge_hms(plain, IMPORTED, hms())["hydrology"]["subbasins"][0] == {
        "name": "S1", "mode": "lumped", "outlet": [1.0, 2.0], "entry": "wadi",
    }  # fmt: skip


def test_edits_and_inflows_reach_the_job_and_the_engine_takes_them(tmp_path: Path) -> None:
    edits = {"S1": {"storm_area_km2": 20.97, "outlet": NO_OUTLET}, "S2": {"entry": "point"}}
    job = build_job(
        values(tmp_path, inflows=ROWS, hms=hms(**edits)), tmp_path / "out"
    )  # the HMS storm, with its table
    merged = merge_hms(job, IMPORTED, hms(**edits))
    first, second = merged["hydrology"]["subbasins"]
    assert first == {"name": "S1", "mode": "lumped", "outlet": None, "entry": "wadi", "storm_area_km2": 20.97}
    assert second == {"name": "S2", "mode": "2d", "outlet": [3.0, 4.0], "entry": "point"}
    assert merged["hydrology"]["inflows"] == [
        {"name": "Dam outflow", "x": 400100.5, "y": 2700020.25, "element": "Dam Reservoir"},
        {"name": "Sink", "x": 1.0, "y": 2.0, "element": "J9", "entry": "wadi", "enters": False},
    ]
    parsed = RunConfig.model_validate(merged)
    assert (
        parsed.hydrology.subbasins[0].storm_area_km2 == 20.97 and parsed.hydrology.subbasins[0].outlet is None
    )
    assert [i.enters for i in parsed.hydrology.inflows] == [True, False]


def test_what_a_job_holds_comes_back_pinned_and_writes_itself_again(tmp_path: Path) -> None:
    subbasins = [
        {"name": "S1", "mode": "lumped", "outlet": None, "entry": "wadi", "storm_area_km2": 20.97},
        {"name": "S2", "mode": "2d", "outlet": [5.0, 6.0]},
    ]
    edits = entry_rows.edits_from_job(subbasins)
    assert edits == {
        "S1": {"storm_area_km2": 20.97, "entry": "wadi", "outlet": NO_OUTLET},
        "S2": {"entry": "point", "outlet": [5.0, 6.0]},
    }
    inflows = [
        *entry_rows.inflow_jobs(ROWS),
        {"name": "Table", "x": 0.0, "y": 0.0, "times_s": [0.0, 60.0], "flows": [0.0, 1.0]},
    ]
    assert (
        entry_rows.inflow_rows(inflows) == ROWS
    )  # a table hydrograph at a point is not held: the comparison says so
    job = {
        "hydrology": {"hms_basin": str(tmp_path / "Basin.basin"), "subbasins": subbasins, "inflows": inflows}
    }
    states = job_states(job, tmp_path)
    assert states["hydrology"]["extra"]["edits"] == edits
    assert states["hydrology"]["widgets"]["inflows"] == [list(row) for row in ROWS]
    merged = merge_hms({"hydrology": {}, "run": {}}, IMPORTED, hms(**edits))
    assert [{k: v for k, v in s.items() if v is not None} for s in merged["hydrology"]["subbasins"]] == [
        {"name": "S1", "mode": "lumped", "entry": "wadi", "storm_area_km2": 20.97},
        {"name": "S2", "mode": "2d", "outlet": [5.0, 6.0], "entry": "point"},
    ]


def test_a_generated_basins_job_brings_no_edit(tmp_path: Path) -> None:
    job = {"hydrology": {"basin_json": "basin.json", "subbasins": [{"name": "S1", "mode": "lumped"}]}}
    assert "edits" not in job_states(job, tmp_path)["hydrology"]["extra"]


@pytest.mark.parametrize(
    ("reduction", "kind", "form"),
    [
        (
            {"lumped": part(AREA, "c", 100.0), "grid": part(AREA, "c", 100.0)},
            "fixed",
            AREA,
        ),  # the single-storm form
        ({"lumped": part(CURVE, "c"), "grid": part(AREA, "c", 100.0)}, "depth", CURVE),
        ({"lumped": part(AREA, "c", 50.0), "grid": part(AREA, "c", 100.0)}, "fixed", "split"),
        (
            {"lumped": part(COEFFICIENT, coefficient=0.9), "grid": part(COEFFICIENT, coefficient=0.9)},
            "fixed",
            COEFFICIENT,
        ),
        ({"lumped": part(), "grid": part()}, "fixed", NONE),
        ({"lumped": part(AREA, "c", 100.0), "grid": part(AREA, "c", 100.0)}, "gauges", "observed"),
    ],
)
def test_the_lumped_form_an_own_storm_area_meets(reduction: dict, kind: str, form: str) -> None:
    assert lumped_form(reduction, kind) == form


def test_what_stops_a_run_is_said_in_words(tmp_path: Path) -> None:
    modes = {"S1": "lumped", "S2": "2d"}
    assert entry_rows.edit_problems({"S1": {"storm_area_km2": 20.0}}, modes, AREA) == []
    assert (
        entry_rows.edit_problems({"S1": {"storm_area_km2": 20.0}}, modes, None) == []
    )  # the HMS storm's own table
    (two_d,) = entry_rows.edit_problems({"S2": {"storm_area_km2": 20.0}}, modes, CURVE)
    assert "S2 has a storm area of its own and is treated as 2D" in two_d
    (table,) = entry_rows.edit_problems({"S1": {"storm_area_km2": 20.0}}, modes, COEFFICIENT)
    assert "Subbasins S1 read the area-reduction curve" in table
    (observed,) = entry_rows.edit_problems({"S1": {"storm_area_km2": 20.0}}, modes, "observed")
    assert "this rain takes no area reduction" in observed
    found = entry_rows.inflow_problems(
        [
            ("", "", None, 2.0, "point", True),
            ("A", "J", 1.0, 2.0, "point", True),
            ("A", "J", 1.0, 2.0, "point", True),
        ]
    )
    assert found == [
        "Point inflow 1 needs a name: the run keeps its series by name.",
        "Point inflow 1 needs the lumped element whose outflow enters there.",
        "Point inflow 1 needs its point: x and y in the DEM's coordinates.",
        "Point inflows need names of their own: A stands twice.",
    ]
    said = problems(values(tmp_path, inflows=ROWS[:1]))
    assert any("Point inflows take the outflow of a lumped element" in text for text in said)
    said = problems(
        values(tmp_path, inflows=ROWS[:1], hms=hms(S2={"storm_area_km2": 5.0}), entry_problems=["bad outlet"])
    )
    assert "bad outlet" in said and any("S2 has a storm area of its own" in text for text in said)


def test_the_status_line_counts_what_is_set() -> None:
    edits = {"S1": {"storm_area_km2": 20.0, "outlet": NO_OUTLET}, "S2": {"entry": "point"}, "S3": {}}
    assert (
        entry_rows.words(edits, ROWS)
        == "1 at a storm area of its own \N{MIDDLE DOT} 2 entries set by subbasin \N{MIDDLE DOT} 2 point inflows"
    )
    assert entry_rows.words({}, []) == ""


def test_a_model_of_format_4_comes_up_with_nothing_set_and_nothing_said() -> None:
    old = {
        "format": model_doc.FORMAT,
        "version": 4,
        "sections": {"hydrology": {"widgets": {"exclude": True}, "extra": {"modes": {"S1": "lumped"}}}},
    }
    doc = model_doc.loads(json.dumps(old))
    hydrology = doc["sections"]["hydrology"]
    assert doc["version"] == model_doc.VERSION == 7 and not doc.get(model_doc.MIGRATED)  # 6: W105, nothing said here
    assert hydrology["widgets"] == {"exclude": True, "inflows": []}
    assert hydrology["extra"] == {"modes": {"S1": "lumped"}, "edits": {}}


@pytest.mark.skipif(
    not (W79.is_dir() and W102.is_dir()), reason="the Block 2 jobs of W79 are not on this machine"
)
@pytest.mark.parametrize(
    ("stem", "kind"),
    [("rerun2_run3_hybrid_aligned", "hybrid_lumped"), ("rerun2_run4_hybrid_2d_routing_aligned", "hybrid_2d")],
)
def test_the_block_2_hybrid_jobs_are_held_whole(stem: str, kind: str) -> None:
    """W102's gaps closed without QGIS: the edits and inflows read from W79's job, laid over the dock's own rebuilt job
    and the HMS import it was made with (W102, Run's way), give W79's hydrology field by field."""
    schema = SchemaView(RunConfig.model_json_schema())
    original = json.loads((W79 / f"{stem}.json").read_text(encoding="utf-8"))
    rebuilt = json.loads((W102 / stem / "job.json").read_text(encoding="utf-8"))
    imported = json.loads((W102 / stem / "hms_import.json").read_text(encoding="utf-8"))
    states = job_states(original, W79)["hydrology"]
    modes = {s["name"]: s["mode"] for s in rebuilt["hydrology"]["subbasins"]}
    job = {
        **rebuilt,
        "hydrology": {
            key: value for key, value in rebuilt["hydrology"].items() if key not in ("subbasins", "inflows")
        },
    }
    rows = [tuple(row) for row in states["widgets"]["inflows"]]
    if rows:
        job["hydrology"]["inflows"] = entry_rows.inflow_jobs(rows)
    merged = merge_hms(job, imported, {"modes": modes, "edits": states["extra"]["edits"]})
    before = not_held(strip_defaults(original, schema), strip_defaults(rebuilt, schema)).get("Hydrology", [])
    after = not_held(strip_defaults(original, schema), strip_defaults(merged, schema)).get("Hydrology", [])
    assert {"hydrology.subbasins[].storm_area_km2", "hydrology.subbasins[].entry"} <= set(before)
    assert after == ["hydrology.curve_number"]  # the one gap W102 found that this iteration leaves
    RunConfig.model_validate(merged)
