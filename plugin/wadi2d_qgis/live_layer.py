# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The run on the map: the live depth layer, the result group, the marker on a failed cell."""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDataProvider,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
)
from qgis.gui import QgsVertexMarker
from qgis.PyQt.QtGui import QColor

from .progress import live_source
from .protocol import MAPS_DIR
from .result_layers import GROUP_CELLS, hide_band_name
from .style import MAP_ORDER, STYLES, style_depth, style_mesh

LIVE_NAME = "Wadi2D live depth"
MESH_NAME = "Wadi2D mesh, cell size in m"
MARKER_SIZE = 18
MARKER_PEN = 3


def show_mesh(path: Path | str, sizes: list[float], old_id: str | None) -> str | None:
    """The preview on the map, one colour per cell size, in place of the last one. Returns the layer's id."""
    project = QgsProject.instance()
    if old_id and project.mapLayer(old_id) is not None:
        project.removeMapLayer(old_id)
    layer = QgsRasterLayer(str(path), MESH_NAME)
    if not layer.isValid():
        return None
    style_mesh(layer, sizes)
    project.addMapLayer(layer)
    return layer.id()


class LiveLayer:
    """One layer on the live raster: added once, reloaded when the file changes.

    The engine rewrites ``live/depth.tif`` in place, so a reload of the data provider is enough. If the
    engine had to fall back to numbered files, the layer's source moves to the current one.
    """

    def __init__(self) -> None:
        self._layer_id: str | None = None
        self._path: Path | None = None
        self._stamp = None

    def update(self, out_dir: Path | str) -> None:
        found = live_source(out_dir)
        if found is None:
            return
        path, stamp = found
        if stamp == self._stamp:
            return
        if self._layer_id is None:
            self._add(path)
            self._stamp = stamp
            return
        layer = QgsProject.instance().mapLayer(self._layer_id)
        if layer is None:  # the user removed it; do not bring it back
            return
        if path != self._path:
            layer.setDataSource(str(path), LIVE_NAME, "gdal", QgsDataProvider.ProviderOptions())
            style_depth(layer)
            self._path = path
        else:
            layer.dataProvider().reloadData()
        layer.triggerRepaint()
        self._stamp = stamp

    def _add(self, path: Path) -> None:
        layer = QgsRasterLayer(str(path), LIVE_NAME)
        if not layer.isValid():  # caught in mid-write: the next poll tries again
            return
        style_depth(layer)
        QgsProject.instance().addMapLayer(layer)
        self._layer_id = layer.id()
        self._path = path

    def layer(self):
        return QgsProject.instance().mapLayer(self._layer_id) if self._layer_id else None

    def clear(self) -> None:
        """Takes the layer off the map, which also lets go of the file."""
        if self.layer() is not None:
            QgsProject.instance().removeMapLayer(self._layer_id)
        self._layer_id, self._path, self._stamp = None, None, None


def load_maps(out_dir: Path | str, name: str, tucked: bool = False) -> list:
    """``maps/*.tif`` into a group named after the run; loading a run again replaces its group.

    ``tucked`` puts them in a closed subgroup, switched off, under what the run made after them.
    """
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    old = root.findGroup(name)
    if old is not None:
        project.removeMapLayers(old.findLayerIds())
        root.removeChildNode(old)
    paths = sorted((Path(out_dir) / MAPS_DIR).glob("*.tif"), key=_map_rank)
    layers = [layer for layer in (QgsRasterLayer(str(path), path.stem) for path in paths) if layer.isValid()]
    if not layers:
        return []
    group = root.insertGroup(0, name)
    if tucked:
        group = group.addGroup(GROUP_CELLS)
        group.setExpanded(False)
    for index, layer in enumerate(layers):
        style = STYLES.get(layer.name())
        if style:
            style(layer)
        project.addMapLayer(layer, False)
        node = group.addLayer(layer)
        node.setItemVisibilityChecked(index == 0 and not tucked)
        hide_band_name(node)
    return layers


def _map_rank(path: Path) -> tuple[int, str]:
    rank = MAP_ORDER.index(path.stem) if path.stem in MAP_ORDER else len(MAP_ORDER)
    return rank, path.stem


def mark_cell(canvas, xy: tuple[float, float], crs_text: str):
    """A red cross on the failed cell, with the map centred on it. ``crs_text`` is the DEM's CRS."""
    point = QgsPointXY(*xy)
    crs = QgsCoordinateReferenceSystem(crs_text)
    if crs.isValid():
        target = canvas.mapSettings().destinationCrs()
        point = QgsCoordinateTransform(crs, target, QgsProject.instance()).transform(point)
    marker = QgsVertexMarker(canvas)
    marker.setCenter(point)
    marker.setIconType(QgsVertexMarker.ICON_X)
    marker.setColor(QColor("red"))
    marker.setIconSize(MARKER_SIZE)
    marker.setPenWidth(MARKER_PEN)
    canvas.setCenter(point)
    canvas.refresh()
    return marker


def remove_marker(canvas, marker) -> None:
    if marker is not None:
        canvas.scene().removeItem(marker)
