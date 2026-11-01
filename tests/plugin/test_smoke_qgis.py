# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Starts the headless smoke test on QGIS's Python; skipped on a machine without this QGIS."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

LAUNCHER = Path(os.environ.get("WADI2D_QGIS_PYTHON", r"C:\Program Files\QGIS 3.44.8\bin\python-qgis-ltr.bat"))
SMOKE = Path(__file__).with_name("smoke_qgis.py")
TIMEOUT_S = 240


needs_qgis = pytest.mark.skipif(not LAUNCHER.exists(), reason=f"no QGIS Python at {LAUNCHER}")


def run_smoke(*args: str) -> str:
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PYTHON")}
    env["QT_QPA_PLATFORM"] = "offscreen"
    done = subprocess.run(
        [str(LAUNCHER), str(SMOKE), sys.executable, *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
    )
    report = done.stdout + done.stderr
    assert done.returncode == 0, report
    assert "SMOKE PASSED" in done.stdout, report
    return done.stdout


@needs_qgis
def test_the_dock_runs_the_fake_engine_to_done_on_qgis_python() -> None:
    run_smoke()


@needs_qgis
def test_the_dock_runs_the_real_engine_to_done_on_qgis_python() -> None:
    pytest.importorskip("wadi2d.run")
    run_smoke("real")
