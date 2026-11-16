# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Hydrology section's point inflows table (W103), on the dock's canvas: Click on the map adds a row at the point
clicked, in the DEM's coordinates, as the job holds them. Held by the dock."""

from __future__ import annotations

from qgis.core import QgsCoordinateTransform, QgsPointXY, QgsProject
from qgis.gui import QgsMapToolEmitPoint


class InflowPointLinks:
    def __init__(self, dock) -> None:
        self.dock = dock
        self.box = dock.hydrology.inflows
        self.canvas = dock.iface.mapCanvas()
        self.tool = QgsMapToolEmitPoint(self.canvas)
        self.old_tool = None
        self.tool.canvasClicked.connect(self._clicked)
        self.box.place_requested.connect(self.start)
        self.box.place_stopped.connect(self.stop)

    def start(self) -> None:
        self.old_tool = self.canvas.mapTool()
        self.canvas.setMapTool(self.tool)

    def stop(self) -> None:
        if self.canvas.mapTool() is self.tool:
            self.canvas.unsetMapTool(self.tool)
            if self.old_tool is not None:
                self.canvas.setMapTool(self.old_tool)

    def _clicked(self, point, _button=None) -> None:
        self.stop()
        dem = self.dock.terrain.dem_layer()
        shown = self.canvas.mapSettings().destinationCrs()
        target = dem.crs() if dem is not None else shown
        at = QgsCoordinateTransform(shown, target, QgsProject.instance()).transform(QgsPointXY(point))
        self.box.add_point(at.x(), at.y())
