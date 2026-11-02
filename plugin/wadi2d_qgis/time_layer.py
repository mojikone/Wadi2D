# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The saved frames of a run as a mesh layer that moves with QGIS's Temporal Controller."""

from __future__ import annotations

import json
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsDateTimeRange,
    QgsInterval,
    QgsMeshDatasetIndex,
    QgsMeshLayer,
    QgsProject,
    QgsTemporalNavigationObject,
    QgsUnitTypes,
)
from qgis.PyQt.QtWidgets import QDockWidget

from . import style
from .protocol import FRAMES_FILE, RUN_FILE
from .result_layers import GROUP_MAPS

LAYER_TITLE = "Flood over time, cells"


def has_results(run: Path | str) -> bool:
    return (Path(run) / "results.h5").is_file()


def _run_crs(run: Path) -> QgsCoordinateReferenceSystem:
    try:
        text = json.loads((run / RUN_FILE).read_text(encoding="utf-8")).get("crs", "")
    except (OSError, ValueError):
        text = ""
    crs = QgsCoordinateReferenceSystem(text)
    return crs if crs.isValid() else QgsProject.instance().crs()


def open_frames(run: Path) -> QgsMeshLayer | None:
    layer = QgsMeshLayer(str(run / FRAMES_FILE), LAYER_TITLE, "mdal")
    if not layer.isValid() or layer.datasetGroupCount() == 0 or not layer.temporalProperties().isActive():
        return None
    layer.setCrs(_run_crs(run))
    style.style_frames(layer)
    return layer


def _add(layer: QgsMeshLayer, group_name: str) -> None:
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    top = root.findGroup(group_name) or root.insertGroup(0, group_name)
    project.addMapLayer(layer, False)
    top.insertLayer(0, layer)
    maps = top.findGroup(GROUP_MAPS)
    if maps is not None:  # the run's maximum, under a flood that is still rising, would read as the flood
        maps.setItemVisibilityChecked(False)


def frame_interval_s(layer: QgsMeshLayer) -> float:
    """The time between the first two frames; a run of one frame has none to speak of."""
    provider = layer.dataProvider()
    if provider.datasetCount(0) < 2:
        return 60.0
    first = provider.datasetMetadata(QgsMeshDatasetIndex(0, 0)).time()
    second = provider.datasetMetadata(QgsMeshDatasetIndex(0, 1)).time()
    return (second - first) * 3600.0


def show_controller(canvas, main_window, layer: QgsMeshLayer) -> None:
    """The Temporal Controller on the run's whole time, one step per saved frame, at the start."""
    controller = canvas.temporalController()
    extent: QgsDateTimeRange = layer.temporalProperties().timeExtent()
    controller.setNavigationMode(QgsTemporalNavigationObject.Animated)
    controller.setTemporalExtents(extent)
    controller.setFrameDuration(QgsInterval(frame_interval_s(layer), QgsUnitTypes.TemporalSeconds))
    controller.rewindToStart()
    for dock in main_window.findChildren(QDockWidget):
        if "temporal" in dock.objectName().lower() or "temporal" in dock.windowTitle().lower():
            dock.setVisible(True)
            dock.raise_()


def load_frames(run: Path | str, canvas, main_window) -> QgsMeshLayer | None:
    folder = Path(run)
    layer = open_frames(folder)
    if layer is None:
        return None
    _add(layer, folder.name)
    show_controller(canvas, main_window, layer)
    return layer
