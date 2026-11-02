# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A real engine run, then its layers and sheets on QGIS's Python; skipped on a machine without this QGIS."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, write_dem

LAUNCHER = Path(os.environ.get("WADI2D_QGIS_PYTHON", r"C:\Program Files\QGIS 3.44.8\bin\python-qgis-ltr.bat"))
SHEETS = Path(__file__).with_name("sheets_qgis.py")
TIMEOUT_S = 240


@pytest.mark.skipif(not LAUNCHER.exists(), reason=f"no QGIS Python at {LAUNCHER}")
def test_a_finished_run_gives_styled_layers_and_a_pdf(tmp_path: Path) -> None:
    pytest.importorskip("wadi2d.run")
    from wadi2d.run import run_job

    x = (np.arange(120) + 0.5) * 5.0
    y = (np.arange(64) + 0.5) * 5.0
    xx, yy = np.meshgrid(x, y)
    bank = np.clip(np.abs(yy - 160.0) - 30.0, 0.0, 6.0) * 0.5
    dem = write_dem(tmp_path / "wadi.tif", 200.0 - 0.02 * xx + bank, 5.0)
    cfg = job(
        dem,
        30,
        16,
        20.0,
        terrain={"manning": 0.04},
        storm={"kind": "uniform", "depth_mm": 120.0, "duration_min": 30.0},
        boundaries=[{"kind": "free", "coordinates": [(X0 + 590.0, Y0), (X0 + 590.0, Y0 - 320.0)]}],
        run={"duration_s": 2400.0, "source_every_s": 30.0},
        outputs={"map_every_s": 300.0},
    )
    summary = run_job(cfg, tmp_path / "run")
    assert summary.exit_code == 0
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PYTHON")}
    done = subprocess.run(
        [str(LAUNCHER), str(SHEETS), str(tmp_path / "run")],
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    report = done.stdout + done.stderr
    assert "SHEETS PASSED" in done.stdout, report
