# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""On QGIS's own Python: a run's domain edge checks land in its model's Inputs > Boundaries (W78).

Started by ``test_edge_qgis.py``. Argument: a folder holding run folders ``bidah`` (streams and pools) and ``bidah_2``
(nothing found). Prints ``EDGE PASSED`` as its last line.
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
from wadi2d_qgis.edge_layers import SLOT_EDGE, clear_edge_checks, load_edge_checks  # noqa: E402

project = QgsProject.instance()

layers = load_edge_checks(WORK / "bidah")
assert [layer.name() for layer in layers] == [
    "Streams across a closed domain edge",
    "Deep water against a closed domain edge",
], [layer.name() for layer in layers]
boundaries = g.input_group("bidah", g.BOUNDARIES)
nodes = [n for n in boundaries.findLayers() if n.customProperty(g.SLOT) == SLOT_EDGE]
assert len(nodes) == 2, "both layers in Inputs > Boundaries"
streams, pools = layers
assert streams.featureCount() == 2 and pools.featureCount() == 1
assert streams.renderer().type() == "categorizedSymbol"
assert {c.value() for c in streams.renderer().categories()} >= {"stream leaves", "stream enters", "pool"}

# the next run of the model takes the last one's away first, and a clean run adds nothing
first = [layer.id() for layer in layers]
clear_edge_checks(WORK / "bidah_2")
assert all(project.mapLayer(i) is None for i in first), "the model's old edge checks left the project"
assert load_edge_checks(WORK / "bidah_2") == []
assert not [n for n in boundaries.findLayers() if n.customProperty(g.SLOT) == SLOT_EDGE]

print("EDGE PASSED", flush=True)
sys.stdout.flush()
os._exit(0)
