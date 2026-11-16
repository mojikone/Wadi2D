# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""W101 item 1: the rain sources, the area reduction in two parts and the Data tables, as plain values, and the job
the engine's own schema takes from them."""

from __future__ import annotations

import pytest
from wadi2d_qgis import model_doc, table_rows
from wadi2d_qgis.job_builder import build_job, merge_hms, problems
from wadi2d_qgis.reduction_rows import (
    AREA,
    COEFFICIENT,
    CURVE,
    HMS_SPLIT,
    NONE,
    SINGLE_WORDS,
    STUDY,
    STUDY_WANTS,
    factor_at,
    part,
    reduction_job,
)
from wadi2d_qgis.study_rows import study_problems, study_table

from wadi2d.config.rain import ArfTableConfig, PatternTable
from wadi2d.config.schema import RunConfig

CURVE_A = {"areas_km2": [10.0, 100.0, 1000.0], "factors": [0.99, 0.913, 0.7], "reduces_below_table": True}
PATTERN = {"time": [0.0, 25.0, 100.0], "depth": [0.0, 60.0, 100.0], "time_units": "percent", "form": "cumulative"}
STORE = {"patterns": {"Front loaded": PATTERN}, "arf_curves": {"Block 2": CURVE_A}}


def values(tmp_path, storm, reduction=None, **extra) -> dict:
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"x")
    found = {
        "dem": str(dem), "crs": "EPSG:32640", "dx": 10.0, "manning": 0.04, "duration_h": 2.0, "output": str(tmp_path),
        "extent": (0.0, 0.0, 100.0, 100.0), "storm": storm, "data_tables": STORE, **extra,
    }  # fmt: skip
    if reduction is not None:
        found["reduction"] = reduction
    return found


def both(entry: dict, **absent) -> dict:
    return {"lumped": entry, "grid": dict(entry), **{f"{k}_absent": v for k, v in absent.items()}}


FIXED = {"kind": "fixed", "depth_mm": 60.0, "hours": 1.0}


def test_a_fixed_depth_writes_the_job_the_steady_rain_wrote(tmp_path) -> None:
    old = build_job(values(tmp_path, None, rain_mm_h=60.0, rain_hours=1.0), tmp_path / "a")
    new = build_job(values(tmp_path, FIXED, both(part())), tmp_path / "b")
    assert new["storm"] == old["storm"] == {"kind": "uniform", "depth_mm": 60.0, "duration_min": 60.0}
    assert "data_tables" not in new  # a store nothing reads is not in the job
    assert problems(values(tmp_path, FIXED, both(part()))) == []


def test_one_reduction_for_every_part_keeps_the_single_storm_form(tmp_path) -> None:
    coefficient = build_job(values(tmp_path, FIXED, both(part(COEFFICIENT, coefficient=0.8))), tmp_path / "c")
    assert coefficient["storm"]["arf_factor"] == 0.8 and "area_reduction" not in coefficient["storm"]
    area = build_job(values(tmp_path, FIXED, both(part(AREA, "Block 2", 100.0))), tmp_path / "d")
    assert area["storm"]["storm_area_km2"] == 100.0
    assert area["storm"]["arf"] == {"areas_km2": [10.0, 100.0, 1000.0], "factors": [0.99, 0.913, 0.7]}
    for job in (coefficient, area):
        assert RunConfig.model_validate(job).storm.kind == "uniform"
    # a model with one part only (a 2D model) keeps the form too: the other part is absent, not none
    only = build_job(values(tmp_path, FIXED, {"lumped": part(), "grid": part(AREA, "Block 2", 100.0), "lumped_absent": True}), tmp_path / "e")
    assert only["storm"]["storm_area_km2"] == 100.0


def test_parts_that_differ_write_the_split_and_the_curves_they_name(tmp_path) -> None:
    split = {"lumped": part(CURVE, "Block 2"), "grid": part(AREA, "Block 2", 505.0)}
    job = build_job(values(tmp_path, FIXED, split), tmp_path / "f")
    assert job["storm"]["area_reduction"] == {
        "lumped": {"form": "curve", "curve": "Block 2"}, "grid": {"form": "area", "curve": "Block 2", "area_km2": 505.0},
    }  # fmt: skip
    assert job["data_tables"] == {"arf_curves": {"Block 2": {"areas_km2": CURVE_A["areas_km2"], "factors": CURVE_A["factors"]}}}
    cfg = RunConfig.model_validate(job)
    assert cfg.storm.area_reduction.grid.table.factors == [0.99, 0.913, 0.7]  # filled in from the store
    lumped_off = build_job(values(tmp_path, FIXED, {"lumped": part(), "grid": part(COEFFICIENT, coefficient=0.6)}), tmp_path / "g")
    assert lumped_off["storm"]["area_reduction"] == {"grid": {"form": "coefficient", "coefficient": 0.6}}


def test_depth_and_pattern_and_the_depth_grid(tmp_path) -> None:
    scs = {"kind": "depth", "depth_mm": 157.0, "hours": 24.0, "pattern": "scs:II"}
    job = build_job(values(tmp_path, scs, both(part(COEFFICIENT, coefficient=0.9))), tmp_path / "h")
    assert job["storm"] == {
        "kind": "depth", "depth_mm": 157.0, "duration_min": 1440.0, "pattern": {"kind": "scs", "scs_type": "II"},
        "area_reduction": {"lumped": {"form": "coefficient", "coefficient": 0.9}, "grid": {"form": "coefficient", "coefficient": 0.9}},
    }  # fmt: skip
    RunConfig.model_validate(job)
    stored = {"kind": "depth", "depth_mm": 80.0, "hours": 6.0, "pattern": "table:Front loaded"}
    job = build_job(values(tmp_path, stored, both(part())), tmp_path / "i")
    assert job["storm"]["pattern"] == {"kind": "table", "table": "Front loaded"}
    assert job["data_tables"] == {"patterns": {"Front loaded": {"time": PATTERN["time"], "depth": PATTERN["depth"]}}}
    assert RunConfig.model_validate(job).storm.pattern.values.depth == [0.0, 60.0, 100.0]
    uniform = build_job(values(tmp_path, {**stored, "pattern": "uniform"}, both(part())), tmp_path / "j")
    assert "pattern" not in uniform["storm"] and "data_tables" not in uniform
    raster = tmp_path / "pmp.tif"
    raster.write_bytes(b"x")
    grid = {"kind": "depth_grid", "raster": str(raster), "hours": 24.0, "pattern": "scs:I"}
    job = build_job(values(tmp_path, grid, both(part(AREA, "Block 2", 74.3))), tmp_path / "k")
    assert job["storm"]["kind"] == "depth_grid" and job["storm"]["depth_grid"] == str(raster.resolve())
    assert job["storm"]["area_reduction"]["grid"]["area_km2"] == 74.3  # a depth grid never takes the single-storm form
    RunConfig.model_validate(job)


def test_what_stops_a_run_is_said_in_words(tmp_path) -> None:
    scs_short = {"kind": "depth", "depth_mm": 50.0, "hours": 6.0, "pattern": "scs:II"}
    assert any("24-hour" in text for text in problems(values(tmp_path, scs_short, both(part()))))
    assert any("Set the depth" in text for text in problems(values(tmp_path, {**FIXED, "depth_mm": 0.0}, both(part()))))
    missing = {**FIXED}
    assert any('"Gone"' in text for text in problems(values(tmp_path, missing, both(part(AREA, "Gone", 10.0)))))
    assert any("coefficient lies above 0" in text for text in problems(values(tmp_path, FIXED, both(part(COEFFICIENT, coefficient=0.0)))))
    study = {"lumped": part(CURVE, "Block 2"), "grid": part(STUDY, "Block 2")}
    assert SINGLE_WORDS in problems(values(tmp_path, FIXED, study))
    lost_pattern = {"kind": "depth", "depth_mm": 50.0, "hours": 6.0, "pattern": "table:Gone"}
    assert any('pattern "Gone"' in text for text in problems(values(tmp_path, lost_pattern, both(part()))))
    bad = {"patterns": {}, "arf_curves": {"Falls": {"areas_km2": [100.0, 10.0], "factors": [0.9, 0.8]}}}
    found = problems({**values(tmp_path, FIXED, both(part(AREA, "Falls", 50.0))), "data_tables": bad})
    assert any("areas must rise" in text for text in found)


def test_the_hms_table_is_read_at_one_area_for_both_parts(tmp_path) -> None:
    rain = tmp_path / "rain.nc"
    rain.write_bytes(b"x")
    gridded = {"kind": "gridded", "file": str(rain), "units": "auto", "interval_min": 0.0, "stamp": "end"}
    hms = {"basin": "b", "met": "m", "control": "c", "folder": "f", "modes": {}}
    same = both(part(AREA, "(hms)", 74.3))
    job = build_job(values(tmp_path, gridded, same, hms=hms), tmp_path / "l")
    assert job["storm"]["storm_area_km2"] == 74.3 and "arf" not in job["storm"]  # the import fills it, as before W101
    table = {"areas_km2": [10.0, 1000.0], "factors": [1.0, 0.8]}
    merged = merge_hms(job, {"storm": {"arf": table}, "run": {}, "hydrology": {}}, hms)
    assert merged["storm"]["arf"] == table
    split = {"lumped": part(CURVE, "(hms)"), "grid": part(AREA, "(hms)", 74.3)}
    assert HMS_SPLIT in problems(values(tmp_path, gridded, split, hms=hms))


def test_the_study_reads_the_2d_parts_curve(tmp_path) -> None:
    study = {"lumped": part(CURVE, "Block 2"), "grid": part(STUDY, "Block 2", single_km2=74.3)}
    single = build_job(values(tmp_path, FIXED, study), tmp_path / "m")
    assert single["storm"]["area_reduction"]["grid"] == {"form": "area", "curve": "Block 2", "area_km2": 74.3}
    RunConfig.model_validate(single)
    for_study = build_job(values(tmp_path, FIXED, study, study={"n_areas": 3}), tmp_path / "n")
    assert for_study["storm"]["area_reduction"]["grid"] == {"form": "curve", "curve": "Block 2"}
    assert study_table(values(tmp_path, FIXED, study)) == CURVE_A
    assert STUDY_WANTS in study_problems(values(tmp_path, FIXED, both(part(AREA, "Block 2", 10.0))))
    assert STUDY_WANTS in problems(values(tmp_path, FIXED, both(part(AREA, "Block 2", 10.0)), for_study=True))


def test_observed_rain_takes_no_reduction(tmp_path) -> None:
    table = {"kind": "hyetograph", "rows": [(30.0, 10.0), (60.0, 25.0)]}
    job = build_job(values(tmp_path, table, both(part(COEFFICIENT, coefficient=0.5))), tmp_path / "o")
    assert set(job["storm"]) == {"kind", "hyetograph_min", "hyetograph_mm"}
    assert reduction_job(both(part(COEFFICIENT, coefficient=0.5)), "gauges", {}) == ({}, set())


def test_the_factor_is_read_as_the_engine_reads_it() -> None:
    import numpy as np

    from wadi2d.storm.arf import ArfTable

    for below in (True, False):
        curve = {**CURVE_A, "reduces_below_table": below}
        engine = ArfTable(np.array(curve["areas_km2"]), np.array(curve["factors"]), below)
        for area in (1.0, 10.0, 55.0, 100.0, 505.0, 1000.0, 5000.0):
            assert factor_at(curve, area) == pytest.approx(engine.factor(area), abs=1e-12)


@pytest.mark.parametrize(
    "table",
    [
        {"time": [0.0, 50.0], "depth": [0.0, 100.0], "time_units": "percent", "form": "cumulative"},
        {"time": [0.0, 100.0], "depth": [0.0, 0.0], "time_units": "percent", "form": "cumulative"},
        {"time": [10.0, 5.0, 100.0], "depth": [0.0, 1.0, 2.0], "time_units": "percent", "form": "cumulative"},
        {"time": [0.0, 30.0, 60.0], "depth": [0.0, 5.0, 3.0], "time_units": "minutes", "form": "cumulative"},
        {"time": [0.0, 1.0], "depth": [1.0, 2.0], "time_units": "fraction", "form": "incremental"},
        {"time": [30.0, 60.0], "depth": [4.0, 6.0], "time_units": "minutes", "form": "incremental"},
        {"time": [0.0, 0.5, 1.0], "depth": [0.0, 0.2, 1.0], "time_units": "fraction", "form": "cumulative"},
    ],
)
def test_a_pattern_is_refused_where_the_engine_refuses_it(table) -> None:
    try:
        PatternTable.model_validate(table)
        engine_ok = True
    except ValueError:
        engine_ok = False
    assert (table_rows.pattern_problems("p", table) == []) == engine_ok


def test_a_curve_the_engine_takes_is_taken() -> None:
    ArfTableConfig.model_validate({k: v for k, v in CURVE_A.items()})
    assert table_rows.curve_problems("c", CURVE_A) == []
    assert table_rows.curve_problems("c", {"areas_km2": [1.0], "factors": [0.9, 0.8]})


def _doc(storm: dict, hydrology: dict | None = None) -> dict:
    return {"format": model_doc.FORMAT, "version": 2, "sections": {"storm": {"widgets": storm}, "hydrology": {"widgets": hydrology or {}}}}


def test_a_model_of_format_2_is_brought_up_in_words() -> None:
    steady = model_doc.loads(model_doc.dumps(_doc({"kind": {"data": "single"}, "single": {"data": "uniform"}, "rain": 40.0, "hours": 0.5})))
    storm = steady["sections"]["storm"]["widgets"]
    assert (storm["kind"]["data"], storm["fixed_depth"], storm["hours"]) == ("fixed", 20.0, 0.5)
    assert "rain" not in storm and "single" not in storm
    assert any("fixed depth of 20 mm" in text for text in steady[model_doc.MIGRATED])
    design = model_doc.loads(model_doc.dumps(_doc({
        "kind": {"data": "hypothetical"}, "design_depth": 120.0, "design_hours": 6.0,
        "pattern": [[0.0, 0.0], [100.0, 100.0]], "arf_mode": {"data": "area"}, "storm_area": 74.3,
        "arf": [[10.0, 0.99], [100.0, 0.913]],
    })))  # fmt: skip
    storm, reduction = (design["sections"][k]["widgets"] for k in ("storm", "reduction"))
    store = design["sections"]["tables"]["extra"]["store"]
    assert storm["kind"]["data"] == "depth" and storm["depth_pattern"]["data"] == "table:Design pattern"
    assert store["patterns"]["Design pattern"]["depth"] == [0.0, 100.0]
    assert store["arf_curves"]["Area reduction"]["factors"] == [0.99, 0.913]
    assert reduction["lumped.form"]["data"] == reduction["grid.form"]["data"] == "area"
    assert reduction["grid.area"] == 74.3
    given = model_doc.loads(model_doc.dumps(_doc({"kind": {"data": "gridded"}, "arf_mode": {"data": "given"}, "arf_factor": 0.7})))
    assert given["sections"]["reduction"]["widgets"]["grid.coefficient"] == 0.7
    by_element = model_doc.loads(model_doc.dumps(_doc({"kind": {"data": "hms"}}, {"arf_by_element": True})))
    assert by_element["sections"]["reduction"]["widgets"]["by_element"] is True
    assert "arf_by_element" not in by_element["sections"]["hydrology"]["widgets"]


def test_the_lumped_curve_in_a_lumped_model_is_the_by_element_rule(tmp_path) -> None:
    reduction = {"lumped": part(CURVE, "Block 2"), "grid": part(), "grid_absent": True}
    job = build_job(values(tmp_path, FIXED, reduction, lumped_only=True), tmp_path / "p")
    assert job["storm"]["area_reduction"] == {"lumped": {"form": "curve", "curve": "Block 2"}}
    assert "arf_by_element" not in job["hydrology"]
    assert part()["form"] == NONE
