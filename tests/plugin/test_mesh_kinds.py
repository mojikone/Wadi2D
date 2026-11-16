# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""W101 item 4: the Mesh section's kind, read from the two ticks a saved model holds; the job each kind's new settings
write, taken by the engine's schema; a job's settings read back; what Build mesh says."""

from __future__ import annotations

from wadi2d_qgis import job_states
from wadi2d_qgis.job_builder import build_job
from wadi2d_qgis.mesh_kinds import ALIGNED, QUADTREE, SQUARES, built_words, kind_of, switches

from wadi2d.config.schema import RunConfig


def values(tmp_path, **extra) -> dict:
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"x")
    return {
        "dem": str(dem), "crs": "EPSG:32640", "dx": 10.0, "manning": 0.04, "duration_h": 1.0, "output": str(tmp_path),
        "extent": (0.0, 0.0, 100.0, 100.0), "rain_mm_h": 10.0, "rain_hours": 1.0, **extra,
    }  # fmt: skip


def test_the_kind_is_the_two_ticks() -> None:
    assert kind_of(False, False) == SQUARES and kind_of(True, False) == QUADTREE and kind_of(False, True) == ALIGNED
    assert kind_of(True, True) == ALIGNED, "both on: the aligned mesh, which the engine refuses on the quadtree"
    for kind in (SQUARES, QUADTREE, ALIGNED):
        assert kind_of(*switches(kind)) == kind


def test_the_new_settings_reach_the_engine(tmp_path) -> None:
    banks = tmp_path / "suggest.gpkg"
    banks.write_bytes(b"x")
    strips = {"banks": str(banks), "generator": "centres", "gorge_rows": 4}
    floor = {"bank_rise_m": 2.0, "bank_scarp_m": 1.5, "bank_slope": 0.08, "bank_slope_cap": False}
    job = build_job(values(tmp_path, strips=strips, stream_km2=2.5, breaklines=floor), tmp_path / "a")
    assert job["strips"]["gorge_rows"] == 4 and job["mesh"] == {"stream_area_mid_km2": 2.5}
    assert job["breaklines"] == floor
    cfg = RunConfig.model_validate(job)
    assert cfg.strips.gorge_rows == 4 and cfg.mesh.stream_area_mid_km2 == 2.5 and not cfg.mesh.enabled
    assert (cfg.breaklines.bank_scarp_m, cfg.breaklines.bank_slope, cfg.breaklines.bank_slope_cap) == (1.5, 0.08, False)
    back = job_states.job_states(job, tmp_path / "elsewhere", tmp_path / "x.gpkg")["mesh"]["widgets"]
    assert (back["gorge_rows"], back["stream_area"], back["bank_scarp"], back["bank_slope_cap"]) == (4, 2.5, 1.5, False)


def test_a_job_without_them_is_the_job_of_before(tmp_path) -> None:
    job = build_job(values(tmp_path, breaklines={"bank_rise_m": 2.0}), tmp_path / "b")
    assert "mesh" not in job and "strips" not in job and job["breaklines"] == {"bank_rise_m": 2.0}


def test_what_build_mesh_says() -> None:
    aligned = {
        "kind": ALIGNED, "cells": 1200, "aligned": 200, "squares": 1000, "replaced": 180, "smallest_m2": 212.4,
        "smallest_m": 14.57, "left_out": ["Up"], "notes": ["hard line smoothed at a bend"],
    }  # fmt: skip
    text = built_words(aligned)
    assert "1,200 cells: 200 aligned along the streams, 1,000 squares" in text and "212 m2" in text
    assert "Left out of the mesh, lumped: Up." in text and "hard line smoothed at a bend." in text
    many = built_words({**aligned, "left_out": [], "notes": [f"note {n}" for n in range(13)]})
    assert "note 3." in many and "note 4." not in many and many.endswith("And 9 more of the kind.")
    assert built_words({"kind": SQUARES, "cells": 4000, "smallest_m": 20.0}) == "4,000 square cells of 20 m."
    quad = {"kind": QUADTREE, "cells": 900, "ratio": 2.5, "smallest_m": 10.0, "tiles_by_size": {"10 m": 2, "20 m": 0}}
    assert built_words(quad) == "900 cells, 2.5 x fewer than the uniform grid. Smallest cell 10 m. Tiles: 2 of 10 m."
