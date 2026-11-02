# Wadi2D engine tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A run from a plain shell on a PC where another program's GDAL has set PROJ_LIB and GDAL_DATA for the whole account."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from wadi2d.engine.cli import FOREIGN_ENV, main

LOOKUP = "from rasterio.crs import CRS; print(CRS.from_epsg(32640).to_epsg())"


def python(code: str, folder: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, **{name: str(folder) for name in FOREIGN_ENV}}
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)


def foreign_folder(tmp_path: Path) -> Path:
    (tmp_path / "proj.db").write_bytes(b"")
    return tmp_path


def test_a_foreign_proj_folder_breaks_a_lookup_and_the_engine_is_spared(tmp_path: Path) -> None:
    folder = foreign_folder(tmp_path)
    assert python(LOOKUP, folder).returncode != 0, "the foreign folder has to bite, or this test proves nothing"
    spared = python(f"from wadi2d.engine.cli import own_environment; own_environment(); {LOOKUP}", folder)
    assert spared.returncode == 0, spared.stderr
    assert spared.stdout.strip() == "32640"


def test_main_cleans_before_it_does_anything(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setenv("GDAL_DATA", "elsewhere")
    assert main(["schema"]) == 0
    assert "GDAL_DATA" not in os.environ
    assert capsys.readouterr().out


def test_cupys_warning_about_a_toolkit_we_do_not_need_stays_quiet(tmp_path: Path) -> None:
    code = (
        "import warnings; from wadi2d.engine.cli import own_environment; own_environment(); "
        "warnings.warn('CUDA path could not be detected. Set CUDA_PATH environment variable if CuPy fails to load.')"
    )
    assert python(code, tmp_path).stderr == ""
