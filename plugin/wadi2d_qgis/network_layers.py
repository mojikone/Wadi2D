# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A run's lumped network on the map (W88): the catchments that ran the HMS way, hatched and labelled with their area
and peak, those the 2D mesh left out in grey, and the reaches and junctions with theirs, in the run's group.

Every feature carries the element's ``name``, so a right-click on it opens its hydrograph in the Result lines panel.
A lumped-only run has nothing else to show; a run with a 2D part shows them over its maps, switched on."""

from __future__ import annotations

from pathlib import Path

from qgis.core import QgsVectorLayer

from . import style
from .layer_groups import NETWORK, add_layer, run_results, subgroup
from .protocol import NETWORK_FILE, NETWORK_LAYERS

TITLES = {
    "subbasins": "Catchments that ran the HMS way: area, peak outflow",
    "reaches": "Reaches of the lumped network: peak outflow",
    "points": "Junctions, reservoirs and outlets: peak outflow",
}
STYLES = {
    "subbasins": style.style_network_subbasins,
    "reaches": style.style_network_reaches,
    "points": style.style_network_points,
}


def open_network(run: Path | str) -> list:
    """The network's layers of a run, styled, points on top; empty for a run without them."""
    path = Path(run) / NETWORK_FILE
    if not path.is_file():
        return []
    options = QgsVectorLayer.LayerOptions()
    options.forceReadOnly = True  # a writable GeoPackage goes to WAL mode, and its connections lock each other out
    found = []
    for name in reversed(NETWORK_LAYERS):
        layer = QgsVectorLayer(f"{path}|layername={name}", TITLES[name], "ogr", options)
        if layer.isValid() and layer.featureCount() > 0:
            STYLES[name](layer)
            found.append(layer)
    return found


def load_network(run: Path | str, group_name: str = "", index: int = 0) -> list:
    """Under the run's results group, in its own subgroup at ``index``."""
    layers = open_network(run)
    if not layers:
        return []
    group = subgroup(run_results(run, group_name), NETWORK, index)
    for layer in layers:
        node = add_layer(group, layer)
        node.setExpanded(False)
    return layers
