# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""On QGIS's own Python: a run's lumped network in its group (W88).

Started by ``test_network_qgis.py``. Arguments: a lumped-only run folder, a run folder with a 2D part. Prints
``NETWORK PASSED`` as its last line.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "plugin"))
LUMPED, HYBRID = Path(sys.argv[1]), Path(sys.argv[2])

from qgis.core import QgsApplication, QgsCategorizedSymbolRenderer, QgsProject  # noqa: E402

app = QgsApplication([], False)
app.initQgis()

from wadi2d_qgis import layer_groups as g  # noqa: E402
from wadi2d_qgis.network_layers import TITLES, load_network  # noqa: E402
from wadi2d_qgis.protocol import is_lumped_run  # noqa: E402
from wadi2d_qgis.time_layer import has_frames, has_results  # noqa: E402

assert is_lumped_run(LUMPED) and has_results(LUMPED) and not has_frames(LUMPED), "a lumped run has no frames"
assert not is_lumped_run(HYBRID) and has_frames(HYBRID)

layers = load_network(LUMPED, LUMPED.name)
assert [layer.name() for layer in layers] == [TITLES["points"], TITLES["subbasins"]], [layer.name() for layer in layers]
top = g.find_run_results(LUMPED, LUMPED.name)
assert top is not None
(network,) = [child for child in top.children() if child.name() == g.NETWORK]
assert len(network.findLayers()) == 2 and all(node.isVisible() for node in network.findLayers())
points, subbasins = layers
assert {f["name"] for f in points.getFeatures()} == {"J1", "J2", "Out"}
assert points.labelsEnabled() and points.labeling().settings().fieldName == "label"
renderer = subbasins.renderer()
assert isinstance(renderer, QgsCategorizedSymbolRenderer) and renderer.classAttribute() == "left_out"
labels = {f["name"]: f["label"] for f in subbasins.getFeatures()}
assert set(labels) == {"Up", "Low"} and all("km2" in text and "m3/s" in text for text in labels.values()), labels

hybrid = load_network(HYBRID, HYBRID.name)
(cut,) = [layer for layer in hybrid if layer.name() == TITLES["subbasins"]]
(row,) = list(cut.getFeatures())
assert row["name"] == "Up" and row["left_out"] == 1 and "left out of the 2D mesh" in row["label"]
assert len(QgsProject.instance().mapLayers()) == 2 + len(hybrid)
print("NETWORK PASSED")
app.exitQgis()
