# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Engine commands, exit codes, the clean environment, without QGIS."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from wadi2d_qgis.protocol import (
    ENGINE_FILE,
    ENGINE_MODULE,
    EXIT_MESSAGES,
    FALLBACK_ENGINE,
    SHARED_ENGINE_FOLDER,
    cell_grid_scale,
    cell_grid_title,
    clean_env,
    default_engine,
    engine_error_text,
    estimate_text,
    exit_message,
    mesh_text,
    next_run_dir,
    parse_engine,
    parse_estimate,
    pid_alive,
    run_args,
)


@pytest.mark.parametrize("code", [0, 1, 2, 3, 4, 5, 6, 7])
def test_every_exit_code_of_the_protocol_has_a_sentence(code: int) -> None:
    assert code in EXIT_MESSAGES
    assert exit_message(code).endswith(".")


def test_unknown_and_missing_exit_codes_still_read_plainly() -> None:
    assert "unknown code (42)" in exit_message(42)
    assert "without reporting" in exit_message(None)


def test_the_default_engine_splits_into_python_and_module() -> None:
    assert parse_engine(r'"C:\Program Files\x\python.exe" -m wadi2d.engine.cli')[1:] == list(ENGINE_MODULE)
    assert parse_engine(FALLBACK_ENGINE)[1:] == list(ENGINE_MODULE)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (r"C:\venv\Scripts\wadi2d.exe", [r"C:\venv\Scripts\wadi2d.exe"]),
        (r"C:\venv\Scripts\python.exe", [r"C:\venv\Scripts\python.exe", *ENGINE_MODULE]),
        (r"C:\Program Files\w\wadi2d.exe", [r"C:\Program Files\w\wadi2d.exe"]),
        (r"C:\Program Files\w\python.exe -m wadi2d", [r"C:\Program Files\w\python.exe", "-m", "wadi2d"]),
        (
            r'"C:\Program Files\w\python.exe" "D:\a b\fake.py"',
            [r"C:\Program Files\w\python.exe", r"D:\a b\fake.py"],
        ),
        ("  wadi2d  ", ["wadi2d"]),
    ],
)
def test_parse_engine(text: str, expected: list[str]) -> None:
    assert parse_engine(text) == expected


def test_an_empty_engine_path_is_refused() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_engine("   ")


def test_run_arguments() -> None:
    assert run_args("j.json", "out") == ["run", "j.json", "--out", "out"]
    assert run_args("j.json", "out", dry_run=True)[-1] == "--dry-run"
    assert run_args("j.json", "out", resume=True)[-1] == "--resume"


def test_clean_env_removes_what_qgis_added_and_keeps_the_rest() -> None:
    root = r"C:\PROGRA~1\QGIS34~1.8"
    env = {
        "OSGEO4W_ROOT": root,
        "PYTHONHOME": rf"{root}\apps\Python312",
        "PYTHONPATH": rf"{root}\apps\qgis-ltr\python;",
        "GDAL_DATA": rf"{root}\apps\gdal\share\gdal",
        "GDAL_DRIVER_PATH": rf"{root}\apps\gdal\lib\gdalplugins",
        "PROJ_DATA": rf"{root}\share\proj",
        "QGIS_PREFIX_PATH": f"{root}/apps/qgis-ltr".replace("\\", "/"),
        "QT_PLUGIN_PATH": rf"{root}\apps\qt5\plugins",
        "VSI_CACHE": "TRUE",
        "Path": rf"{root}\apps\qgis-ltr\bin;{root}\bin;C:\Windows\system32;D:\tools",
        "SystemRoot": r"C:\Windows",
        "CUDA_VISIBLE_DEVICES": "0",
    }
    clean = clean_env(env)
    assert clean == {
        "Path": r"C:\Windows\system32;D:\tools",
        "SystemRoot": r"C:\Windows",
        "CUDA_VISIBLE_DEVICES": "0",
    }


def test_clean_env_leaves_a_plain_environment_alone() -> None:
    env = {"PATH": r"C:\Windows;D:\x", "TEMP": r"C:\t"}
    assert clean_env(env) == env


def test_pid_alive() -> None:
    assert pid_alive(os.getpid())
    assert not pid_alive(None)
    assert not pid_alive(0)
    assert not pid_alive(2**22 - 3)


def test_a_used_folder_gets_a_numbered_sibling_and_the_old_one_stays(tmp_path: Path) -> None:
    base = tmp_path / "run"
    assert next_run_dir(base) == base
    base.mkdir()
    assert next_run_dir(base) == base
    (base / "progress.jsonl").write_text("x", "utf-8")
    assert next_run_dir(base) == tmp_path / "run_2"
    (tmp_path / "run_2").mkdir()
    (tmp_path / "run_2" / "progress.jsonl").write_text("x", "utf-8")
    assert next_run_dir(base) == tmp_path / "run_3"


def test_estimate_reads_what_the_dry_run_prints() -> None:
    assert parse_estimate('{\n "cells": 7\n}\n') == {"cells": 7}
    assert parse_estimate("no json here") is None
    assert parse_estimate("[1]") is None


@pytest.mark.parametrize(
    ("seconds", "words"), [(40.0, "about 40 s"), (240.0, "about 4 min"), (7200.0, "about 2.0 h")]
)
def test_estimate_text(seconds: float, words: str) -> None:
    estimate = {"cells": 1497120, "device_gb": 0.687, "wall_s": seconds}
    assert estimate_text(estimate) == f"1,497,120 cells, 0.69 GB, {words}"


def test_the_estimate_carries_the_engine_s_note_on_a_mesh() -> None:
    estimate = {"cells": 1200, "device_gb": 0.2, "wall_s": 40.0, "note": "The time is rough."}
    assert estimate_text(estimate) == "1,200 cells, 0.20 GB, about 40 s. The time is rough."


MESH_SUMMARY = {"cells": 1200, "ratio": 2.5, "tiles_by_size": {"10 m": 3, "20 m": 0, "40 m": 2}}


def test_the_preview_with_no_lines_reads_as_it_did() -> None:
    assert mesh_text(MESH_SUMMARY) == "1,200 cells, 2.5 x fewer than the uniform grid. Tiles: 3 of 10 m, 2 of 40 m."


def test_the_preview_gives_each_line_the_engine_s_own_numbers() -> None:
    line = {"name": "Wadi", "near": 10.0, "rows": 6, "far": 40.0, "reach": 420.0}
    assert mesh_text({**MESH_SUMMARY, "lines": [line]}).endswith(
        "2 of 40 m. Wadi: 10 m for 6 rows each side, no coarser than 40 m within 420 m."
    )


def test_the_engines_own_sentence_is_taken_from_its_json_error_line() -> None:
    stderr = 'some warning\n{"ev": "error", "code": 3, "message": "terrain.dem not found: x.tif"}\n'
    assert engine_error_text(stderr) == "terrain.dem not found: x.tif"


def test_a_python_traceback_comes_through_as_its_tail() -> None:
    stderr = "Traceback (most recent call last):\n  File x\nValueError: no\n"
    assert engine_error_text(stderr).endswith("ValueError: no")
    assert engine_error_text("  ") == ""


def test_the_default_engine_comes_from_the_installer_not_from_this_machine(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert default_engine(tmp_path) == FALLBACK_ENGINE
    (tmp_path / ENGINE_FILE).write_text('"C:/x y/python.exe" -m wadi2d.engine.cli\n', encoding="utf-8")
    assert default_engine(tmp_path) == '"C:/x y/python.exe" -m wadi2d.engine.cli'
    assert "Mojtaba" not in FALLBACK_ENGINE


def test_a_plugin_installed_from_zip_finds_the_engine_the_installer_recorded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    assert default_engine(plugin) == FALLBACK_ENGINE
    shared = tmp_path / SHARED_ENGINE_FOLDER
    shared.mkdir()
    (shared / ENGINE_FILE).write_text('"C:/shared/python.exe" -m wadi2d.engine.cli\n', encoding="utf-8")
    assert default_engine(plugin) == '"C:/shared/python.exe" -m wadi2d.engine.cli'
    (plugin / ENGINE_FILE).write_text('"C:/beside/python.exe" -m wadi2d.engine.cli\n', encoding="utf-8")
    assert default_engine(plugin) == '"C:/beside/python.exe" -m wadi2d.engine.cli'


def test_the_cell_grid_says_its_sizes_and_the_scale_it_draws_from() -> None:
    assert cell_grid_scale(20.0) == 20000
    assert cell_grid_title(20.0, 20.0) == "Cell grid, 20 m, drawn from 1:20,000 in"
    assert cell_grid_title(10.0, 40.0) == "Cell grid, 10 to 40 m, drawn from 1:10,000 in"


def test_estimate_says_the_disk_of_the_saved_maps() -> None:
    estimate = {"cells": 100, "device_gb": 0.5, "wall_s": 60.0, "maps": 193, "maps_gb": 3.84}
    assert estimate_text(estimate).endswith("193 saved maps, at most 3.8 GB of disk")
