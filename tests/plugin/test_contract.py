# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The plugin against the real engine's schema. These tests may import the engine; the plugin never does."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wadi2d_qgis import job_builder
from wadi2d_qgis.job_builder import Feature, SchemaView, build_job, merge_hms, preview_job
from wadi2d_qgis.shaped import END_KEYS, LINING, OBJECT_PATH, SECTION_PATH, SHAPE_KEYS, SHAPED_KINDS

config = pytest.importorskip("wadi2d.config.schema")
SAMPLE = Path(__file__).with_name("schema_sample.json")
PATHS = (
    job_builder.DX,
    job_builder.MANNING,
    job_builder.DURATION,
    job_builder.RAIN_DEPTH,
    job_builder.RAIN_DURATION,
    job_builder.CURVE_NUMBER,
    job_builder.SUBBASIN_MODE,
    job_builder.BOUNDARY_KIND,
    job_builder.BOUNDARY_STAGE,
    job_builder.BOUNDARY_SLOPE,
    job_builder.SPILLWAY_C,
    *(SECTION_PATH + key for key in SHAPE_KEYS),
    *(OBJECT_PATH + key for key in (*END_KEYS, LINING)),
)


@pytest.fixture
def real() -> SchemaView:
    return SchemaView(config.json_schema())


@pytest.mark.parametrize("path", PATHS)
def test_every_path_the_dock_binds_exists_in_the_engine(real: SchemaView, path: str) -> None:
    assert real.has(path)


def test_the_frozen_sample_still_matches_the_engine() -> None:
    assert json.loads(SAMPLE.read_text("utf-8")) == config.json_schema()


def test_schema_view_resolves_references_lists_and_nullable_fields(real: SchemaView) -> None:
    low, high = real.bounds(job_builder.DX)
    assert low < high
    assert real.default(job_builder.MANNING) > 0.0
    assert real.tip(job_builder.DX)
    assert set(real.enum(job_builder.BOUNDARY_KIND)) == {"stage", "normal", "free"}
    assert real.bounds(job_builder.CURVE_NUMBER)[1] == 100.0
    assert not real.has("grid.no_such_field")


def full_values(tmp_path: Path, **changes) -> dict:
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"x")
    line = [[400000.0, 2700000.0], [400100.0, 2700050.0]]
    ring = [[[400000.0, 2699000.0], [401000.0, 2699000.0], [401000.0, 2700000.0], [400000.0, 2699000.0]]]
    base = {
        "dem": str(dem), "crs": "EPSG:32640", "pixel": 0.5, "dx": 20.0, "manning": 0.04,
        "domain": [Feature("Polygon", ring)], "rain_mm_h": 25.0, "rain_hours": 6.0, "curve_number": 80.0,
        "duration_h": 12.0,
        "structures": {
            "crest_line": [Feature("LineString", line, {"crest_z": 512.0})],
            "wall": [Feature("LineString", line)],
            "spillway": [Feature("LineString", line, {"crest_z": 510.0, "coefficient": 2.1, "length": 50.0})],
            "burn_line": [Feature("LineString", line, {"crest_z": 498.0})],
        },
        "boundaries": [
            Feature("LineString", line, {"kind": "normal", "value": 0.01}),
            Feature("LineString", line, {"kind": "stage", "value": 2.0}),
            Feature("LineString", line, {"kind": "free", "value": None}),
        ],
        "design": [Feature("Point", [400050.0, 2699500.0], {"name": "Dam"}), Feature("LineString", line)],
    }  # fmt: skip
    return {**base, **changes}


def test_a_full_job_passes_the_engine_validation(tmp_path: Path) -> None:
    job = build_job(full_values(tmp_path), tmp_path / "out")
    parsed = config.RunConfig.model_validate(job)
    assert parsed.grid.dx == 20.0
    assert len(parsed.terrain.objects) == 4
    assert parsed.storm.kind == "uniform"
    assert parsed.storm.depth_mm == 150.0
    assert parsed.outputs.points[0].name == "Dam"


def test_every_shaped_kind_the_dock_offers_is_an_engine_kind() -> None:
    kinds = config.TerrainObject.model_fields["kind"].annotation.__args__
    assert set(SHAPED_KINDS) == set(config.SHAPED_KINDS)
    assert set(SHAPED_KINDS) <= set(kinds)


def test_jobs_with_every_shaped_object_pass_the_engine_validation(tmp_path: Path) -> None:
    table = tmp_path / "s.csv"
    table.write_text("station,bed_z,left_top_z,right_top_z\n0,100,103,102\n100,99,102,101\n", encoding="utf-8")
    line = [[400000.0, 2700000.0], [400100.0, 2700050.0]]
    structures = {
        "embankment": [Feature("LineString", line, {"crest_z": 110.0, "width": 6.0, "openings": "10-20 left; 40-50"})],
        "channel": [
            Feature("LineString", line, {"bed_start_z": 100.0, "bed_slope": 0.01, "width": 4.0, "lining_n": 0.02}),
        ],
        "channel_dyke": [
            Feature("LineString", line, {"table": str(table), "start_end": "taper", "taper_length": 30.0}),
            Feature("LineString", line, {"crest_z": 99.0, "top_z": 103.0, "end_end": "closed"}),
            Feature("LineString", line, {"crest_z": 99.0, "freeboard": 0.5, "water_depth": 2.0}),
        ],
    }
    data = full_values(tmp_path, structures=structures, terrain_map=True)
    parsed = config.RunConfig.model_validate(build_job(data, tmp_path / "out"))
    assert [o.kind for o in parsed.terrain.objects].count("channel_dyke") == 3
    assert parsed.outputs.terrain_map is True
    assert parsed.terrain.objects[0].openings[0].side == "left"
    assert config.RunConfig.model_validate(preview_job(data, tmp_path / "p")).storm.kind == "none"


def test_an_extent_job_passes_the_engine_validation(tmp_path: Path) -> None:
    values = full_values(tmp_path, domain=None, extent=(400000.0, 2699000.0, 401000.0, 2700000.0))
    assert config.RunConfig.model_validate(build_job(values, tmp_path / "out")).grid.extent is not None


def test_an_hms_job_passes_the_engine_validation(tmp_path: Path) -> None:
    job = build_job(full_values(tmp_path, hms={"folder": "x"}), tmp_path / "out")
    imported = {
        "storm": {"kind": "uniform", "depth_mm": 120.0, "duration_min": 1440.0},
        "hydrology": {"hms_basin": "b.basin", "subbasins": [{"name": "S1", "mode": "lumped"}]},
        "run": {"duration_s": 7200.0},
    }
    merged = merge_hms(job, imported, {"modes": {"S1": "2d"}})
    parsed = config.RunConfig.model_validate(merged)
    assert parsed.hydrology.subbasins[0].mode == "2d"


@pytest.mark.data
def test_the_block_2_project_goes_through_the_real_import_into_a_valid_job(
    hms_project_dir: Path, tmp_path: Path
) -> None:
    from wadi2d.engine.cli import main

    found = job_builder.hms_files(hms_project_dir)
    assert "FM_100yr.met" in found["met"]
    names = job_builder.hms_subbasins(hms_project_dir / "Basin_1.basin")
    assert len(names) == 18
    modes = dict.fromkeys(names, "lumped") | {names[0]: "2d"}
    hms = {
        "folder": str(hms_project_dir),
        "basin": "Basin_1.basin",
        "met": "FM_100yr.met",
        "control": "Control_1.control",
        "modes": modes,
    }
    imported = tmp_path / "hms_import.json"
    assert main(job_builder.hms_import_args(hms, imported)) == 0
    job = build_job(full_values(tmp_path, hms=hms), tmp_path / "out")
    merged = merge_hms(job, json.loads(imported.read_text("utf-8")), hms)
    parsed = config.RunConfig.model_validate(merged)
    assert parsed.storm.kind == "hypothetical"
    assert parsed.run.duration_s > 3600.0
    assert parsed.hydrology.hms_basin.endswith("Basin_1.basin")
    assert parsed.hydrology.subbasins[0].mode == "2d"
    assert parsed.hydrology.subbasins[0].outlet is not None
    assert parsed.hydrology.curve_number == 80.0
    assert parsed.terrain.manning == 0.04
