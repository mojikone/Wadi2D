# Wadi2D QGIS plugin installer. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Puts the plugin into the default QGIS profile. Asks nothing; run it as often as you like.

python tools/install_plugin.py           copies the plugin
python tools/install_plugin.py --link    makes a directory junction, so edits in the repo are live
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN = "wadi2d_qgis"
SOURCE = Path(__file__).resolve().parent.parent / "plugin" / PLUGIN


def plugins_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "QGIS" / "QGIS3" / "profiles" / "default" / "python" / "plugins"


def remove(path: Path) -> None:
    """Whatever is there. A junction goes alone: its target, the repo, is never touched."""
    if os.path.isjunction(path):
        os.rmdir(path)
    elif path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def install(target_dir: Path, link: bool = False) -> Path:
    destination = target_dir / PLUGIN
    target_dir.mkdir(parents=True, exist_ok=True)
    remove(destination)
    if link:
        command = ["cmd", "/c", "mklink", "/J", str(destination), str(SOURCE)]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    else:
        shutil.copytree(SOURCE, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--link", action="store_true", help="directory junction instead of a copy")
    parser.add_argument("--plugins-dir", type=Path, help="install here instead of the default profile")
    options = parser.parse_args(argv)
    destination = install(options.plugins_dir or plugins_dir(), options.link)
    print(f"{'Linked' if options.link else 'Copied'} to {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
