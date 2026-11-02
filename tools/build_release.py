# Wadi2D release builder. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Builds dist/Wadi2D-<version>-windows.zip from the last commit. Run it from the project venv.

python tools/build_release.py

The zip holds the engine wheel, a plugin zip that QGIS can also install by itself, the package versions the tests ran on
and the double-click installer. Only committed files go in, so nothing local or half-done can reach a user.
"""

from __future__ import annotations

import configparser
import contextlib
import io
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPO = Path(__file__).resolve().parent.parent
PLUGIN = "wadi2d_qgis"
PACKAGE = "wadi2d"
TEMPLATES = Path("tools") / "release"
INSTALLER_FILES = ("install_wadi2d.bat", "install_wadi2d.ps1", "README.txt")
CONSTRAINTS = "constraints.txt"
EXTRAS = ("gpu", "mesh", "vector")  # what the installer asks for
PINNED = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==\S+$")
LEFT_OUT = ("__pycache__", ".pyc", "engine.txt")


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True).stdout


def export_commit(destination: Path) -> str:
    """The last commit as plain files; its short hash."""
    with tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", "HEAD"))) as archive:
        archive.extractall(destination, filter="data")
    return git("rev-parse", "--short", "HEAD").decode().strip()


def read_version(tree: Path) -> str:
    """The one version, in the engine's package; the plugin's metadata has to say the same."""
    text = (tree / PACKAGE / "__init__.py").read_text(encoding="utf-8")
    version = re.search(r'^__version__ = "([^"]+)"', text, re.MULTILINE).group(1)
    metadata = configparser.ConfigParser()
    metadata.read(tree / "plugin" / PLUGIN / "metadata.txt", encoding="utf-8")
    if metadata["general"]["version"] != version:
        raise SystemExit(f"plugin metadata says {metadata['general']['version']}, the engine says {version}")
    return version


def build_wheel(tree: Path, folder: Path) -> Path:
    command = [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-cache-dir", "--wheel-dir", str(folder), str(tree)]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    return next(folder.glob("*.whl"))


def missing_from_wheel(wheel: Path, tree: Path) -> list[str]:
    """Every committed file of the engine package that the wheel left out, kernels above all."""
    with zipfile.ZipFile(wheel) as archive:
        inside = set(archive.namelist())
    wanted = (p.relative_to(tree).as_posix() for p in (tree / PACKAGE).rglob("*") if p.is_file() and p.suffix != ".md")
    return sorted(name for name in wanted if name not in inside)


def plugin_zip(tree: Path, destination: Path) -> Path:
    """What QGIS's Install from ZIP wants: one top folder named as the plugin, with its licence."""
    source = tree / "plugin" / PLUGIN
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file() and not any(mark in path.as_posix() for mark in LEFT_OUT):
                archive.write(path, f"{PLUGIN}/{path.relative_to(source).as_posix()}")
        archive.write(tree / "LICENSE", f"{PLUGIN}/LICENSE")
    return destination


def runtime_packages(tree: Path) -> set[str]:
    """Every package a release can load: the engine's dependencies and extras, followed down through what is installed."""
    project = tomllib.loads((tree / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    wanted = list(project["dependencies"])
    for extra in EXTRAS:
        wanted += project["optional-dependencies"][extra]
    found: set[str] = set()
    while wanted:
        requirement = Requirement(wanted.pop())
        name = canonicalize_name(requirement.name)
        if name in found or (requirement.marker and not requirement.marker.evaluate({"extra": ""})):
            continue
        found.add(name)
        with contextlib.suppress(metadata.PackageNotFoundError):
            wanted += metadata.requires(name) or []
    return found


def pinned_versions(freeze: str, packages: set[str]) -> str:
    """The name==version lines of a pip freeze for these packages: what a new install is held to."""
    lines = (s.strip() for s in freeze.splitlines())
    matches = ((s, PINNED.match(s)) for s in lines)
    return "\n".join(s for s, m in matches if m and canonicalize_name(m.group(1)) in packages) + "\n"


def windows_text(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="wadi2d_release_") as temporary:
        work = Path(temporary)
        tree = work / "tree"
        tree.mkdir()
        commit = export_commit(tree)
        version = read_version(tree)
        wheel = build_wheel(tree, work / "wheel")
        missing = missing_from_wheel(wheel, tree)
        if missing:
            raise SystemExit(f"the wheel left out {missing}")
        plugin = plugin_zip(tree, work / f"{PLUGIN}-{version}.zip")
        freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], check=True, capture_output=True, text=True).stdout

        name = f"Wadi2D-{version}-windows"
        target = REPO / "dist" / f"{name}.zip"
        target.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in (wheel, plugin):
                archive.write(path, f"{name}/{path.name}")
            for file in INSTALLER_FILES:
                archive.writestr(f"{name}/{file}", windows_text(tree / TEMPLATES / file))
            archive.writestr(f"{name}/{CONSTRAINTS}", pinned_versions(freeze, runtime_packages(tree)))
            archive.write(tree / "LICENSE", f"{name}/LICENSE.txt")
            archive.write(tree / "LICENSES.md", f"{name}/LICENSES.md")
            archive.writestr(f"{name}/BUILD.txt", f"Wadi2D {version}, commit {commit}\n")
    print(f"{target} from {commit}, {target.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
