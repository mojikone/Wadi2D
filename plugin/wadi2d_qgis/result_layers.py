# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The product layers of a run folder: opened, styled, and put in the run's results group (``layer_groups``).

A ``group_name`` below is the run's label in its model, the run folder's name when empty."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from qgis.core import (
    QgsMapLayerLegendUtils,
    QgsRasterLayer,
    QgsVectorLayer,
)

from . import style
from .layer_groups import CELLS, MAPS, RECORD, SETUP, add_layer, find_run_results, run_results, subgroup
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
    PIXEL_LEVEL,
    PIXEL_HAZARD,
    PIXEL_SPEED,
    REACH_LAYER,
    STRIP_CELLS_LAYER,
    STRIP_FACES_LAYER,
    STRIP_MESH_FILE,
    SUBBASIN_LAYER,
    cell_grid_scale,
    cell_grid_title,
    has_drawings,
    has_record,
)

GROUP_MAPS = MAPS  # the names live in layer_groups; these stay for the callers that know them by these names
GROUP_SETUP = SETUP
GROUP_RECORD = RECORD
GROUP_CELLS = CELLS


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
    record_depth: object = None
    """The depth raster of record: what a run with no depth drawing shows."""

    def setup(self) -> list:
        """Top first."""
        found = (self.lines, self.inflows, self.boundaries, self.domain, self.reaches, self.subbasins)
        return [layer for layer in found if layer is not None]

    def overlays(self) -> list:
        """What is drawn over the results, top first."""
        return [layer for layer in (self.lines, self.inflows, self.boundaries, self.domain) if layer is not None]


def has_products(run: Path | str) -> bool:
    """A run with its pixel rasters: its layers load and its sheets can be made. The smooth polygons and the depth
    picture are not asked of it: a run makes them only when ticked, and Make map has them made when they are missing."""
    return has_record(run)


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
        (PIXEL_LEVEL, "Highest water level, m", None),
    )
    for name, title, styler in record:
        layer = _raster(folder, name, title)
        if layer is not None:
            if styler is not None:
                styler(layer)
            found.record.append(layer)
            if name == PIXEL_DEPTH:
                found.record_depth = layer
    return found


def hide_band_name(tree_layer) -> None:
    """No 'Band 1 (Gray)' line: keep every legend node but the first of a raster."""
    count = len(tree_layer.layer().legend().createLayerTreeModelLegendNodes(tree_layer))
    if count > 1:
        QgsMapLayerLegendUtils.setLegendNodeOrder(tree_layer, list(range(1, count)))
        tree_layer.layer().legendChanged.emit()  # the layer panel has already drawn this legend


def _add(group, layers: list, shown: tuple = ()) -> None:
    for layer in layers:
        node = add_layer(group, layer, shown=layer in shown)
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


def load_cell_grid(run: Path | str, group_name: str = ""):
    """Under the run's Model setup, with or without pixel maps: a run that made none has the grid all the same."""
    layer = open_cell_grid(run)
    if layer is None:
        return None
    setup = subgroup(run_results(run, group_name), GROUP_SETUP, 0)
    _add(setup, [layer], (layer,))
    return layer


def open_strip_mesh(run: Path | str) -> list:
    """The aligned cells and their faces of a run with corridors, styled; empty for a run without."""
    path = Path(run) / STRIP_MESH_FILE
    if not path.is_file():
        return []
    options = QgsVectorLayer.LayerOptions()
    options.forceReadOnly = True
    out = []
    for name, title, styler in (
        (STRIP_FACES_LAYER, "Corridor faces: on a bank (red), the join (orange)", style.style_strip_faces),
        (STRIP_CELLS_LAYER, "Corridor cells, aligned with the banks", style.style_strip_cells),
        (STRIP_CELLS_LAYER, STRIP_DEPTH_TITLE, style.style_strip_depth),
    ):
        layer = QgsVectorLayer(f"{path}|layername={name}", title, "ogr", options)
        if layer.isValid() and layer.featureCount() > 0:
            styler(layer)
            out.append(layer)
    return out


STRIP_DEPTH_TITLE = "Aligned cells: maximum depth, m"
"""The aligned cells filled by their own maximum depth, the cutoff applied (W88); off, since the pixel depth covers
them where the pixel maps were made."""


def load_strip_mesh(run: Path | str, group_name: str = "") -> list:
    """Under Model setup beside the cell grid: the corridors a run stepped, their cells and faces, and the cells by
    their maximum depth, off."""
    layers = open_strip_mesh(run)
    if not layers:
        return []
    setup = subgroup(run_results(run, group_name), GROUP_SETUP, 0)
    _add(setup, layers, tuple(layer for layer in layers if layer.name() != STRIP_DEPTH_TITLE))
    return layers


def load_products(run: Path | str, group_name: str = "") -> RunLayers | None:
    """The product layers on top of the run's group, grouped; the depth drawing is the one switched on.

    A run that made no drawing has no Flood maps group: its depth raster of record is switched on in its place."""
    if not has_products(run):
        return None
    top = run_results(run, group_name)
    found = open_layers(run)
    drawn = [layer for layer in (found.hazard, found.depth) if layer is not None]
    record = subgroup(top, GROUP_RECORD, 0)
    if drawn:
        _add(subgroup(top, GROUP_MAPS, 0), drawn, (found.depth,))
    setup = subgroup(top, GROUP_SETUP, 0)
    _add(setup, found.setup(), (found.domain, found.boundaries, found.inflows, found.lines))
    _add(record, found.record, () if found.depth is not None else (found.record_depth,))
    record.setExpanded(found.depth is None)
    return found


def load_drawings(run: Path | str, group_name: str = "") -> list:
    """The polygons and the depth picture made after the run, into the run's group if the project still has it and
    they are not there yet; the depth picture takes over from the depth raster of record."""
    top = find_run_results(run, group_name)
    if top is None or top.findGroup(GROUP_MAPS) is not None or not has_drawings(run):
        return []
    folder = Path(run)
    depth = _raster(folder, DEPTH_DRAWING, "Maximum depth, m")
    hazard = _vector(folder, HAZARD_LAYER, "AIDR hazard class")
    if depth is not None:
        style.style_depth_drawing(depth)
    if hazard is not None:
        style.style_hazard_classes(hazard, class_labels(read_facts(folder).limits))
    drawn = [layer for layer in (hazard, depth) if layer is not None]
    if not drawn:
        return []
    record = top.findGroup(GROUP_RECORD)
    at = top.children().index(record) if record is not None else 0
    _add(subgroup(top, GROUP_MAPS, at), drawn, (depth,))
    if record is not None and depth is not None:
        for node in record.findLayers():
            node.setItemVisibilityChecked(False)
        record.setExpanded(False)
    return drawn
