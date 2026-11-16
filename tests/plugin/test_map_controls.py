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


def test_the_window_asks_for_the_dems_own_pixel(tmp_path) -> None:
    box = (1000.0, 2000.0, 1500.25, 2600.0)
    folder = window_folder(tmp_path, box)
    assert folder == Path(tmp_path) / "pixels" / "windows" / "window_1000_2000_1500_2600_dem"
    assert window_args(tmp_path, box, folder) == [
        "window", str(tmp_path), "1000.000", "2000.000", "1500.250", "2600.000", "--pixel", "0", "--out", str(folder),
    ]
