# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""What a run found wrong with its ground, on the map (W85): the pits, small deep sinks that water can leave over no
face, and the cells that set the time step when the run was asked to name them. Points in the model's Inputs > Terrain.
The engine writes them in the run folder's ``terrain_checks.gpkg`` and ``step_limiter.gpkg``; the warnings in the dock
say the same in words.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer, QgsVectorLayer

from .layer_groups import TERRAIN, add_layer, clear_slot, input_group, model_of_run

SLOT_CHECKS = "terrain checks"
SOURCES = (
    # file (the engine's wadi2d.terrain.pits.FILE and wadi2d.engine.step_limiter.FILE), layer, title, marker
    ("terrain_checks.gpkg", "pits", "Pits in the ground: small and deep", ("diamond", "#b00020")),
    ("step_limiter.gpkg", "step_limiter", "Cells that set the time step", ("star", "#d08000")),
)
SIZE_MM = "4.0"


def open_terrain_checks(run: Path | str) -> list:
    """The run's check layers that hold a point, styled; none for a clean run or one from before W85."""
    options = QgsVectorLayer.LayerOptions()
    options.forceReadOnly = True  # the next run rewrites the files in place
    found = []
    for file, name, title, (shape, colour) in SOURCES:
        path = Path(run) / file
        if not path.is_file():
            continue
        layer = QgsVectorLayer(f"{path}|layername={name}", title, "ogr", options)
        if layer.isValid() and layer.featureCount() > 0:
            symbol = QgsMarkerSymbol.createSimple(
                {"name": shape, "color": colour, "outline_color": "#ffffff", "size": SIZE_MM}
            )
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            found.append(layer)
    return found


def clear_terrain_checks(run: Path | str) -> None:
    """The model's check layers off the map, so the run about to start can rewrite its files."""
    clear_slot(model_of_run(run), SLOT_CHECKS)


def load_terrain_checks(run: Path | str) -> list:
    """The run's checks on top of the model's Inputs > Terrain, the last run's gone."""
    model = model_of_run(run)
    clear_slot(model, SLOT_CHECKS)
    layers = open_terrain_checks(run)
    if layers:
        group = input_group(model, TERRAIN)
        for index, layer in enumerate(layers):
            add_layer(group, layer, SLOT_CHECKS, index=index)
    return layers
