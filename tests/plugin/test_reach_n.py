# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The generated reaches' Manning n (W106, gap 7 of W104): written to the run's job and to the basin's, on a
generated basin only, and a saved model of before keeping Terrain's n with words."""

from __future__ import annotations

import json
from pathlib import Path

from tests.plugin.test_job_builder import values
from wadi2d_qgis import model_doc
from wadi2d_qgis.job_builder import basin_job, build_job


def _basin(tmp_path: Path) -> dict:
    path = tmp_path / "basin.json"
    path.write_text("{}", encoding="utf-8")
    return {"json": str(path), "modes": {"S1": "lumped"}, "settings": {"stream_threshold_km2": 7.5, "lag_method": "kirpich"}}


def test_the_reach_n_reaches_the_job_on_a_generated_basin_only(tmp_path: Path) -> None:
    given = {"reach_manning_n": 0.1, "reach_manning": {"R3": 0.07}}
    job = build_job(values(tmp_path, basin=_basin(tmp_path), **given), tmp_path / "out")
    assert job["hydrology"]["reach_manning_n"] == 0.1 and job["hydrology"]["reach_manning"] == {"R3": 0.07}
    plain = build_job(values(tmp_path, **given), tmp_path / "out")["hydrology"]
    assert "reach_manning_n" not in plain and "reach_manning" not in plain  # no generated basin: nothing to set
    kept = build_job(values(tmp_path, basin=_basin(tmp_path), reach_manning_n=None, reach_manning={}), tmp_path / "out")
    assert "reach_manning_n" not in kept["hydrology"] and "reach_manning" not in kept["hydrology"]


def test_the_basin_is_generated_with_it(tmp_path: Path) -> None:
    job = basin_job(values(tmp_path, basin=_basin(tmp_path), reach_manning_n=0.1), tmp_path / "out")
    assert job["hydrology"]["reach_manning_n"] == 0.1
    assert "reach_manning_n" not in basin_job(values(tmp_path, basin=_basin(tmp_path)), tmp_path / "out")["hydrology"]


def test_a_model_of_format_6_with_a_generated_basin_keeps_terrains_n() -> None:
    old = {"format": model_doc.FORMAT, "version": 6, "sections": {"hydrology": {"widgets": {"basin#checked": True}}}}
    doc = model_doc.loads(json.dumps(old))
    assert doc["sections"]["hydrology"]["widgets"]["reach_n"] == 0.0
    assert doc[model_doc.MIGRATED] == [model_doc.REACH_N_KEPT]
    hms = {**old, "sections": {"hydrology": {"widgets": {"basin#checked": False, "folder": "D:/hms"}}}}
    assert "reach_n" not in model_doc.loads(json.dumps(hms))["sections"]["hydrology"]["widgets"]
