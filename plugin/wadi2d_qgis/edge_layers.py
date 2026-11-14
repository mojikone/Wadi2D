# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The domain edge checks of a run on the map (W78): streams that cross a closed edge, found before the run, and deep
water held against one, found after it, as points in the model's Inputs > Boundaries. The engine writes them in the run
folder's ``edge_checks.gpkg``; the warnings in the dock say the same in words.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsMarkerSymbol,
    QgsRendererCategory,
    QgsVectorLayer,
)

from .layer_groups import BOUNDARIES, add_layer, clear_slot, input_group, model_of_run

EDGE_FILE = "edge_checks.gpkg"  # the engine's wadi2d.edge_valleys.FILE
SLOT_EDGE = "edge checks"
LAYERS = (
    ("edge_streams", "Streams across a closed domain edge"),
    ("edge_pools", "Deep water against a closed domain edge"),
)
MARKERS = {
    "stream leaves": ("triangle", "#c00000", "Stream leaves: no outflow line"),
    "stream enters": ("triangle", "#d08000", "Stream enters: no inflow line"),
    "pool": ("circle", "#0050c0", "Pool the edge holds"),
    "deep water": ("circle", "#7a00a0", "Deep water along the edge"),
    "bowl": ("circle", "#909090", "Edge cells past a divide"),
}
SIZE_MM = "4.0"


def _style(layer) -> None:
    categories = []
    for kind, (shape, colour, label) in MARKERS.items():
        symbol = QgsMarkerSymbol.createSimple(
            {"name": shape, "color": colour, "outline_color": "#ffffff", "size": SIZE_MM}
        )
        categories.append(QgsRendererCategory(kind, symbol, label))
    layer.setRenderer(QgsCategorizedSymbolRenderer("kind", categories))


def open_edge_checks(run: Path | str) -> list:
    """The run's edge check layers that hold a point, styled; none for a clean run or one from before W78."""
    path = Path(run) / EDGE_FILE
    if not path.is_file():
        return []
    options = QgsVectorLayer.LayerOptions()
    options.forceReadOnly = True  # the next run rewrites the file in place
    found = []
    for name, title in LAYERS:
        layer = QgsVectorLayer(f"{path}|layername={name}", title, "ogr", options)
        if layer.isValid() and layer.featureCount() > 0:
            _style(layer)
            found.append(layer)
    return found


def clear_edge_checks(run: Path | str) -> None:
    """The model's edge check layers off the map, so the run about to start can rewrite its file."""
    clear_slot(model_of_run(run), SLOT_EDGE)


def load_edge_checks(run: Path | str) -> list:
    """The run's edge checks on top of the model's Inputs > Boundaries, the last run's gone."""
    model = model_of_run(run)
    clear_slot(model, SLOT_EDGE)
    layers = open_edge_checks(run)
    if layers:
        group = input_group(model, BOUNDARIES)
        for index, layer in enumerate(layers):
            add_layer(group, layer, SLOT_EDGE, index=index)
    return layers
