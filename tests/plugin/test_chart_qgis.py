# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The right-click on the map and the element chart on QGIS's Python (W64); skipped on a machine without this QGIS."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

LAUNCHER = Path(os.environ.get("WADI2D_QGIS_PYTHON", r"C:\Program Files\QGIS 3.44.8\bin\python-qgis-ltr.bat"))
CHART = Path(__file__).with_name("chart_qgis.py")
TIMEOUT_S = 240


@pytest.mark.skipif(not LAUNCHER.exists(), reason=f"no QGIS Python at {LAUNCHER}")
def test_a_right_click_on_an_element_opens_its_chart_in_the_panel(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PYTHON")}
    env["QT_QPA_PLATFORM"] = "offscreen"
    env.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))  # offscreen Qt finds no fonts on its own: the picture had no words
    out = Path(os.environ.get("WADI2D_CHART_OUT", tmp_path))
    done = subprocess.run(
        [str(LAUNCHER), str(CHART), str(out)], env=env, capture_output=True, text=True, timeout=TIMEOUT_S, check=False
    )
    report = done.stdout + done.stderr
    assert "CHART PASSED" in done.stdout, report
    assert (out / "chart_reservoir.png").is_file() and (out / "chart_subbasin.png").is_file()
