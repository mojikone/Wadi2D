# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where every layer the plugin adds sits in the layer tree: one group per model, a fixed pattern inside it.

    Wadi2D - <model>                 the Run section's output folder, by name
        Results - <run>              one per run folder, newest on top, drawn over the inputs
            Lines                    lines drawn after the run (Result lines)
            Time slider              the frames as a mesh layer, the pixel slider layer
            Model setup              what the run used: domain, boundaries, inflows, design lines, cell grid, corridors
            Flood maps               the smooth hazard polygons and the depth drawing, when made
            Pixel rasters, the numbers of record
            Cell maps                maps/*.tif, closed
        Inputs                       made whole the first time, so each kind always has its place
            Terrain                  Preview terrain: the change and the modified ground
            Boundaries
            Structures
            Hydrology                the basin generated from the DEM; a Basin points layer made by the dock (W73);
                                     the storm map of Preview rain (W77)
            Mesh                     the mesh preview, suggested breaklines and thalwegs

Every name is a constant here, so changing one is one edit. A layer the plugin adds carries a custom property naming
its slot; a later run or preview takes away only its own slot's layers still inside the model's group. A layer the user
moved out stays where it is, and a layer or group the user put inside a results group that is being replaced is moved
up into the model's group, never deleted.
"""

from __future__ import annotations

import re
from pathlib import Path

from qgis.core import QgsLayerTreeGroup, QgsLayerTreeLayer, QgsProject

from .protocol import STUDY_SUFFIX

DASH = "\N{EN DASH}"  # the tree's dash; the docstring above writes it "-"
MODEL_PREFIX = f"Wadi2D {DASH} "
RESULTS_PREFIX = f"Results {DASH} "
NO_MODEL = "no output folder yet"

INPUTS = "Inputs"
TERRAIN = "Terrain"
BOUNDARIES = "Boundaries"
STRUCTURES = "Structures"
HYDROLOGY = "Hydrology"
MESH = "Mesh"
INPUT_GROUPS = (TERRAIN, BOUNDARIES, STRUCTURES, HYDROLOGY, MESH)

LINES = "Lines"
TIME = "Time slider"
SETUP = "Model setup"
MAPS = "Flood maps"
RECORD = "Pixel rasters, the numbers of record"
CELLS = "Cell maps"

ROLE = "wadi2d/role"  # on the plugin's groups: model, inputs, input, results
KEY = "wadi2d/key"  # the model's or the run's name, or the input's kind
SLOT = "wadi2d/slot"  # on the plugin's layer nodes: what made them, so the next one replaces only its own

# Slots of the Inputs layers.
SLOT_TERRAIN = "terrain preview"
SLOT_BASIN = "basin"
SLOT_BASIN_POINTS = "basin points"  # the user's edits (W73): a regeneration replaces the basin, never these
SLOT_RAIN = "storm map"  # Preview rain's map (W77): each preview replaces the last
SLOT_MESH = "mesh preview"
SLOT_SUGGEST = "suggested breaklines"
SLOT_RESULT = "result"


def model_title(model: str) -> str:
    return f"{MODEL_PREFIX}{model}"


def results_title(run: str) -> str:
    return f"{RESULTS_PREFIX}{run}"


def model_name(folder: Path | str | None) -> str:
    """The model of the Run section's output folder: its name."""
    name = Path(folder).name if folder else ""
    return name or NO_MODEL


def model_of_run(run: Path | str) -> str:
    """The model a run folder belongs to: ``bidah_2`` and ``bidah_arf`` are runs of ``bidah`` when ``bidah`` is beside them."""
    folder = Path(run)
    name = folder.name
    numbered = re.fullmatch(r"(.+)_\d+", name)
    if numbered and (folder.with_name(numbered.group(1))).exists():
        name = numbered.group(1)
    if name.endswith(STUDY_SUFFIX) and len(name) > len(STUDY_SUFFIX):
        name = name[: -len(STUDY_SUFFIX)]
    return name or NO_MODEL


def _groups(node):
    for child in node.children():
        if isinstance(child, QgsLayerTreeGroup):
            yield child
            yield from _groups(child)


def _find(parent, role: str, key: str):
    for group in _groups(parent):
        if group.customProperty(ROLE) == role and group.customProperty(KEY) == key:
            return group
    return None


def _new(parent, index: int, title: str, role: str, key: str):
    group = parent.insertGroup(index, title)
    group.setCustomProperty(ROLE, role)
    group.setCustomProperty(KEY, key)
    return group


def find_model(model: str):
    return _find(QgsProject.instance().layerTreeRoot(), "model", model)


def model_group(model: str):
    """The model's group, wherever the user left it; made at the top with its Inputs pattern when missing."""
    found = find_model(model)
    if found is None:
        found = _new(QgsProject.instance().layerTreeRoot(), 0, model_title(model), "model", model)
    inputs = _find(found, "inputs", model)
    if inputs is None:
        inputs = _new(found, len(found.children()), INPUTS, "inputs", model)
        inputs.setExpanded(False)
    for index, kind in enumerate(INPUT_GROUPS):
        if _find(inputs, "input", kind) is None:
            _new(inputs, min(index, len(inputs.children())), kind, "input", kind)
    return found


def input_group(model: str, kind: str):
    return _find(_find(model_group(model), "inputs", model), "input", kind)


def find_results(model: str, run: str):
    top = find_model(model)
    return _find(top, "results", run) if top is not None else None


def results_group(model: str, run: str, fresh: bool = False):
    """The run's group in its model, on top of the model's other results; ``fresh`` replaces it, at the same place."""
    top = model_group(model)
    old = _find(top, "results", run)
    if old is not None and not fresh:
        return old
    index = 0
    if old is not None:
        parent = old.parent()
        index = parent.children().index(old)
        _empty(old, top)
        parent.removeChildNode(old)
        top = parent
    return _new(top, index, results_title(run), "results", run)


def run_results(run: Path | str, label: str | None = None, fresh: bool = False):
    """The results group of a run folder; ``label`` names it when it is not the folder's own name."""
    folder = Path(run)
    return results_group(model_of_run(folder), label or folder.name, fresh)


def find_run_results(run: Path | str, label: str | None = None):
    """The results group of a run folder if the project still has it."""
    folder = Path(run)
    return find_results(model_of_run(folder), label or folder.name)


def drop_results(group) -> None:
    """A results group off the tree, its plugin layers out of the project, anything of the user's kept in the model."""
    parent = group.parent()
    _empty(group, parent)
    parent.removeChildNode(group)


def subgroup(parent, title: str, index: int | None = None):
    """A named group inside a results group, made when missing."""
    for child in parent.children():
        if isinstance(child, QgsLayerTreeGroup) and child.name() == title:
            return child
    return parent.insertGroup(len(parent.children()) if index is None else index, title)


def _empty(group, keep_in) -> None:
    """Takes the plugin's layers out of the project and moves anything of the user's up into ``keep_in``."""
    project = QgsProject.instance()
    owned = []
    for child in list(group.children()):
        if isinstance(child, QgsLayerTreeLayer) and child.customProperty(SLOT):
            owned.append(child.layerId())
        elif (
            isinstance(child, QgsLayerTreeGroup) and child.customProperty(ROLE) is None and _all_owned(child)
        ):
            owned.extend(child.findLayerIds())
        else:
            keep_in.insertChildNode(len(keep_in.children()), child.clone())
            group.removeChildNode(child)
    project.removeMapLayers(owned)


def _all_owned(group) -> bool:
    """A group the plugin made inside a results group: only its own layers in it, or nothing."""
    for child in group.children():
        if isinstance(child, QgsLayerTreeLayer) and not child.customProperty(SLOT):
            return False
        if isinstance(child, QgsLayerTreeGroup) and not _all_owned(child):
            return False
    return True


def add_layer(group, layer, slot: str = SLOT_RESULT, shown: bool = True, index: int | None = None):
    """The layer into the project and the group, marked as the plugin's; its tree node."""
    QgsProject.instance().addMapLayer(layer, False)
    node = group.insertLayer(len(group.children()) if index is None else index, layer)
    node.setCustomProperty(SLOT, slot)
    node.setItemVisibilityChecked(shown)
    return node


def clear_slot(model: str, slot: str) -> None:
    """The plugin's layers of one slot still inside the model's group; one the user moved out is left alone."""
    top = find_model(model)
    if top is None:
        return
    found = [node.layerId() for node in top.findLayers() if node.customProperty(SLOT) == slot]
    QgsProject.instance().removeMapLayers(found)
