# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The product layers of a run folder: opened, styled, and put in the layer tree under groups."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from qgis.core import (
    QgsMapLayerLegendUtils,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from . import style
from .map_notes import class_labels, read_facts
from .protocol import (
    BOUNDARY_LAYER,
    CELL_GRID_FILE,
    CELL_GRID_LAYER,
    DEPTH_DRAWING,
    DOMAIN_LAYER,
    HAZARD_LAYER,
    INFLOW_LAYER,
    LAYERS_FILE,
    LINE_LAYER,
    PIXEL_DEPTH,
    PIXEL_DIR,
    PIXEL_DV,
    PIXEL_HAZARD,
    PIXEL_SPEED,
    REACH_LAYER,
    SUBBASIN_LAYER,
    cell_grid_scale,
    cell_grid_title,
)

GROUP_MAPS = "Flood maps"
GROUP_SETUP = "Model setup"
GROUP_RECORD = "Pixel rasters, the numbers of record"
GROUP_CELLS = "Cell maps"


@dataclass
class RunLayers:
    """Styled layers of a run, none in the project yet; a layer the run does not have is None."""

    depth: object = None
    hazard: object = None
    domain: object = None
    subbasins: object = None
    inflows: object = None
    boundaries: object = None
    lines: object = None
    reaches: object = None
    record: list = field(default_factory=list)

    def setup(self) -> list:
        """Top first."""
        found = (self.lines, self.inflows, self.boundaries, self.domain, self.reaches, self.subbasins)
        return [layer for layer in found if layer is not None]

    def overlays(self) -> list:
        """What is drawn over the results, top first."""
        return [layer for layer in (self.lines, self.inflows, self.boundaries, self.domain) if layer is not None]


def has_products(run: Path | str) -> bool:
    return (Path(run) / PIXEL_DIR / DEPTH_DRAWING).is_file() and (Path(run) / PIXEL_DIR / LAYERS_FILE).is_file()


def _vector(run: Path, layer_name: str, title: str):
    uri = f"{run / PIXEL_DIR / LAYERS_FILE}|layername={layer_name}"
    options = QgsVectorLayer.LayerOptions()
    options.forceReadOnly = True  # a writable GeoPackage goes to WAL mode, and its connections then lock each other out
    layer = QgsVectorLayer(uri, title, "ogr", options)
    return layer if layer.isValid() and layer.featureCount() > 0 else None


def _raster(run: Path, name: str, title: str):
    layer = QgsRasterLayer(str(run / PIXEL_DIR / name), title)
    return layer if layer.isValid() else None


def open_layers(run: Path | str, leave_out: str = "") -> RunLayers:
    """Everything a run folder holds, styled. ``leave_out`` hides design lines with that word in their name."""
    folder = Path(run)
    found = RunLayers()
    facts = read_facts(folder)
    found.depth = _raster(folder, DEPTH_DRAWING, "Maximum depth, m")
    if found.depth is not None:
        style.style_depth_drawing(found.depth)
    found.hazard = _vector(folder, HAZARD_LAYER, "AIDR hazard class")
    if found.hazard is not None:
        style.style_hazard_classes(found.hazard, class_labels(facts.limits))
    found.domain = _vector(folder, DOMAIN_LAYER, "2D model domain, closed walls except open boundaries")
    if found.domain is not None:
        style.style_domain(found.domain)
    found.subbasins = _vector(folder, SUBBASIN_LAYER, "Subbasins")
    if found.subbasins is not None:
        style.style_subbasins(found.subbasins)
    found.inflows = _vector(folder, INFLOW_LAYER, "Lumped hydrograph enters 2D here")
    if found.inflows is not None:
        style.style_inflows(found.inflows)
    found.boundaries = _vector(folder, BOUNDARY_LAYER, "Open boundary")
    if found.boundaries is not None:
        style.style_boundaries(found.boundaries)
    found.lines = _vector(folder, LINE_LAYER, "Design line")
    if found.lines is not None:
        if leave_out:
            found.lines.setSubsetString(f"\"label\" NOT LIKE '%{leave_out}%'")
        style.style_lines(found.lines)
    found.reaches = _vector(folder, REACH_LAYER, "Reach, routed by the 2D model here")
    if found.reaches is not None:
        style.style_reaches(found.reaches)
    record = (
        (PIXEL_HAZARD, "Hazard class", style.style_pixel_hazard),
        (PIXEL_DEPTH, "Depth, m", style.style_pixel_depth),
        (PIXEL_SPEED, "Speed, m/s", None),
        (PIXEL_DV, "Depth x speed, m2/s", None),
    )
    for name, title, styler in record:
        layer = _raster(folder, name, title)
        if layer is not None:
            if styler is not None:
                styler(layer)
            found.record.append(layer)
    return found


def hide_band_name(tree_layer) -> None:
    """No 'Band 1 (Gray)' line: keep every legend node but the first of a raster."""
    count = len(tree_layer.layer().legend().createLayerTreeModelLegendNodes(tree_layer))
    if count > 1:
        QgsMapLayerLegendUtils.setLegendNodeOrder(tree_layer, list(range(1, count)))
        tree_layer.layer().legendChanged.emit()  # the layer panel has already drawn this legend


def _add(group, layers: list, shown: tuple = ()) -> None:
    project = QgsProject.instance()
    for layer in layers:
        project.addMapLayer(layer, False)
        node = group.addLayer(layer)
        node.setItemVisibilityChecked(layer in shown)
        node.setExpanded(False)
        if isinstance(layer, QgsRasterLayer):
            hide_band_name(node)


def open_cell_grid(run: Path | str):
    """The real grid of a run, styled, or None for a run from before it was written."""
    uri = f"{Path(run) / CELL_GRID_FILE}|layername={CELL_GRID_LAYER}"
    options = QgsVectorLayer.LayerOptions()
    options.forceReadOnly = True
    layer = QgsVectorLayer(uri, "Cell grid", "ogr", options)
    if not layer.isValid() or layer.featureCount() == 0:
        return None
    size = layer.fields().indexOf("cell_m")
    finest, coarsest = float(layer.minimumValue(size)), float(layer.maximumValue(size))
    layer.setName(cell_grid_title(finest, coarsest))
    style.style_cell_grid(layer, cell_grid_scale(finest))
    return layer


def load_cell_grid(run: Path | str, group_name: str):
    """Under Model setup, with or without pixel maps: a run that made none has the grid all the same."""
    layer = open_cell_grid(run)
    if layer is None:
        return None
    root = QgsProject.instance().layerTreeRoot()
    top = root.findGroup(group_name) or root.insertGroup(0, group_name)
    setup = top.findGroup(GROUP_SETUP) or top.insertGroup(0, GROUP_SETUP)
    _add(setup, [layer], (layer,))
    return layer


def load_products(run: Path | str, group_name: str) -> RunLayers | None:
    """The product layers on top of the run's group, grouped; the depth drawing is the one switched on."""
    if not has_products(run):
        return None
    root = QgsProject.instance().layerTreeRoot()
    top = root.findGroup(group_name) or root.insertGroup(0, group_name)
    found = open_layers(run)
    record = top.insertGroup(0, GROUP_RECORD)
    maps = top.insertGroup(0, GROUP_MAPS)
    setup = top.insertGroup(0, GROUP_SETUP)
    _add(setup, found.setup(), (found.domain, found.boundaries, found.inflows, found.lines))
    _add(maps, [layer for layer in (found.hazard, found.depth) if layer is not None], (found.depth,))
    _add(record, found.record)
    record.setExpanded(False)
    return found
