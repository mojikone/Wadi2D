# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Values to a job, without QGIS."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wadi2d_qgis.job_builder import (
    Feature,
    build_job,
    feature_collection,
    finite,
    hms_files,
    hms_import_args,
    hms_subbasins,
    merge_hms,
    merge_notes,
    notes,
    problems,
    snap_dx,
    write_job,
)

LINE = [[400000.1234, 2700000.0], [400100.0, 2700050.0]]


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


def test_a_snapped_cell_size_is_said() -> None:
    said = " ".join(notes({"boundaries": [1], "dx": 20.0, "pixel": 3.0}))
    assert "21 m" in said
    assert notes({"boundaries": [1], "dx": 21.0, "pixel": 3.0}) == []


def test_a_duration_set_by_the_control_file_is_said() -> None:
    job = {"run": {"duration_s": 3600.0}}
    said = " ".join(merge_notes(job, {"run": {"duration_s": 172800.0}}))
    assert "48 h" in said
    assert "1 h" in said
    assert merge_notes(job, {"run": {"duration_s": 3600.0}}) == []


def test_snap_dx_goes_to_the_nearest_pixel_multiple() -> None:
    assert snap_dx(20.2, 0.5) == 20.0
    assert snap_dx(0.1, 0.5) == 0.5
    assert snap_dx(10.0, 0.0) == 10.0


def test_a_plain_rain_job(tmp_path: Path) -> None:
    job = build_job(values(tmp_path), tmp_path / "out")
    assert job["grid"]["dx"] == 20.0
    assert job["run"]["duration_s"] == 43200.0
    assert job["storm"] == {"kind": "uniform", "depth_mm": 150.0, "duration_min": 360.0}
    assert job["grid"]["extent"] == [400000.0, 2699000.0, 401000.0, 2700000.0]
    assert "domain" not in job["grid"]


def test_paths_are_absolute_and_the_cache_is_shared_between_runs(tmp_path: Path) -> None:
    cover = tmp_path / "n.tif"
    cover.write_bytes(b"x")
    job = build_job(values(tmp_path, manning_raster=str(cover)), tmp_path / "out")
    assert Path(job["terrain"]["dem"]).is_absolute()
    assert Path(job["terrain"]["manning_raster"]).is_absolute()
    assert Path(job["grid"]["cache_dir"]).parent == (tmp_path).resolve()


def test_a_domain_polygon_lands_in_inputs_as_geojson_in_the_dem_crs(tmp_path: Path) -> None:
    ring = [[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 0.0]]]
    data = values(tmp_path, domain=[Feature("Polygon", ring)], extent=None)
    job = build_job(data, tmp_path / "out")
    path = Path(job["grid"]["domain"])
    assert path.is_absolute()
    assert path.parent.name == "inputs"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["crs"]["properties"]["name"] == "EPSG:32640"
    assert written["features"][0]["geometry"]["type"] == "Polygon"
    assert "extent" not in job["grid"]


def test_structures_become_inline_objects_and_inputs_files(tmp_path: Path) -> None:
    crest = Feature("LineString", LINE, {"crest_z": 512.5})
    spill = Feature("LineString", LINE, {"crest_z": 510.0, "coefficient": 2.1, "length": 50.0})
    wall = Feature("LineString", LINE)
    data = values(tmp_path, structures={"crest_line": [crest], "spillway": [spill], "wall": [wall]})
    job = build_job(data, tmp_path / "out")
    objects = {entry["kind"]: entry for entry in job["terrain"]["objects"]}
    assert objects["crest_line"]["z_constant"] == 512.5
    assert objects["spillway"]["coefficient"] == 2.1
    assert objects["spillway"]["length"] == 50.0
    assert "z_constant" not in objects["wall"]
    assert (tmp_path / "out" / "inputs" / "crest_line.geojson").is_file()


def test_vertex_z_goes_to_the_per_vertex_list_and_xy_stay_two_dimensional(tmp_path: Path) -> None:
    line = Feature("LineString", [[0.0, 0.0, 500.0], [10.0, 0.0, 501.0]])
    job = build_job(values(tmp_path, structures={"crest_line": [line]}), tmp_path / "out")
    entry = job["terrain"]["objects"][0]
    assert entry["z"] == [500.0, 501.0]
    assert entry["coordinates"] == [[0.0, 0.0], [10.0, 0.0]]


def test_boundary_kinds_carry_their_own_value(tmp_path: Path) -> None:
    lines = [
        Feature("LineString", LINE, {"kind": "stage", "value": 2.5}),
        Feature("LineString", LINE, {"kind": "Normal ", "value": 0.01}),
        Feature("LineString", LINE, {"kind": "free", "value": None}),
    ]
    stage, normal, free = build_job(values(tmp_path, boundaries=lines), tmp_path / "out")["boundaries"]
    assert stage["stage"] == 2.5
    assert normal == {"kind": "normal", "coordinates": normal["coordinates"], "slope": 0.01}
    assert set(free) == {"kind", "coordinates"}


def test_design_points_and_lines_split_by_geometry(tmp_path: Path) -> None:
    design = [
        Feature("Point", [400010.0, 2699990.0], {"name": "Dam 1"}),
        Feature("Point", [400020.0, 2699980.0]),
        Feature("LineString", LINE, {"name": "Across"}),
    ]
    outputs = build_job(values(tmp_path, design=design), tmp_path / "out")["outputs"]
    assert outputs["points"][0] == {"name": "Dam 1", "x": 400010.0, "y": 2699990.0}
    assert outputs["points"][1]["name"] == "P2"
    assert outputs["lines"][0]["name"] == "Across"


def test_geojson_coordinates_are_rounded_to_the_millimetre() -> None:
    collection = feature_collection([Feature("LineString", LINE)], "EPSG:32640")
    assert collection["features"][0]["geometry"]["coordinates"][0][0] == 400000.123


@pytest.mark.parametrize(
    ("changes", "words"),
    [
        ({"dem": None}, "DEM"),
        ({"geographic": True}, "projected"),
        ({"output": ""}, "output folder"),
        ({"rain_mm_h": 0.0}, "rain"),
        ({"rain_hours": 0.0}, "hours"),
        ({"hms": {"folder": "x", "basin": "b", "met": "", "control": "c"}}, "HMS"),
        ({"structures": {"crest_line": [Feature("LineString", LINE)]}}, "crest line needs an elevation"),
    ],
)
def test_problems_are_said_in_plain_words(tmp_path: Path, changes: dict, words: str) -> None:
    assert any(words in text for text in problems(values(tmp_path, **changes)))


def test_a_complete_job_has_no_problems(tmp_path: Path) -> None:
    assert problems(values(tmp_path)) == []


def test_notes_warn_of_a_closed_domain_and_a_short_run(tmp_path: Path) -> None:
    said = " ".join(notes(values(tmp_path, duration_h=1.0)))
    assert "wall" in said
    assert "still raining" in said


def test_write_job_round_trips(tmp_path: Path) -> None:
    job = build_job(values(tmp_path), tmp_path / "out")
    assert json.loads(write_job(job, tmp_path / "out").read_text(encoding="utf-8")) == job


def test_hms_folder_reading(tmp_path: Path) -> None:
    (tmp_path / "Basin_1.basin").write_text(
        "Basin: Basin 1\n\nSubbasin: S1\n  Area: 1\nEnd:\n\nReach: R1\nEnd:\n\nSubbasin: S 2\nEnd:\n", "utf-8"
    )
    (tmp_path / "Storm.met").write_text("x", "utf-8")
    (tmp_path / "Control_1.control").write_text("x", "utf-8")
    found = hms_files(tmp_path)
    assert found == {"basin": ["Basin_1.basin"], "met": ["Storm.met"], "control": ["Control_1.control"]}
    assert hms_subbasins(tmp_path / "Basin_1.basin") == ["S1", "S 2"]


def test_hms_import_arguments() -> None:
    hms = {"folder": "D:/hms", "basin": "b.basin", "met": "m.met", "control": "c.control"}
    args = hms_import_args(hms, "x.json")
    assert args[0] == "hms-import"
    assert args[args.index("--met") + 1] == "m.met"
    assert args[-2:] == ["--out", "x.json"]


def test_merge_keeps_the_import_storm_and_the_dock_modes(tmp_path: Path) -> None:
    job = build_job(values(tmp_path, hms={"folder": "x"}, curve_number=80.0), tmp_path / "out")
    assert "storm" not in job
    imported = {
        "storm": {"kind": "hypothetical", "depth_mm": 120.0},
        "hydrology": {
            "hms_basin": "b.basin",
            "subbasins": [{"name": "S1", "mode": "lumped", "outlet": [1, 2]}],
        },
        "run": {"duration_s": 7200.0},
    }
    merged = merge_hms(job, imported, {"modes": {"S1": "2d", "S2": "lumped"}})
    assert merged["storm"]["depth_mm"] == 120.0
    assert merged["run"]["duration_s"] == 7200.0
    assert merged["hydrology"]["hms_basin"] == "b.basin"
    assert merged["hydrology"]["curve_number"] == 80.0
    assert merged["hydrology"]["subbasins"][0] == {"name": "S1", "mode": "2d", "outlet": [1, 2]}
    assert merged["hydrology"]["subbasins"][1] == {"name": "S2", "mode": "lumped"}


def test_a_failed_reprojection_is_seen_at_any_depth() -> None:
    inf = float("inf")
    assert finite([[[1.0, 2.0], [3.0, 4.0]]])
    assert not finite([[[1.0, 2.0], [inf, inf]]])
    assert not finite([float("nan"), 2.0])


def test_an_hms_run_with_no_curve_number_is_said() -> None:
    base = {"boundaries": [1], "hms": {"folder": "x"}}
    assert "no losses" in " ".join(notes(base))
    assert notes({**base, "curve_number": 85.0}) == []
    assert notes({**base, "cn_raster": "cn.tif"}) == []
