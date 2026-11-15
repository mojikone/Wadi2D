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
# the depth cutoff (W88): a cell under it draws nothing, the raster's numbers unchanged; a new cutoff restyles
from qgis.core import QgsRasterLayer, QgsSettings  # noqa: E402
from wadi2d_qgis import settings, style  # noqa: E402

QgsSettings().remove(settings.DEPTH_CUTOFF_KEY)
assert settings.depth_cutoff() == style.DEPTH_CUTOFF_M == 0.05
depth = QgsRasterLayer(str(HYBRID / "maps" / "max_depth.tif"), "depth")
assert depth.isValid()
style.style_depth(depth)
QgsProject.instance().addMapLayer(depth)


def drawn(layer):
    """(values, alphas) of the whole raster as the renderer draws it."""
    provider, extent = layer.dataProvider(), layer.extent()
    w, h = layer.width(), layer.height()
    values = provider.block(1, extent, w, h)
    image = layer.renderer().block(1, extent, w, h)
    out = []
    for row in range(h):
        for col in range(w):
            value = values.value(row, col)
            if values.isNoData(row, col):
                continue
            out.append((value, (image.color(row, col) >> 24) & 0xFF))
    return out


shallow = [(v, a) for v, a in drawn(depth) if 0.0 < v < 0.05]
deep = [(v, a) for v, a in drawn(depth) if v >= 0.06]
assert shallow and deep, (len(shallow), len(deep))
assert all(a == 0 for _v, a in shallow) and all(a > 0 for _v, a in deep)
shader = depth.renderer().shader().rasterShaderFunction()
assert shader.clip() and abs(shader.minimumValue() - 0.05) < 1e-9
settings.set_depth_cutoff(0.0)
assert style.restyle_depth_layers() == 1
assert any(a > 0 for v, a in drawn(depth) if 0.0 < v < 0.05), "0 draws every wet cell"
assert not depth.renderer().shader().rasterShaderFunction().clip()
settings.set_depth_cutoff(0.05)
cut = style.cut_items(
    [style.QgsColorRampShader.ColorRampItem(0.0, style.QColor(0, 0, 0, 0)),
     style.QgsColorRampShader.ColorRampItem(0.1, style.QColor(100, 200, 50, 200))], 0.05,
)  # fmt: skip
assert cut[0].value == 0.05 and cut[0].color.getRgb() == (50, 100, 25, 100)
QgsSettings().remove(settings.DEPTH_CUTOFF_KEY)
print("NETWORK PASSED")
app.exitQgis()
