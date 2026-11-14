# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The three layers of a generated basin, styled, in the model's Inputs > Hydrology; a new generation replaces the last."""

from __future__ import annotations

from pathlib import Path

from qgis.core import QgsVectorLayer

from . import style
from .layer_groups import HYDROLOGY, SLOT_BASIN, add_layer, clear_slot, input_group
from .protocol import BASIN_LAYERS

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


def load_basin_layers(gpkg: Path | str, model: str) -> list:
    """Subbasins, reaches and junctions into the model's Inputs > Hydrology, replacing the last generation's there."""
    clear_slot(model, SLOT_BASIN)
    layers = []
    for name in reversed(BASIN_LAYERS):  # junctions on top
        layer = open_basin_layer(gpkg, name)
        if layer is not None:
            STYLES[name](layer)
            layers.append(layer)
    if not layers:
        return []
    group = input_group(model, HYDROLOGY)
    for index, layer in enumerate(reversed(layers)):
        add_layer(group, layer, SLOT_BASIN, index=index)
    return layers
