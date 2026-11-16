# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""W101, his item 7: the map pixel and the depth x speed raster in the job, written only when set; the window's
command."""

from __future__ import annotations

from pathlib import Path

from wadi2d_qgis.job_builder import build_job
from wadi2d_qgis.window_rows import window_args, window_folder

from wadi2d.config.schema import RunConfig


def values(tmp_path, **extra) -> dict:
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"x")
    return {
        "dem": str(dem), "crs": "EPSG:32640", "dx": 10.0, "manning": 0.04, "duration_h": 1.0, "output": str(tmp_path),
        "extent": (0.0, 0.0, 100.0, 100.0), "rain_mm_h": 10.0, "rain_hours": 1.0, **extra,
    }  # fmt: skip


def test_at_the_defaults_the_job_is_the_one_before(tmp_path) -> None:
    job = build_job(values(tmp_path, pixels=True, map_pixel=None, dv_raster=False), tmp_path / "a")
    assert "pixels" not in job["outputs"]


def test_a_pixel_and_the_raster_are_written_and_taken(tmp_path) -> None:
    job = build_job(values(tmp_path, pixels=True, map_pixel=10.0, dv_raster=True), tmp_path / "b")
    assert job["outputs"]["pixels"] == {"pixel_m": 10.0, "dv_raster": True}
    pixels = RunConfig.model_validate(job).outputs.pixels
    assert (pixels.pixel_m, pixels.dv_raster, pixels.surface) == (10.0, True, "continuous")


def test_no_pixel_maps_take_no_pixel(tmp_path) -> None:
    job = build_job(values(tmp_path, pixels=False, map_pixel=10.0, dv_raster=True), tmp_path / "c")
    assert job["outputs"]["pixels"] == {"enabled": False}


def test_one_depth_threshold_sets_every_floor(tmp_path) -> None:
    job = build_job(values(tmp_path, pixels=True, map_threshold=0.1), tmp_path / "t")
    assert job["outputs"]["pixels"] == {"depth_floor": 0.1, "hazard_depth_floor": 0.1, "cell_depth_floor": 0.1}
    pixels = RunConfig.model_validate(job).outputs.pixels
    assert (pixels.depth_floor, pixels.hazard_depth_floor, pixels.cell_depth_floor) == (0.1, 0.1, 0.1)
    off = build_job(values(tmp_path, pixels=False, map_threshold=0.2), tmp_path / "u")
    assert off["outputs"]["pixels"] == {"enabled": False, "depth_floor": 0.2, "hazard_depth_floor": 0.2, "cell_depth_floor": 0.2}
    assert "pixels" not in build_job(values(tmp_path, pixels=True, map_threshold=None), tmp_path / "v")["outputs"]


def test_a_model_and_a_job_from_before_keep_the_engines_floors(tmp_path) -> None:
    import json

    from wadi2d_qgis import job_states, model_doc

    doc = {"format": model_doc.FORMAT, "version": 3, "sections": {"run": {"widgets": {"folder": "x"}}}}
    brought = model_doc.loads(json.dumps(doc))
    assert brought["sections"]["run"]["widgets"]["cutoff"] < 0.0 and not brought.get(model_doc.MIGRATED)
    old = build_job(values(tmp_path, pixels=True), tmp_path / "w")
    assert job_states.job_states(old, tmp_path)["run"]["widgets"]["cutoff"] < 0.0
    new = build_job(values(tmp_path, pixels=True, map_threshold=0.15), tmp_path / "x")
    assert job_states.job_states(new, tmp_path)["run"]["widgets"]["cutoff"] == 0.15


def test_the_window_asks_for_the_dems_own_pixel(tmp_path) -> None:
    box = (1000.0, 2000.0, 1500.25, 2600.0)
    folder = window_folder(tmp_path, box)
    assert folder == Path(tmp_path) / "pixels" / "windows" / "window_1000_2000_1500_2600_dem"
    assert window_args(tmp_path, box, folder) == [
        "window", str(tmp_path), "1000.000", "2000.000", "1500.250", "2600.000", "--pixel", "0", "--out", str(folder),
    ]
