# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""W101: a job the dock did not write, read into the dock: its inline geometry as layers, the HMS files it does not
name, and the comparison that lists what the dock cannot hold, defaults taken out of both sides."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wadi2d_qgis import job_import
from wadi2d_qgis.job_builder import SchemaView
from wadi2d_qgis.job_states import job_states

from wadi2d.config.schema import RunConfig

HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")
LINE = [[0.0, 0.0], [100.0, 0.0]]


def job() -> dict:
    return {
        "terrain": {
            "dem": "dem.tif",
            "objects": [
                {"kind": "crest_line", "name": "Dam", "coordinates": LINE, "z_constant": 107.39},
                {"kind": "spillway", "name": "Dam spillway", "coordinates": LINE, "z_constant": 102.39, "coefficient": 2.1, "length": 72.0},
            ],
        },
        "boundaries": [{"kind": "normal", "slope": 0.003, "coordinates": LINE}, {"kind": "stage", "stage": 1.5, "coordinates": LINE}],
        "outputs": {"lines": [{"name": "Dam", "coordinates": LINE}]},
        "initial_levels": [{"level": 91.5, "coordinates": [[0, 0], [10, 0], [10, 10], [0, 0]]}],
        "storm": {"kind": "hypothetical", "depth_mm": 251.0},
    }


def test_inline_geometry_becomes_layers_the_sections_read() -> None:
    layers = job_import.inline_layers(job())
    assert set(layers) == {"boundaries", "crest_line", "spillway", "design_lines", "initial_water"}
    assert [props for _xy, props in layers["boundaries"]["features"]] == [{"kind": "normal", "value": 0.003}, {"kind": "stage", "value": 1.5}]
    assert layers["spillway"]["features"][0][1] == {"name": "Dam spillway", "crest_z": 102.39, "coefficient": 2.1, "length": 72.0}


def test_the_sections_take_the_layers_of_the_geopackage(tmp_path) -> None:
    gpkg = tmp_path / "x_imported_inputs.gpkg"
    states = job_states(job(), tmp_path, gpkg)
    assert states["boundaries"]["widgets"]["layer"]["source"] == f"{gpkg}|layername=boundaries"
    structures = states["structures"]["widgets"]
    assert structures["layers.spillway"]["name"] == "spillway"
    assert (structures["fields.spillway.crest_z"], structures["fields.spillway.coefficient"]) == ("crest_z", "coefficient")
    assert states["points"]["widgets"]["layer"]["name"] == "design_lines" and states["points"]["widgets"]["name"] == "name"
    assert structures["start_water.pond_level"] == "level"


def test_differences_are_paths_with_lists_folded() -> None:
    a = {"hydrology": {"subbasins": [{"name": "S1", "storm_area_km2": 20.0}, {"name": "S2", "storm_area_km2": None}]}}
    b = {"hydrology": {"subbasins": [{"name": "S1"}, {"name": "S2"}]}}
    assert job_import.differences(a, b) == ["hydrology.subbasins[].storm_area_km2"]
    assert job_import.differences({"x": [1.0, 2.0]}, {"x": [1.0002, 2.0]}) == []  # to the millimetre
    found = job_import.not_held(a, b)
    assert found == {"Hydrology": ["hydrology.subbasins[].storm_area_km2"]}
    assert job_import.held_words(found) == ["Hydrology: the dock cannot hold yet hydrology.subbasins[].storm_area_km2"]


def test_defaults_come_out_of_a_job_written_in_full() -> None:
    schema = SchemaView(RunConfig.model_json_schema())
    small = {"grid": {"dx": 20.0}, "run": {"duration_s": 7200.0}, "storm": {"kind": "uniform", "depth_mm": 50.0}}
    full = RunConfig.model_validate(small).model_dump(mode="json")
    assert job_import.strip_defaults(full, schema) == job_import.strip_defaults(small, schema)
    assert job_import.not_held(job_import.strip_defaults(full, schema), job_import.strip_defaults(small, schema)) == {}


@pytest.mark.skipif(not HMS.is_dir(), reason="his HMS project is not on this machine")
def test_the_hms_files_a_job_does_not_name_are_chosen_in_words() -> None:
    chosen = job_import.hms_choice(HMS, {"storm": {"depth_mm": 251.0}, "hydrology": {"hms_basin": "x"}})
    assert chosen["files"] == {"control": "Control_1.control", "met": "FM_200yr.met"}
    assert any("FM_200yr.met was chosen" in text for text in chosen["words"])


def test_objects_compare_in_the_order_the_engine_applies_them() -> None:
    crest, other = {"kind": "crest_line", "name": "A"}, {"kind": "crest_line", "name": "B"}
    spill = {"kind": "spillway", "name": "A spillway"}
    a = {"terrain": {"objects": [crest, spill, other]}}
    assert job_import.not_held(a, {"terrain": {"objects": [crest, other, spill]}}) == {}
    swapped = {"terrain": {"objects": [other, crest, spill]}}  # crest lines among themselves in another order
    assert job_import.not_held(a, swapped) == {"Structures": ["terrain.objects[].name"]}


def test_a_folder_gives_its_job_or_the_engines_resolved_one(tmp_path) -> None:
    assert job_import.find_job(tmp_path) is None
    (tmp_path / "config.resolved.json").write_text(json.dumps({}), encoding="utf-8")
    assert job_import.find_job(tmp_path).name == "config.resolved.json"
    (tmp_path / "job.json").write_text(json.dumps({}), encoding="utf-8")
    assert job_import.find_job(tmp_path).name == "job.json"
