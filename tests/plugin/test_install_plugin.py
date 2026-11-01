# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The installer, against a temporary folder: the real QGIS profile is never touched by a test."""

from __future__ import annotations

import configparser
import os
from pathlib import Path

import install_plugin
import pytest

PLUGIN_ROOT = install_plugin.SOURCE


def test_copy_is_complete_and_repeatable(tmp_path: Path) -> None:
    for _ in range(2):
        assert install_plugin.main(["--plugins-dir", str(tmp_path)]) == 0
    installed = tmp_path / "wadi2d_qgis"
    assert (installed / "metadata.txt").is_file()
    assert (installed / "sections" / "terrain.py").is_file()
    assert not list(installed.rglob("__pycache__"))


def test_a_copy_replaces_stale_files(tmp_path: Path) -> None:
    install_plugin.install(tmp_path)
    stale = tmp_path / "wadi2d_qgis" / "gone.py"
    stale.write_text("x", "utf-8")
    install_plugin.install(tmp_path)
    assert not stale.exists()


@pytest.mark.skipif(os.name != "nt", reason="directory junctions are a Windows feature")
def test_link_makes_a_junction_and_removing_it_spares_the_repo(tmp_path: Path) -> None:
    linked = install_plugin.install(tmp_path, link=True)
    assert os.path.isjunction(linked)
    assert (linked / "metadata.txt").read_bytes() == (PLUGIN_ROOT / "metadata.txt").read_bytes()
    install_plugin.install(tmp_path, link=True)
    assert os.path.isjunction(linked)
    install_plugin.install(tmp_path)
    assert not os.path.isjunction(linked)
    assert (PLUGIN_ROOT / "metadata.txt").is_file()


def test_metadata_says_what_qgis_needs() -> None:
    metadata = configparser.ConfigParser()
    metadata.read(PLUGIN_ROOT / "metadata.txt", encoding="utf-8")
    general = metadata["general"]
    assert general["qgisMinimumVersion"] == "3.34"
    assert general["license"] == "GPL-3.0-or-later"
    for key in ("name", "description", "about", "version", "author", "repository"):
        assert general[key]


def test_every_source_file_carries_the_licence_header() -> None:
    for path in PLUGIN_ROOT.rglob("*.py"):
        assert "SPDX-License-Identifier: GPL-3.0-or-later" in path.read_text("utf-8")[:200], path


def test_the_plugin_never_imports_the_engine() -> None:
    for path in PLUGIN_ROOT.rglob("*.py"):
        for line in path.read_text("utf-8").splitlines():
            stripped = line.strip()
            assert not stripped.startswith(("import wadi2d", "from wadi2d")), f"{path}: {line}"
            assert "PyQt5" not in stripped, f"{path}: use qgis.PyQt"
