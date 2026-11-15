# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A run's lumped network in its group, on QGIS's Python (W88); skipped without this QGIS or the engine."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

LAUNCHER = Path(os.environ.get("WADI2D_QGIS_PYTHON", r"C:\Program Files\QGIS 3.44.8\bin\python-qgis-ltr.bat"))
SCRIPT = Path(__file__).with_name("network_qgis.py")
TIMEOUT_S = 240


@pytest.mark.skipif(not LAUNCHER.exists(), reason=f"no QGIS Python at {LAUNCHER}")
def test_the_lumped_network_lands_in_the_runs_group_labelled_and_hatched(tmp_path: Path) -> None:
    pytest.importorskip("wadi2d.run")
    from tests.engine.test_lumped_network import net_job
    from wadi2d.run import run_job

    lumped = tmp_path / "valley" / "valley_hms"
    hybrid = tmp_path / "valley" / "valley_cut"
    cfg = net_job(tmp_path, low="lumped", entry="outlet", run={"lumped_only": True})
    assert run_job(cfg, lumped).exit_code == 0
    assert run_job(net_job(tmp_path, exclude=True), hybrid).exit_code == 0
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PYTHON")}
    env["QT_QPA_PLATFORM"] = "offscreen"
    done = subprocess.run(
        [str(LAUNCHER), str(SCRIPT), str(lumped), str(hybrid)], env=env, capture_output=True, text=True, timeout=TIMEOUT_S
    )
    assert "NETWORK PASSED" in done.stdout, done.stdout + done.stderr
