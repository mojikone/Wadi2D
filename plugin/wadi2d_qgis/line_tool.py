# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Drawing a temporary line on the map, and the scratch layer that keeps it."""

from __future__ import annotations

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsLineSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProject,
    QgsSingleSymbolRenderer,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor

LAYER_TITLE = "Temporary result lines"
NAME_FIELD = "name"
COLOUR = "#c8560a"
LINE_WIDTH_MM = "0.9"
BAND_WIDTH = 2
LABEL_SIZE = 9.0


class DrawLine(QgsMapTool):
    """Left click adds a point, right click ends the line, Escape drops it."""

    drawn = pyqtSignal(list)
    dropped = pyqtSignal()

    def __init__(self, canvas) -> None:
        super().__init__(canvas)
        self.points: list[QgsPointXY] = []
        self.band = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.band.setColor(QColor(COLOUR))
        self.band.setWidth(BAND_WIDTH)
        self.setCursor(Qt.CrossCursor)

    def canvasMoveEvent(self, event) -> None:
        if self.points:
            self.band.setToGeometry(QgsGeometry.fromPolylineXY([*self.points, event.mapPoint()]), None)

    def canvasReleaseEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            self._end()
            return
        self.points.append(event.mapPoint())
        self.band.setToGeometry(QgsGeometry.fromPolylineXY(self.points), None)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._clear()
            self.dropped.emit()

    def _end(self) -> None:
        points = self.points
        self._clear()
        if len(points) < 2:
            self.dropped.emit()
            return
        self.drawn.emit(points)

    def _clear(self) -> None:
        self.points = []
        self.band.reset(QgsWkbTypes.LineGeometry)

    def deactivate(self) -> None:
        self._clear()
        super().deactivate()


def _style(layer: QgsVectorLayer) -> None:
    symbol = QgsLineSymbol.createSimple({"color": COLOUR, "width": LINE_WIDTH_MM, "line_style": "dash"})
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    text = QgsTextFormat()
    text.setSize(LABEL_SIZE)
    text.setColor(QColor(COLOUR))
    labels = QgsPalLayerSettings()
    labels.fieldName = NAME_FIELD
    labels.placement = Qgis.LabelPlacement.Line
    labels.setFormat(text)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(labels))
    layer.setLabelsEnabled(True)


def scratch_layer(crs, group_name: str) -> QgsVectorLayer:
    """An empty scratch layer on top of the run's group; it is gone with the project unless saved."""
    layer = QgsVectorLayer(f"LineString?field={NAME_FIELD}:string", LAYER_TITLE, "memory")
    layer.setCrs(crs)
    _style(layer)
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    top = root.findGroup(group_name) or root
    project.addMapLayer(layer, False)
    top.insertLayer(0, layer)
    return layer


def add_line(layer: QgsVectorLayer, name: str, points: list[QgsPointXY]) -> int:
    """The line on the layer; its feature id, for taking it off again."""
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPolylineXY(points))
    feature.setAttribute(NAME_FIELD, name)
    done, added = layer.dataProvider().addFeatures([feature])
    layer.updateExtents()
    layer.triggerRepaint()
    return added[0].id() if done and added else -1


def remove_line(layer: QgsVectorLayer, feature_id: int) -> None:
    layer.dataProvider().deleteFeatures([feature_id])
    layer.triggerRepaint()
