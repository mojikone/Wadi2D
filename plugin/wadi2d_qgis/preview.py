# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Preview terrain: what the objects do to the ground, on the map, in seconds, with no run.

The engine does the work through ``wadi2d terrain``; this side writes the job, loads the two rasters and says what
the engine found.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from qgis.core import QgsCoordinateTransform, QgsProject, QgsRasterLayer
from qgis.PyQt.QtCore import QObject, pyqtSignal

from . import settings
from .engine_process import EngineQuery
from .job_builder import LayerError, preview_job, preview_problems, write_job
from .layer_groups import SLOT_TERRAIN, TERRAIN, add_layer, clear_slot, input_group, model_name
from .protocol import engine_error_text, exit_message, terrain_args
from .shaped import volumes_text
from .style import style_change

CHANGE_LAYER = "terrain change"
MODIFIED_LAYER = "terrain modified"
PREVIEW_PREFIX = "wadi2d_preview_"


def load_terrain(files: dict, model: str) -> list:
    """The two rasters of a preview into the model's Inputs > Terrain, replacing the last preview there."""
    clear_slot(model, SLOT_TERRAIN)
    change = QgsRasterLayer(files["change"], CHANGE_LAYER)
    modified = QgsRasterLayer(files["modified"], MODIFIED_LAYER)
    layers = [layer for layer in (change, modified) if layer.isValid()]
    if not layers:
        return []
    group = input_group(model, TERRAIN)
    for index, layer in enumerate(layers):
        if layer.name() == CHANGE_LAYER:
            style_change(layer)
        add_layer(group, layer, SLOT_TERRAIN, shown=index == 0, index=index)
    return layers


def zoom_to(canvas, layer) -> None:
    """The map on the domain: a preview is there to be looked at."""
    source = layer.crs()
    target = canvas.mapSettings().destinationCrs()
    box = QgsCoordinateTransform(source, target, QgsProject.instance()).transformBoundingBox(layer.extent())
    canvas.setExtent(box)
    canvas.refresh()


class TerrainPreview(QObject):
    """One preview at a time. ``finished`` carries the text for the user and whether it worked."""

    finished = pyqtSignal(str, bool)

    def __init__(self, canvas, parent=None) -> None:
        super().__init__(parent)
        self.canvas = canvas
        self.data: list[dict] = []
        self.report: dict = {}
        self._query: EngineQuery | None = None
        self._model = model_name(None)

    @property
    def running(self) -> bool:
        return self._query is not None

    def start(self, values: dict) -> None:
        """Write the job and start the engine; a problem comes back through ``finished`` too."""
        found = preview_problems(values)
        if found:
            self.finished.emit(" ".join(found), False)
            return
        self._model = model_name(values.get("output"))
        parent = Path(values["output"]).parent if values.get("output") else None
        if parent is not None and not parent.is_dir():
            parent = None
        out = Path(tempfile.mkdtemp(prefix=PREVIEW_PREFIX, dir=parent))
        try:
            job = write_job(preview_job(values, out), out)
        except (OSError, LayerError, ValueError) as problem:
            self.finished.emit(f"The preview could not be written: {problem}", False)
            return
        self._query = EngineQuery(settings.engine_text(), self)
        self._query.done.connect(self._done)
        self._query.start(terrain_args(job, out))

    def _done(self, code: int, out: str, err: str) -> None:
        self._query = None
        try:
            report = json.loads(out) if code == 0 else None
        except ValueError:
            report = None
        if report is None:
            self.finished.emit(f"{exit_message(code)} {engine_error_text(err)}".strip(), False)
            return
        self.report = report
        self.data = json.loads(Path(report["files"]["preview"]).read_text(encoding="utf-8"))
        layers = load_terrain(report["files"], self._model)
        if not layers:
            self.finished.emit("The engine finished, but its rasters could not be loaded.", False)
            return
        zoom_to(self.canvas, layers[0])
        words = [volumes_text(report["volumes"]) or "These objects change no ground inside the domain."]
        words.extend(report["notes"])
        self.finished.emit(" ".join(words), True)
