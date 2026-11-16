# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A window of a finished run mapped at the terrain's finest resolution (W101, his item 7): a rectangle drawn on the
map, ``wadi2d window`` on it, and its depth, speed and hazard rasters loaded into the run's group.

The maps of record are drawn at a coarser pixel by rule since W100; this is their detail where it is wanted, at the
DEM's own pixel, whatever that is on the project's ground. The engine makes the rasters; this side draws the
rectangle, asks, and loads.
"""

from __future__ import annotations

import json
from pathlib import Path

from qgis.core import QgsCoordinateTransform, QgsProject, QgsRasterLayer
from qgis.gui import QgsMapToolExtent
from qgis.PyQt.QtCore import QObject

from . import settings, style
from .engine_process import EngineQuery
from .layer_groups import add_layer, find_run_results, run_results, subgroup
from .protocol import engine_error_text, exit_message
from .window_rows import DRAW_WORDS, GROUP_WORDS, LAYERS, WINDOW_TIMEOUT_S, window_args, window_folder


class WindowLinks(QObject):
    """The window button of the Run section and its map tool."""

    def __init__(self, dock) -> None:
        super().__init__(dock)
        self.dock = dock
        self.canvas = dock.iface.mapCanvas()
        self.tool = QgsMapToolExtent(self.canvas)
        self.tool.extentChanged.connect(self.drawn)
        self._old_tool = None
        self._query: EngineQuery | None = None
        self.folder: Path | None = None
        self.layers: list = []
        dock.panel.window_button.clicked.connect(self.start)

    def start(self) -> None:
        if self.dock.results_dir is None:
            return
        self._old_tool = self.canvas.mapTool()
        self.canvas.setMapTool(self.tool)
        self.dock.panel.say(DRAW_WORDS, "note")

    def drawn(self, extent) -> None:
        """The rectangle, from the map's CRS to the run's, and the engine asked."""
        self.canvas.unsetMapTool(self.tool)
        if self._old_tool is not None:
            self.canvas.setMapTool(self._old_tool)
        run = self.dock.results_dir
        if run is None or extent.isEmpty():
            return
        dem = self.dock.terrain.dem_layer()
        crs = dem.crs() if dem is not None else QgsProject.instance().crs()
        box = QgsCoordinateTransform(self.canvas.mapSettings().destinationCrs(), crs, QgsProject.instance()).transformBoundingBox(extent)
        self.map_box(run, (box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum()))

    def map_box(self, run: Path, box: tuple[float, float, float, float]) -> None:
        """The window of ``box``, in the run's coordinates."""
        self.folder = window_folder(run, box)
        self.dock.panel.window_button.setEnabled(False)
        self.dock.panel.say("Mapping the window at the DEM's pixel...")
        self._query = EngineQuery(settings.engine_text(), self)
        self._query.done.connect(lambda code, _out, err: self._done(run, code, err))
        self._query.start(window_args(run, box, self.folder), WINDOW_TIMEOUT_S)

    def _done(self, run: Path, code: int, err: str) -> None:
        self.dock.panel.window_button.setEnabled(True)
        self._query = None
        if code != 0:
            self.dock.panel.say(f"The window was not made. {exit_message(code)} {engine_error_text(err)}".strip(), "bad")
            return
        self.layers = self.load(run, self.folder)
        names = ", ".join(layer.name() for layer in self.layers)
        self.dock.panel.say(f"The window is in the run's group: {names}." if self.layers else "The window holds no raster.", "good")

    def load(self, run: Path, folder: Path) -> list:
        top = find_run_results(run) or run_results(run)
        group = subgroup(top, GROUP_WORDS.format(name=folder.name), 0)
        found = []
        for name, title, kind in LAYERS:
            path = folder / name
            if not path.is_file():
                continue
            layer = QgsRasterLayer(str(path), title)
            if not layer.isValid():
                continue
            if kind == "depth":
                style.style_pixel_depth(layer)
            elif kind == "hazard":
                style.style_pixel_hazard(layer)
            add_layer(group, layer, shown=kind == "depth")
            found.append(layer)
        return found

    def pixel_of(self, folder: Path) -> float | None:
        """The pixel the window was drawn at, from its own rasters' record."""
        stats = folder / "pixels.json"
        if not stats.is_file():
            return None
        return json.loads(stats.read_text(encoding="utf-8")).get("pixel_m")
