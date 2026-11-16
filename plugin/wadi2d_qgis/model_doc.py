# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The saved model: one versioned document of everything the dock holds. No Qt here.

Interface: :func:`new_doc` (a document from the sections' states), :func:`dumps` / :func:`loads` (text and back, with
the refusals in words), :func:`fingerprint` (what two documents must share to be the same model), the files a
document lives in (:data:`MODEL_FILE` in a run folder, :func:`scenario_path` in the model's folder) and
:func:`write_doc` / :func:`read_doc`.

The same document is kept in three places (W99): with the QGIS project, so a model survives closing QGIS; in every run
folder, so a finished run can be opened back into the dock; and as named scenarios in the model's folder.
A later format adds a function to :data:`MIGRATIONS`; nothing else changes for an old file.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

FORMAT = "wadi2d-model"
VERSION = 1
MODEL_FILE = "model.wadi2d.json"
"""The model document of a run, written into its folder beside ``job.json`` when Run is pressed."""
SCENARIO_DIR = "scenarios"
"""Inside the model's folder (the Run section's output folder), as the generated basin's folder is."""
SCENARIO_SUFFIX = ".wadi2d.json"
MATTERS = ("model_type", "show_all", "sections")
"""What makes two documents the same model: not the stamp, not the plugin that wrote it, not the page shown."""
MIGRATIONS: dict = {}
"""``{from_version: function(doc) -> doc}``; each takes a document one version up."""
RASTER_PROVIDER = "gdal"
"""The provider of a raster layer in a saved layer choice; any other is read as a vector file."""
UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def new_doc(sections: dict, plugin: str = "", **parts) -> dict:
    """A document of the sections' states; ``parts`` are the dock's own (the model type, the show-all switch)."""
    return {
        "format": FORMAT,
        "version": VERSION,
        "plugin": plugin,
        "saved": datetime.now().isoformat(timespec="seconds"),
        **parts,
        "sections": sections,
    }


def fingerprint(doc: dict) -> str:
    """The text two documents share exactly when they are the same model."""
    return json.dumps({key: doc.get(key) for key in MATTERS}, sort_keys=True)


def dumps(doc: dict) -> str:
    return json.dumps(doc, indent=1)


def loads(text: str) -> dict:
    """The document in ``text``, brought up to this format. ``ValueError`` says in words why it cannot be read."""
    try:
        doc = json.loads(text)
    except ValueError as problem:
        raise ValueError(f"This is not a Wadi2D model file: {problem}") from None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT or not isinstance(doc.get("sections"), dict):
        raise ValueError("This is not a Wadi2D model file.")
    version = doc.get("version")
    if not isinstance(version, int) or version < 1:
        raise ValueError("This Wadi2D model file gives no format version.")
    if version > VERSION:
        raise ValueError(
            f"This model was saved by a newer Wadi2D (model format {version}); this plugin reads format {VERSION}. "
            "Update the plugin to open it."
        )
    while version < VERSION:
        doc = MIGRATIONS[version](doc)
        version += 1
        doc["version"] = version
    return doc


def write_doc(path: Path | str, doc: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(doc), encoding="utf-8")
    return path


def read_doc(path: Path | str) -> dict:
    return loads(Path(path).read_text(encoding="utf-8"))


# Scenarios: named copies of the document in the model's folder.


def safe_name(name: str) -> str:
    """A scenario's name as a file name: what Windows refuses is replaced, the ends trimmed."""
    return UNSAFE.sub("_", name).strip(" .")


def scenario_path(model_folder: Path | str, name: str) -> Path:
    return Path(model_folder) / SCENARIO_DIR / f"{safe_name(name)}{SCENARIO_SUFFIX}"


def list_scenarios(model_folder: Path | str) -> list[tuple[str, Path]]:
    """``(name, file)`` of each scenario of the model, by name."""
    folder = Path(model_folder) / SCENARIO_DIR
    if not model_folder or not folder.is_dir():
        return []
    return sorted((path.name[: -len(SCENARIO_SUFFIX)], path) for path in folder.glob(f"*{SCENARIO_SUFFIX}"))
