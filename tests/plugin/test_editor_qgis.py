# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The profile editor on QGIS's Python, with real mouse and key events; skipped on a machine without this QGIS."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tests.engine.conftest import write_dem

LAUNCHER = Path(os.environ.get("WADI2D_QGIS_PYTHON", r"C:\Program Files\QGIS 3.44.8\bin\python-qgis-ltr.bat"))
EDITOR = Path(__file__).with_name("editor_qgis.py")
TIMEOUT_S = 240


@pytest.mark.skipif(not LAUNCHER.exists(), reason=f"no QGIS Python at {LAUNCHER}")
def test_the_editor_takes_drags_typing_undo_and_save(tmp_path: Path) -> None:
    x = (np.arange(100) + 0.5) * 5.0
    dem = write_dem(tmp_path / "dem.tif", np.tile(105.0 - 0.02 * x, (100, 1)), 5.0)
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PYTHON")}
    env["QT_QPA_PLATFORM"] = "offscreen"
    done = subprocess.run(
        [str(LAUNCHER), str(EDITOR), str(dem), str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    report = done.stdout + done.stderr
    assert "EDITOR PASSED" in done.stdout, report
