# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The dock's four model types (W99): what each shows, sets and needs, and that the engine takes the job of each."""

from __future__ import annotations

from pathlib import Path

import pytest
from wadi2d_qgis import model_types
from wadi2d_qgis.job_builder import Feature, build_job, problems
from wadi2d_qgis.model_types import HYBRID_2D, HYBRID_LUMPED, LUMPED, TWO_D, TYPES, apply_type

HMS = {
    "folder": "hms",
    "basin": "a.basin",
    "met": "a.met",
    "control": "a.control",
    "modes": {"S1": "lumped", "S2": "2d"},
}


def values(**more) -> dict:
    base = {
        "dem": "dem.tif", "crs": "EPSG:32640", "pixel": 5.0, "dx": 30.0, "manning": 0.045, "duration_h": 2.0,
        "output": "out", "rain_mm_h": 40.0, "rain_hours": 0.5, "handbacks": [], "exclude_lumped": False,
        "domain": [Feature("Polygon", [[[0.0, 0.0], [90.0, 0.0], [90.0, 90.0], [0.0, 0.0]]])],
    }  # fmt: skip
    return {**base, **more}


def lumped_values(**more) -> dict:
    return values(
        **{"hms": dict(HMS), "lumped_entry": "network", "lumped_only": False, "arf_by_element": False, **more}
    )


def test_no_type_is_the_dock_as_it_was(tmp_path: Path) -> None:
    raw = lumped_values()
    assert apply_type(raw, None) is raw
    assert model_types.sections_shown(None) == model_types.ALL_SECTIONS
    assert "model_type" not in build_job(values(), tmp_path)["run"]


def test_each_type_shows_its_sections() -> None:
    assert model_types.sections_shown(TWO_D) == model_types.ALL_SECTIONS
    hidden = set(model_types.ALL_SECTIONS) - set(model_types.sections_shown(LUMPED))
    assert hidden == {"mesh", "boundaries", "study"}
    assert model_types.sections_shown(LUMPED, show_all=True) == model_types.ALL_SECTIONS
    for kind in (HYBRID_LUMPED, HYBRID_2D):
        assert model_types.sections_shown(kind) == model_types.ALL_SECTIONS


def test_two_d_leaves_the_lumped_part_out_of_the_job(tmp_path: Path) -> None:
    raw = lumped_values(
        exclude_lumped=True,
        handbacks=[Feature("LineString", [[0, 0], [1, 1]], {"name": "h", "element": "E"})],
    )
    typed = apply_type(raw, TWO_D)
    assert "hms" not in typed and typed["handbacks"] == [] and typed["exclude_lumped"] is False
    assert "hms" in raw and raw["exclude_lumped"] is True  # the dock's own values are not touched
    job = build_job(typed, tmp_path)
    assert (
        job["run"]["model_type"] == "2d"
        and "exclude_lumped" not in job["grid"]
        and "lumped_entry" not in job["hydrology"]
    )
    assert model_types.type_notes(raw, TWO_D) == [model_types.UNUSED_LUMPED]
    assert model_types.type_notes(values(), TWO_D) == []


def test_lumped_is_the_network_alone(tmp_path: Path) -> None:
    typed = apply_type(lumped_values(arf_by_element=True, exclude_lumped=True), LUMPED)
    job = build_job(typed, tmp_path)
    assert job["run"]["lumped_only"] is True and job["run"]["model_type"] == "lumped"
    assert job["hydrology"]["arf_by_element"] is True and "exclude_lumped" not in job["grid"]
    assert "lumped_entry" not in job["hydrology"]
    assert typed["hms"]["modes"] == HMS["modes"]  # the mode of each subbasin stays the table's


def test_the_hybrids_differ_in_the_mesh_and_the_entry(tmp_path: Path) -> None:
    left_out = build_job(
        apply_type(lumped_values(lumped_only=True, arf_by_element=True), HYBRID_LUMPED), tmp_path
    )
    assert left_out["grid"]["exclude_lumped"] is True and left_out["run"]["model_type"] == "hybrid_lumped"
    assert "lumped_only" not in left_out["run"] and "arf_by_element" not in left_out["hydrology"]
    assert left_out["hydrology"]["lumped_entry"] == "network"  # a choice the type leaves
    kept = build_job(apply_type(lumped_values(exclude_lumped=True), HYBRID_2D), tmp_path)
    assert "exclude_lumped" not in kept["grid"] and kept["run"]["model_type"] == "hybrid_2d"
    assert "lumped_entry" not in kept["hydrology"]  # the outlets, the engine's default: the 2D model routes


@pytest.mark.parametrize("kind", [LUMPED, HYBRID_LUMPED, HYBRID_2D])
def test_a_type_with_a_lumped_part_needs_one(kind: str) -> None:
    words = model_types.NEEDS_LUMPED.format(title=TYPES[kind].title)
    assert words in problems(apply_type(values(), kind))
    assert words not in problems(apply_type(lumped_values(), kind))
    assert model_types.type_problems(apply_type(values(), TWO_D)) == []


def test_a_model_with_no_type_runs_as_the_engine_would_read_it() -> None:
    assert model_types.inferred(values()) == TWO_D
    assert model_types.inferred(lumped_values()) == HYBRID_2D
    assert model_types.inferred(lumped_values(exclude_lumped=True)) == HYBRID_LUMPED
    assert model_types.inferred(lumped_values(lumped_only=True, exclude_lumped=True)) == LUMPED
    assert model_types.inferred(values(basin={"json": "basin.json"})) == HYBRID_2D


# Against the engine: these may import it; the plugin never does.


def test_the_types_are_the_engines() -> None:
    land = pytest.importorskip("wadi2d.config.land")
    assert tuple(TYPES) == land.MODEL_TYPES
    assert (TWO_D, LUMPED, HYBRID_LUMPED, HYBRID_2D) == (
        land.MODEL_2D, land.MODEL_LUMPED, land.MODEL_HYBRID_LUMPED, land.MODEL_HYBRID_2D,
    )  # fmt: skip


def test_the_engine_infers_as_the_dock_does(tmp_path: Path) -> None:
    schema = pytest.importorskip("wadi2d.config.schema")
    engine_types = pytest.importorskip("wadi2d.config.model_type")
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"")
    job = build_job(apply_type(values(dem=str(dem)), TWO_D), tmp_path / "run")
    cfg = schema.RunConfig.model_validate(job)
    assert engine_types.model_type(cfg) == "2d" and engine_types.model_type_problems(cfg) == []
    untyped = schema.RunConfig.model_validate(build_job(values(dem=str(dem)), tmp_path / "run"))
    assert engine_types.inferred_type(untyped) == model_types.inferred(values())


def test_the_hybrids_set_a_generated_basins_rule_and_leave_an_hms_project_alone(tmp_path) -> None:
    """W106 gap 3: on a generated basin Hybrid Lumped ends the lumped model at its last points and Hybrid 2D routes no
    reach or reservoir lumped; the job carries the rule, an HMS project's job does not."""
    from tests.plugin.test_job_builder import values as job_values
    from tests.plugin.test_reach_n import _basin
    from wadi2d_qgis.job_builder import build_job
    from wadi2d_qgis.model_types import GENERATED_RULES, HYBRID_2D, HYBRID_LUMPED, LUMPED, TWO_D, apply_type

    generated = {"basin": {"json": "b.json"}}
    assert apply_type(generated, HYBRID_LUMPED)["generated_entry"] == GENERATED_RULES[HYBRID_LUMPED] == "last_points"
    assert apply_type(generated, HYBRID_2D)["generated_entry"] == GENERATED_RULES[HYBRID_2D] == "outlets"
    for kind in (LUMPED, TWO_D, None):
        assert "generated_entry" not in apply_type(generated, kind)
    assert "generated_entry" not in apply_type({"hms": {"folder": "x"}}, HYBRID_2D)
    job = build_job(apply_type(job_values(tmp_path, basin=_basin(tmp_path)), HYBRID_2D), tmp_path / "out")
    assert job["hydrology"]["generated_entry"] == "outlets" and job["run"]["model_type"] == "hybrid_2d"
