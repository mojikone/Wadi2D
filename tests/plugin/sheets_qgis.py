# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""On QGIS's own Python: a real run folder through the layers and the map sheets.

Started by ``test_sheets_qgis.py``. Argument: the run folder. Prints ``SHEETS PASSED`` as its last line.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "plugin"))
RUN = Path(sys.argv[1])

from qgis.core import QgsApplication, QgsLayoutItemLegend, QgsLayoutItemMap, QgsProject  # noqa: E402

app = QgsApplication([], False)
app.initQgis()

from wadi2d_qgis.live_layer import load_maps  # noqa: E402
from wadi2d_qgis.map_sheets import build_book, export_pdf, nice_segment, sheets_file  # noqa: E402
from wadi2d_qgis.result_layers import (  # noqa: E402  # noqa: E402
    GROUP_CELLS,
    GROUP_MAPS,
    GROUP_RECORD,
    GROUP_SETUP,
    has_products,
    load_products,
    open_layers,
)

project = QgsProject.instance()
assert has_products(RUN)
found = open_layers(RUN)
assert found.depth is not None and found.depth.isValid()
assert found.hazard is not None and found.hazard.featureCount() >= 1
assert found.domain is not None and found.domain.isValid()
assert found.boundaries is not None
assert len(found.record) == 4

colours = {c.value(): c.symbol().color().name() for c in found.hazard.renderer().categories()}
assert colours[1] == "#0000ff" and colours[6] == "#ff0000", colours
items = found.depth.renderer().shader().rasterShaderFunction().colorRampItemList()
assert items[-1].value == 3.0 and items[-1].color.name() == "#08306b"
assert items[0].color.alpha() == 0
assert found.depth.resampleFilter().zoomedInResampler() is not None

load_maps(RUN, "run", tucked=True)
load_products(RUN, "run")
top = project.layerTreeRoot().findGroup("run")
names = [child.name() for child in top.children()]
assert names == [GROUP_SETUP, GROUP_MAPS, GROUP_RECORD, GROUP_CELLS], names
shown = [n.name() for n in top.findLayers() if n.isVisible()]
assert "Maximum depth, m" in shown and "AIDR hazard class" not in shown, shown
assert "max_depth" not in shown

book = build_book(RUN, title="Test", background="hillshade")
maps = [i for i in book.layout.items() if isinstance(i, QgsLayoutItemMap)]
legends = [i for i in book.layout.items() if isinstance(i, QgsLayoutItemLegend)]
assert len(maps) == 3 and len(legends) == 3
assert book.layout.pageCollection().pageCount() == 3
page = book.layout.pageCollection().page(0).pageSize()
assert (round(page.width()), round(page.height())) == (420, 297)
for legend in legends:
    model = legend.model()
    for node in model.rootGroup().findLayers():
        texts = [str(n.data(0)) for n in model.layerLegendNodes(node, True)]
        assert not any("Band 1" in text for text in texts), texts
pdf = export_pdf(book, sheets_file(RUN))
assert pdf.stat().st_size > 10_000
assert nice_segment(40.0) == 0.5  # 0.8 km wanted
assert nice_segment(120.0) == 2.0  # 2.4 km wanted
print("SHEETS PASSED", flush=True)
sys.stdout.flush()
os._exit(0)
