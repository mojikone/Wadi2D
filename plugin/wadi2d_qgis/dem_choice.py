# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The DEM the Terrain section starts on (W101, his fault of 2026-11-16): never a layer a run wrote.

A project of results holds rasters of Wadi2D's own (depth, speed, hazard, cell maps), and a layer picker takes the first
raster it finds, so the DEM was a depth map. The default is now the layer whose file is the DEM a run in the project was
made on, read from that run's ``job.json``; else nothing, and Terrain says the DEM is missing.

Interface: :func:`is_product`, :func:`run_folder_of`, :func:`default_dem`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .layer_groups import RESULTS_PREFIX
from .protocol import JOB_FILE

PRODUCT_FOLDERS = ("pixels", "maps", "windows", "composite")
"""Folders of a run that hold its rasters."""


def _file(source: str) -> str:
    return os.path.normcase(os.path.normpath(source.split("|")[0])) if source else ""


def run_folder_of(source: str) -> Path | None:
    """The run folder a file lies in, at any depth: the nearest folder above it holding a ``job.json``."""
    path = Path(source.split("|")[0])
    for folder in list(path.parents)[:4]:
        if (folder / JOB_FILE).is_file():
            return folder
    return None


def _under_results(layer, root) -> bool:
    node = root.findLayer(layer.id()) if root is not None else None
    group = node.parent() if node is not None else None
    while group is not None:
        if group.name().startswith(RESULTS_PREFIX):
            return True
        group = group.parent()
    return False


def is_product(layer, root=None) -> bool:
    """A layer a run wrote: in a run folder's rasters, or under a results group of the layer tree."""
    source = layer.source().split("|")[0]
    parts = {part.lower() for part in Path(source).parts}
    return _under_results(layer, root) or (run_folder_of(source) is not None and bool(parts & set(PRODUCT_FOLDERS)))


def _job_dems(layers) -> set[str]:
    """The DEMs the runs of these layers were made on, by their files."""
    found = set()
    for folder in {run_folder_of(layer.source()) for layer in layers} - {None}:
        try:
            dem = json.loads((folder / JOB_FILE).read_text(encoding="utf-8"))["terrain"]["dem"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        found.add(_file(dem))
    return found


def default_dem(project):
    """The raster the Terrain section starts on: the DEM of a run in the project, never a run's own raster; None
    when there is none to be sure of."""
    from qgis.core import QgsRasterLayer

    root = project.layerTreeRoot()
    layers = list(project.mapLayers().values())
    wanted = _job_dems(layers)
    rasters = [layer for layer in layers if isinstance(layer, QgsRasterLayer) and not is_product(layer)]
    named = [layer for layer in rasters if _file(layer.source()) in wanted]
    # the DEM's own file wherever it sits in the tree, one outside a results group first
    return next((layer for layer in named if not _under_results(layer, root)), named[0] if named else None)
