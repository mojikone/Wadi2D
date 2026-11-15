# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""On QGIS's own Python: a run's pits and the cells that set its time step land in its model's Inputs > Terrain (W85).

Started by ``test_checks_qgis.py``. Argument: a folder holding run folders ``wadi`` (two pits and one limiter cell)
and ``wadi_2`` (nothing found). Prints ``CHECKS PASSED`` as its last line.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "plugin"))
WORK = Path(sys.argv[1])

from qgis.core import QgsApplication, QgsProject  # noqa: E402

app = QgsApplication([], False)
app.initQgis()

from wadi2d_qgis import layer_groups as g  # noqa: E402
from wadi2d_qgis.check_layers import SLOT_CHECKS, clear_terrain_checks, load_terrain_checks  # noqa: E402

project = QgsProject.instance()

layers = load_terrain_checks(WORK / "wadi")
assert [layer.name() for layer in layers] == [
    "Pits in the ground: small and deep",
    "Cells that set the time step",
], [layer.name() for layer in layers]
terrain = g.input_group("wadi", g.TERRAIN)
nodes = [n for n in terrain.findLayers() if n.customProperty(g.SLOT) == SLOT_CHECKS]
assert len(nodes) == 2, "both layers in Inputs > Terrain"
pits, limiter = layers
assert pits.featureCount() == 2 and limiter.featureCount() == 1
assert {f.name() for f in pits.fields()} >= {"depth_m", "area_m2", "volume_m3", "spill_m", "filled"}
assert max(f["depth_m"] for f in pits.getFeatures()) == 117.07
assert {f.name() for f in limiter.fields()} >= {"ticks", "dt_min_s", "hydraulic_depth", "dt_without_tile"}
assert pits.renderer().type() == "singleSymbol" and pits.readOnly()

# the next run of the model takes the last one's away first, and a clean run adds nothing
first = [layer.id() for layer in layers]
clear_terrain_checks(WORK / "wadi_2")
assert all(project.mapLayer(i) is None for i in first), "the model's old checks left the project"
assert load_terrain_checks(WORK / "wadi_2") == []
assert not [n for n in terrain.findLayers() if n.customProperty(g.SLOT) == SLOT_CHECKS]

print("CHECKS PASSED", flush=True)
sys.stdout.flush()
os._exit(0)
