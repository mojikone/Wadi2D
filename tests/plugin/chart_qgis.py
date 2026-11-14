# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""On QGIS's own Python: the right-click on the map opens an element's chart in the Result lines panel (W64).

Started by ``test_chart_qgis.py``. Arguments: a folder for the picture of the chart. The panel is the real one on a real
map canvas; its listing is written as ``wadi2d lines`` writes it, so no engine runs here (the listing itself is tested on a
real run in ``tests/engine/test_basin_run.py``). Prints ``CHART PASSED`` as its last line.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "plugin"))
OUT = Path(sys.argv[1])

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsTemporalNavigationObject,
    QgsVectorLayer,
)
from qgis.PyQt.QtGui import QFont  # noqa: E402

app = QgsApplication([], True)
app.initQgis()
app.setFont(QFont("Arial", 9))  # offscreen Qt otherwise mixes in a symbol font: the picture's words came out garbled

from qgis.gui import QgsMapCanvas, QgsMapMouseEvent  # noqa: E402
from qgis.PyQt.QtCore import QEvent, QPoint, Qt  # noqa: E402
from qgis.PyQt.QtWidgets import QMainWindow, QMenu  # noqa: E402
from wadi2d_qgis.protocol import LINES_LIST  # noqa: E402
from wadi2d_qgis.result_lines import ResultLinesPanel  # noqa: E402

CRS = "EPSG:32640"
X, Y = 500_500.0, 2_499_500.0
TIMES = [600.0 * k for k in range(13)]


class Iface:
    """What the panel asks of QGIS's interface."""

    def __init__(self) -> None:
        self.window = QMainWindow()
        self.canvas = QgsMapCanvas(self.window)
        self.window.setCentralWidget(self.canvas)
        self.navigation = QgsTemporalNavigationObject()  # QGIS's own window gives its canvas one
        self.canvas.setTemporalController(self.navigation)

    def mapCanvas(self):
        return self.canvas

    def mainWindow(self):
        return self.window

    def addDockWidget(self, area, dock):
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        self.window.removeDockWidget(dock)


def layer(kind: str, title: str, items: list[tuple[str, QgsGeometry]]) -> QgsVectorLayer:
    found = QgsVectorLayer(f"{kind}?crs={CRS}&field=name:string", title, "memory")
    features = []
    for name, geometry in items:
        feature = QgsFeature(found.fields())
        feature.setAttribute("name", name)
        feature.setGeometry(geometry)
        features.append(feature)
    found.dataProvider().addFeatures(features)
    QgsProject.instance().addMapLayer(found)
    return found


def hydrograph(peak: float) -> list[float]:
    return [peak * max(0.0, 1.0 - abs(k - 5) / 5.0) for k in range(13)]


project = QgsProject.instance()
project.setCrs(QgsCoordinateReferenceSystem(CRS))
square = QgsGeometry.fromRect(QgsRectangle(X - 400.0, Y - 400.0, X + 400.0, Y + 400.0))
layer("Polygon", "Subbasins, generated", [("S1", square)])
layer("Point", "Junctions, generated", [("Faydh 01", QgsGeometry.fromPointXY(QgsPointXY(X, Y)))])
layer("Point", "Somewhere else", [("Faydh 01", QgsGeometry.fromPointXY(QgsPointXY(X + 5000.0, Y)))])

iface = Iface()
iface.window.resize(1200, 900)
iface.window.show()
canvas = iface.canvas
canvas.setDestinationCrs(QgsCoordinateReferenceSystem(CRS))
canvas.setLayers(list(project.mapLayers().values()))
canvas.setExtent(QgsRectangle(X - 1000.0, Y - 1000.0, X + 1000.0, Y + 1000.0))
app.processEvents()

panel = ResultLinesPanel(iface, iface.window)
rain = [0.0, 6.0, 8.0, 4.0, 2.0] + [0.0] * 8
excess = [0.0, 0.5, 3.0, 2.5, 1.5] + [0.0] * 8
listing = {
    "crs": QgsCoordinateReferenceSystem(CRS).toWkt(),
    "frames_s": TIMES,
    "interval_s": 600.0,
    "lines": [],
    "points": [],
    "lumped": [
        {
            "name": "Faydh 01", "t_s": TIMES, "inflow_m3s": hydrograph(300.0), "outflow_m3s": hydrograph(180.0),
            "pool_m": [100.0 + 0.3 * k for k in range(13)], "rain_mm": rain, "excess_mm": excess,
            "element": {"kind": "reservoir", "drainage_area_km2": 74.3, "tc_minutes": 95.0, "lag_minutes": None},
        },
        {
            "name": "S1", "t_s": TIMES, "inflow_m3s": [0.0] * 13, "outflow_m3s": hydrograph(120.0),
            "rain_mm": rain, "excess_mm": excess,
            "element": {"kind": "subbasin", "drainage_area_km2": 20.0, "tc_minutes": 60.0, "lag_minutes": 36.0},
        },
    ],
    "observed": [],
}  # fmt: skip
Path(panel._file(LINES_LIST)).write_text(json.dumps(listing), encoding="utf-8")
panel._listed()
assert panel.choice.count() == 2, panel.choice.count()


def right_click(x: float, y: float) -> QMenu:
    pixel = canvas.getCoordinateTransform().transform(QgsPointXY(x, y))
    event = QgsMapMouseEvent(canvas, QEvent.MouseButtonPress, QPoint(round(pixel.x()), round(pixel.y())), Qt.RightButton)
    menu = QMenu()
    canvas.contextMenuAboutToShow.emit(menu, event)
    return menu


# on the junction: the junction first, then the subbasin it sits in; the far feature of the same name is not under it
menu = right_click(X, Y)
texts = [action.text() for action in menu.actions()]
assert texts == ["Hydrograph: Lumped element: Faydh 01", "Hydrograph: Lumped element: S1"], texts
menu.actions()[0].trigger()
assert panel.choice.currentText() == "Lumped element: Faydh 01", panel.choice.currentText()
view = panel.plot.view
assert view.heading == "Reservoir: Faydh 01.", view.heading
assert view.charts[0].bars is not None and view.charts[0].right, view.charts[0]
assert "tc 95 min" in view.note and "centroid of excess to peak" in view.note, view.note

# inside the subbasin, away from the junction: the subbasin alone
menu = right_click(X + 300.0, Y - 300.0)
texts = [action.text() for action in menu.actions()]
assert texts == ["Hydrograph: Lumped element: S1"], texts
menu.actions()[0].trigger()
assert panel.plot.view.heading == "Subbasin: S1.", panel.plot.view.heading

# off every element: nothing added to QGIS's own menu
assert [a.text() for a in right_click(X + 900.0, Y + 900.0).actions()] == []

# the chart paints: each of the two, saved as a picture for the record
OUT.mkdir(parents=True, exist_ok=True)
panel.plot.resize(1000, 460)
for index, name in enumerate(("reservoir", "subbasin")):
    panel.show_entry(index)
    panel._set_frame(6)
    picture = panel.plot.grab()
    assert not picture.isNull()
    assert picture.save(str(OUT / f"chart_{name}.png")), OUT

panel.release()
print("CHART PASSED", flush=True)
sys.stdout.flush()
os._exit(0)
