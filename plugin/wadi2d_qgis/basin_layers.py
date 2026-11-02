# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The three layers of a generated basin, styled, in their own group; a new generation replaces the last."""

from __future__ import annotations

from pathlib import Path

from qgis.core import QgsProject, QgsVectorLayer

from . import style
from .protocol import BASIN_LAYERS

GROUP = "Wadi2D basin"
TITLES = {"subbasins": "Subbasins, generated", "reaches": "Reaches, generated", "junctions": "Junctions, generated"}
STYLES = {
    "subbasins": style.style_basin_subbasins,
    "reaches": style.style_basin_reaches,
    "junctions": style.style_basin_junctions,
}


def open_basin_layer(gpkg: Path | str, name: str):
    options = QgsVectorLayer.LayerOptions()
    options.forceReadOnly = True  # a writable GeoPackage goes to WAL mode, and its connections lock each other out
    layer = QgsVectorLayer(f"{gpkg}|layername={name}", TITLES[name], "ogr", options)
    return layer if layer.isValid() else None


def load_basin_layers(gpkg: Path | str) -> list:
    """Subbasins, reaches and junctions into the basin group, replacing the last generation's."""
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    old = root.findGroup(GROUP)
    if old is not None:
        project.removeMapLayers(old.findLayerIds())
        root.removeChildNode(old)
    layers = []
    for name in reversed(BASIN_LAYERS):  # junctions on top
        layer = open_basin_layer(gpkg, name)
        if layer is not None:
            STYLES[name](layer)
            layers.append(layer)
    if not layers:
        return []
    group = root.insertGroup(0, GROUP)
    for layer in reversed(layers):
        project.addMapLayer(layer, False)
        group.addLayer(layer)
    return layers
