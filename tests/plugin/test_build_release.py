# Wadi2D release tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The release builder on a small tree, and the rules its templates live by. No network, no git."""

from __future__ import annotations

import zipfile
from pathlib import Path

import build_release
import pytest

REPO = build_release.REPO


def small_tree(root: Path, version: str = "1.2.3", metadata: str = "1.2.3") -> Path:
    plugin = root / "plugin" / build_release.PLUGIN
    (plugin / "sections").mkdir(parents=True)
    (plugin / "__pycache__").mkdir()
    (plugin / "metadata.txt").write_text(f"[general]\nversion={metadata}\n", "utf-8")
    (plugin / "sections" / "terrain.py").write_text("x = 1\n", "utf-8")
    (plugin / "engine.txt").write_text("a path on this machine\n", "utf-8")
    (plugin / "__pycache__" / "x.pyc").write_bytes(b"x")
    (root / build_release.PACKAGE).mkdir()
    (root / build_release.PACKAGE / "__init__.py").write_text(f'__version__ = "{version}"\n', "utf-8")
    (root / "LICENSE").write_text("GPL\n", "utf-8")
    return root


def test_the_version_is_the_engines_and_the_plugin_must_agree(tmp_path: Path) -> None:
    assert build_release.read_version(small_tree(tmp_path)) == "1.2.3"
    (tmp_path / "plugin" / build_release.PLUGIN / "metadata.txt").write_text("[general]\nversion=9\n", "utf-8")
    with pytest.raises(SystemExit):
        build_release.read_version(tmp_path)


def test_this_repository_agrees_with_itself() -> None:
    assert build_release.read_version(REPO)


def test_the_plugin_zip_has_one_top_folder_a_licence_and_nothing_local(tmp_path: Path) -> None:
    made = build_release.plugin_zip(small_tree(tmp_path), tmp_path / "p.zip")
    with zipfile.ZipFile(made) as archive:
        names = archive.namelist()
    assert {name.split("/")[0] for name in names} == {build_release.PLUGIN}
    assert f"{build_release.PLUGIN}/LICENSE" in names
    assert f"{build_release.PLUGIN}/sections/terrain.py" in names
    assert not [name for name in names if "__pycache__" in name or name.endswith("engine.txt")]


def test_a_wheel_that_drops_a_kernel_is_caught(tmp_path: Path) -> None:
    tree = small_tree(tmp_path)
    (tree / build_release.PACKAGE / "cells.cu").write_text("kernel\n", "utf-8")
    wheel = tmp_path / "w.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"{build_release.PACKAGE}/__init__.py", "x")
    assert build_release.missing_from_wheel(wheel, tree) == [f"{build_release.PACKAGE}/cells.cu"]


def test_pins_keep_plain_versions_only() -> None:
    freeze = "numpy==2.4.6\n-e git+https://x/y#egg=z\nfoo @ file:///C:/a/b\nwadi2d==0.1.0\nWadi2D-x==1\n"
    assert build_release.pinned_versions(freeze) == "numpy==2.4.6\nWadi2D-x==1\n"


def test_windows_text_never_doubles_a_carriage_return(tmp_path: Path) -> None:
    path = tmp_path / "x.bat"
    path.write_bytes(b"a\nb\r\nc\n")
    assert build_release.windows_text(path) == b"a\r\nb\r\nc\r\n"


@pytest.mark.parametrize("name", build_release.INSTALLER_FILES)
def test_templates_are_plain_ascii(name: str) -> None:
    """Windows PowerShell 5.1 reads a file with no byte-order mark in the local code page."""
    assert (REPO / build_release.TEMPLATES / name).read_bytes().isascii()


def test_the_installer_writes_no_byte_order_mark_and_spares_a_junction() -> None:
    script = (REPO / build_release.TEMPLATES / "install_wadi2d.ps1").read_text("utf-8")
    assert "Set-Content" not in script and "Out-File" not in script
    assert "ReparsePoint" in script
