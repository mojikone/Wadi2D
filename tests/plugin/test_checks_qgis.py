# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A run's pits and step limiter cells on the map (W85), on QGIS's Python; skipped on a machine without this QGIS.
The run folders are written by the engine's own writers, so the files the dock reads are the files a run makes.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

LAUNCHER = Path(os.environ.get("WADI2D_QGIS_PYTHON", r"C:\Program Files\QGIS 3.44.8\bin\python-qgis-ltr.bat"))
SCRIPT = Path(__file__).with_name("checks_qgis.py")
TIMEOUT_S = 240


@pytest.mark.skipif(not LAUNCHER.exists(), reason=f"no QGIS Python at {LAUNCHER}")
def test_pits_and_limiter_cells_land_in_inputs_terrain_and_a_clean_run_adds_none(tmp_path: Path) -> None:
    pits = pytest.importorskip("wadi2d.terrain.pits")
    limiter = pytest.importorskip("wadi2d.engine.step_limiter")
    from rasterio.crs import CRS

    crs = CRS.from_epsg(32640).to_wkt()
    run = tmp_path / "wadi"
    run.mkdir()
    found = [
        pits.Pit(
            414801.0,
            2722476.0,
            117.07,
            280.1,
            11123.1,
            1181.6,
            1064.53,
            ((30, 31), (31, 30), (31, 31), (30, 30)),
        ),
        pits.Pit(438521.0, 2739036.0, 12.47, 508.5, 1595.4, 46.97, 34.5, ((5, 6),)),
    ]
    assert pits.write_pits(run, found, crs, filled=False) == run / pits.FILE
    log = limiter.LimiterLog(None, None, None)
    log.cells[(31, 30, "x")] = {
        "ticks": 130, "t_first_s": 40000.0, "t_last_s": 108000.0, "dt_min_s": 0.199, "x": 414781.0, "y": 2722476.0,
        "axis": "x", "crest": 0, **{name: 1.0 for name in limiter.KEPT},
    }  # fmt: skip
    assert log.write(run, crs) == run / limiter.FILE
    (tmp_path / "wadi_2").mkdir()
    assert pits.write_pits(tmp_path / "wadi_2", [], crs, filled=False) is None
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PYTHON")}
    env["QT_QPA_PLATFORM"] = "offscreen"
    done = subprocess.run(
        [str(LAUNCHER), str(SCRIPT), str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
    )
    assert "CHECKS PASSED" in done.stdout, done.stdout + done.stderr
