# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The storm map of Preview rain (W77), in the model's Inputs > Hydrology; a new preview replaces the last.

The engine's ``rain-preview --map`` writes ``rain_map.json``: every lumped subbasin and the 2D area with its polygon
and depth after the area reduction, and for gridded or gauge rain a total-depth raster. The plugin only draws them.
"""

from __future__ import annotations

import json
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

from . import style
from .layer_groups import HYDROLOGY, SLOT_RAIN, add_layer, clear_slot, input_group

MAP_FILE = "rain_map.json"
AREAS_TITLE = "Rain depth by area, before the run"
TOTAL_TITLE = "Total rain depth, before the run"
FIELDS = (("name", QVariant.String), ("mode", QVariant.String), ("area_km2", QVariant.Double),
          ("depth_mm", QVariant.Double), ("peak_mm_h", QVariant.Double), ("label", QVariant.String))  # fmt: skip


def _areas_layer(found: dict, crs: QgsCoordinateReferenceSystem):
    layer = QgsVectorLayer(f"MultiPolygon?crs={crs.authid() or 'EPSG:4326'}", AREAS_TITLE, "memory")
    layer.setCrs(crs)
    provider = layer.dataProvider()
    provider.addAttributes([QgsField(name, kind) for name, kind in FIELDS])
    layer.updateFields()
    features = []
    for area in found["areas"]:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt(area["wkt"]))
        label = f"{area['name']}\n{area['depth_mm']:.1f} mm"
        feature.setAttributes(
            [area["name"], area["mode"], area["area_km2"], area["depth_mm"], area["peak_mm_h"], label]
        )
        features.append(feature)
    provider.addFeatures(features)
    layer.updateExtents()
    depths = [area["depth_mm"] for area in found["areas"]]
    style.style_rain_areas(layer, min(depths), max(depths))
    return layer


def _total_layer(path: Path):
    layer = QgsRasterLayer(str(path), TOTAL_TITLE)
    if not layer.isValid():
        return None
    stats = layer.dataProvider().bandStatistics(1)
    style.style_rain_total(layer, stats.minimumValue, stats.maximumValue)
    return layer


def load_rain_map(folder: Path | str, model: str) -> list:
    """The map's layers into the model's Inputs > Hydrology, replacing the last preview's there."""
    clear_slot(model, SLOT_RAIN)
    folder = Path(folder)
    found = json.loads((folder / MAP_FILE).read_text(encoding="utf-8"))
    crs = (
        QgsCoordinateReferenceSystem.fromWkt(found["crs"])
        if found.get("crs")
        else QgsCoordinateReferenceSystem()
    )
    layers = []
    if found["areas"]:
        layers.append(_areas_layer(found, crs))
    if found.get("total"):
        total = _total_layer(folder / found["total"])
        if total is not None:
            layers.append(total)
    if layers:
        group = input_group(model, HYDROLOGY)
        for index, layer in enumerate(layers):
            add_layer(group, layer, SLOT_RAIN, index=index)
    return layers
