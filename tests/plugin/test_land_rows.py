# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""W101 item 2: Manning in its four forms and the CN override, the job each writes and the engine's schema takes, and
what is refused in words."""

from __future__ import annotations

from wadi2d_qgis import job_states, land_rows
from wadi2d_qgis.job_builder import build_job, problems

from wadi2d.config.schema import RunConfig


def values(tmp_path, **extra) -> dict:
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"x")
    landuse = tmp_path / "landuse.tif"
    landuse.write_bytes(b"x")
    return {
        "dem": str(dem), "crs": "EPSG:32640", "dx": 10.0, "manning": 0.04, "duration_h": 1.0, "output": str(tmp_path),
        "extent": (0.0, 0.0, 100.0, 100.0), "rain_mm_h": 10.0, "rain_hours": 1.0, **extra,
    }  # fmt: skip


def rough(form, tmp_path, **extra) -> dict:
    return {"form": form, "n": 0.04, "n_aligned": 0.06, "land_use": str(tmp_path / "landuse.tif"), "classes": [], **extra}


def test_one_value_and_a_grid_write_the_job_they_always_wrote(tmp_path) -> None:
    plain = build_job(values(tmp_path), tmp_path / "a")
    for form in (land_rows.ONE, land_rows.GRID):
        job = build_job(values(tmp_path, roughness=rough(form, tmp_path)), tmp_path / "a")
        assert job["terrain"] == plain["terrain"] and "roughness" not in job["terrain"]


def test_split_and_land_use_write_the_roughness_the_engine_takes(tmp_path) -> None:
    split = build_job(values(tmp_path, roughness=rough(land_rows.SPLIT, tmp_path)), tmp_path / "b")
    assert split["terrain"]["roughness"] == {"form": "split", "n": 0.04, "n_aligned": 0.06}
    classes = [(1.0, 0.035, "plain"), (2.0, 0.08, "")]
    land = build_job(values(tmp_path, roughness=rough(land_rows.LAND, tmp_path, classes=classes)), tmp_path / "c")
    assert land["terrain"]["roughness"]["classes"] == [{"code": 1, "n": 0.035, "name": "plain"}, {"code": 2, "n": 0.08}]
    RunConfig.model_validate(land)
    assert "terrain.roughness" not in str(problems(values(tmp_path, roughness=rough(land_rows.LAND, tmp_path, classes=classes))))


def test_what_stops_a_run_is_said(tmp_path) -> None:
    assert land_rows.SPLIT_WORDS in problems(values(tmp_path, roughness=rough(land_rows.SPLIT, tmp_path)))
    assert any("Fill the table" in text for text in problems(values(tmp_path, roughness=rough(land_rows.LAND, tmp_path))))
    twice = rough(land_rows.LAND, tmp_path, classes=[(1.0, 0.03, ""), (1.0, 0.05, "")])
    assert any("twice" in text for text in problems(values(tmp_path, roughness=twice)))
    overlap = {"by": "range", "ranges": [(10.0, 50.0, 70.0), (40.0, 90.0, 80.0)]}
    assert any("overlap" in text for text in problems(values(tmp_path, cn_override=overlap)))
    assert any("names its subbasin" in text for text in problems(values(tmp_path, cn_override={"by": "subbasin", "subbasins": [("", 80.0)]})))


def test_the_cn_override_in_its_three_forms(tmp_path) -> None:
    by_range = build_job(values(tmp_path, cn_override={"by": "range", "ranges": [(1.0, 60.0, 70.0), (60.5, 100.0, 90.0)]}), tmp_path / "d")
    assert by_range["hydrology"]["cn_override"] == {
        "by": "range", "ranges": [{"low": 1.0, "high": 60.0, "curve_number": 70.0}, {"low": 60.5, "high": 100.0, "curve_number": 90.0}],
    }  # fmt: skip
    RunConfig.model_validate(by_range)
    land = {"by": "land_use", "land_use": str(tmp_path / "landuse.tif"), "classes": [(3.0, 85.0, "town")]}
    job = build_job(values(tmp_path, cn_override=land), tmp_path / "e")
    assert job["hydrology"]["cn_override"]["classes"] == [{"code": 3, "curve_number": 85.0, "name": "town"}]
    subbasin = build_job(values(tmp_path, cn_override={"by": "subbasin", "subbasins": [("S13", 82.0)]}), tmp_path / "f")
    assert subbasin["hydrology"]["cn_override"] == {"by": "subbasin", "subbasins": [{"name": "S13", "curve_number": 82.0}]}
    assert "cn_override" not in build_job(values(tmp_path, cn_override={"by": "none"}), tmp_path / "g")["hydrology"]


def test_a_job_gives_its_forms_back(tmp_path) -> None:
    classes = [(1.0, 0.035, "plain")]
    job = build_job(values(tmp_path, roughness=rough(land_rows.LAND, tmp_path, classes=classes),
                           cn_override={"by": "range", "ranges": [(0.0, 60.0, 70.0)]}), tmp_path / "h")  # fmt: skip
    states = job_states.job_states(job, tmp_path)
    ground, hydro = states["terrain"]["widgets"], states["hydrology"]["widgets"]
    assert ground["manning_form"]["data"] == "land_use" and ground["rough_classes"] == [[1, 0.035, "plain"]]
    assert hydro["cn_by"]["data"] == "range" and hydro["cn_table"] == [[0.0, 60.0, 70.0]]
