# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A CN value beside a CN grid, for the grid's holes (W106, gap 1 of W104): the words before a run, which subbasins
keep their rain off the grid, the saved model of before, and the status line. The count itself needs GDAL and is
checked through the real dock."""

from __future__ import annotations

import json

from wadi2d_qgis import cn_holes, model_doc
from wadi2d_qgis import section_status as s


def _model() -> dict:
    """S1 and S2 drain to the dam D, S3 to J below it; S4 lacks its CN; J2 a junction above S2's."""
    def element(name, kind, downstream, missing=()):
        return {"name": name, "kind": kind, "downstream": downstream, "missing": list(missing)}

    return {
        "elements": [
            element("S1", "subbasin", "J2"),
            element("J2", "junction", "R1"),
            element("R1", "reach", "D"),
            element("S2", "subbasin", "D"),
            element("D", "reservoir", "R2"),
            element("R2", "reach", "J"),
            element("S3", "subbasin", "J"),
            element("S4", "subbasin", "D", ["curve_number"]),
            element("J", "junction", None),
        ]
    }


def test_lumped_above_every_dam_by_default_and_the_named_points() -> None:
    model = _model()
    assert cn_holes.lumped_above(model, None) == {"S1", "S2"}  # S4 lacks its CN: it is on the grid
    assert cn_holes.lumped_above(model, ["J2"]) == {"S1"}
    assert cn_holes.lumped_above(model, ["J"]) == {"S1", "S2", "S3"}
    assert cn_holes.lumped_above(model, []) == set()


def test_lumped_of_a_job(tmp_path) -> None:
    basin = tmp_path / "basin.json"
    basin.write_text(json.dumps(_model()), encoding="utf-8")
    job = {"hydrology": {"basin_json": str(basin), "subbasins": [{"name": "S3", "mode": "2d"}]}, "run": {}}
    gpkg, names, sure = cn_holes.lumped_of_job(job)
    assert gpkg == str(tmp_path / "basin.gpkg") and names == {"S1", "S2"} and sure  # every complete one but S3
    job["run"]["model_type"] = "hybrid_2d"
    job["hydrology"]["generated_entry"] = "outlets"
    assert cn_holes.lumped_of_job(job)[1] == {"S1", "S2"}  # above the dam alone
    job["hydrology"]["last_points"] = ["J2"]
    assert cn_holes.lumped_of_job(job)[1] == {"S1"}
    assert cn_holes.lumped_of_job({"hydrology": {"hms_basin": "x.basin"}}) == (None, set(), False)


def test_words_and_what_needs_no_count() -> None:
    said = cn_holes.holes_words(14561, 20.0, True)
    assert "14,561 cells of 20 m" in said and "5.82 km2" in said and "Curve number" in said
    assert "if they are rained on" in cn_holes.holes_words(10, 20.0, False)
    grid = {"grid": {"dx": 20.0, "domain": "d.geojson"}, "terrain": {"cn_raster": "cn.tif"}, "hydrology": {}, "run": {}}
    assert cn_holes.check_job({**grid, "hydrology": {"curve_number": 88.0}}) is None  # a value fills the holes
    assert cn_holes.check_job({**grid, "run": {"lumped_only": True}}) is None  # no rain on a grid
    assert cn_holes.check_job({**grid, "terrain": {}}) is None  # no grid


def test_a_model_of_format_6_keeps_its_job() -> None:
    old = {
        "format": model_doc.FORMAT, "version": 6,
        "sections": {"hydrology": {"widgets": {"cn.box": 80.0, "cn.raster": {"source": "cn.tif"}}}},
    }  # fmt: skip
    doc = model_doc.loads(json.dumps(old))
    assert doc["version"] == model_doc.VERSION == 7
    assert doc["sections"]["hydrology"]["widgets"]["cn.box"] == 0.0  # greyed out and unused before: empty now
    alone = {**old, "sections": {"hydrology": {"widgets": {"cn.box": 80.0, "cn.raster": None}}}}
    assert model_doc.loads(json.dumps(alone))["sections"]["hydrology"]["widgets"]["cn.box"] == 80.0
    assert not doc.get(model_doc.MIGRATED)


def test_status_words_name_the_value_of_the_holes() -> None:
    words = s.hydrology("2d", None, False, False, False, 0, 0, 88.0, "CN grid", None).words
    assert words == "Curve number from CN grid, 88 where it has none"
    assert s.hydrology("2d", None, False, False, False, 0, 0, None, "CN grid", None).words == "Curve number from CN grid"
