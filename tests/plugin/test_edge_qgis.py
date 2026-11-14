# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The domain edge checks on the map (W78), on QGIS's Python; skipped on a machine without this QGIS. The run folders
are written by the engine's own writer, so the file the dock reads is the file a run makes."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

LAUNCHER = Path(os.environ.get("WADI2D_QGIS_PYTHON", r"C:\Program Files\QGIS 3.44.8\bin\python-qgis-ltr.bat"))
SCRIPT = Path(__file__).with_name("edge_qgis.py")
TIMEOUT_S = 240


@pytest.mark.skipif(not LAUNCHER.exists(), reason=f"no QGIS Python at {LAUNCHER}")
def test_edge_checks_land_in_inputs_boundaries_and_a_clean_run_adds_none(tmp_path: Path) -> None:
    edge = pytest.importorskip("wadi2d.edge_valleys")
    from rasterio.crs import CRS

    crs = CRS.from_epsg(32640).to_wkt()
    run = tmp_path / "bidah"
    run.mkdir()
    edge.write_crossings(
        run,
        [
            edge.Crossing(439281.0, 2728700.0, edge.LEAVES, 0.43),
            edge.Crossing(437300.0, 2727855.0, edge.ENTERS, 3.41),
        ],
        crs,
    )
    edge.write_pools(run, [edge.Pool(439416.0, 2728690.0, edge.POOL, 4.3, 77.0, 0.0, 100.0, 0.034)], crs)
    (tmp_path / "bidah_2").mkdir()
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PYTHON")}
    env["QT_QPA_PLATFORM"] = "offscreen"
    done = subprocess.run(
        [str(LAUNCHER), str(SCRIPT), str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
    )
    assert "EDGE PASSED" in done.stdout, done.stdout + done.stderr
