# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The layer tree's pattern on QGIS's Python (W68); skipped on a machine without this QGIS."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

LAUNCHER = Path(os.environ.get("WADI2D_QGIS_PYTHON", r"C:\Program Files\QGIS 3.44.8\bin\python-qgis-ltr.bat"))
GROUPS = Path(__file__).with_name("groups_qgis.py")
TIMEOUT_S = 240


@pytest.mark.skipif(not LAUNCHER.exists(), reason=f"no QGIS Python at {LAUNCHER}")
def test_one_group_per_model_and_a_rerun_replaces_only_its_own_results(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PYTHON")}
    env["QT_QPA_PLATFORM"] = "offscreen"
    done = subprocess.run(
        [str(LAUNCHER), str(GROUPS), str(tmp_path)], env=env, capture_output=True, text=True, timeout=TIMEOUT_S
    )
    report = done.stdout + done.stderr
    assert "GROUPS PASSED" in done.stdout, report
