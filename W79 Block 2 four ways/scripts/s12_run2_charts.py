"""run2_charts/: run 2's hydrographs drawn by the plugin's own element chart (W64/W74), headless, as PNG.

Run with ``"C:\\Program Files\\QGIS 3.44.8\\bin\\python-qgis-ltr.bat" s12_run2_charts.py``. The chart is the Result lines
panel's (``wadi2d_qgis.line_plot.LinePlot`` showing ``element_view``): the rain per step hung from the top (rain and
excess), the outflow and inflow below, a reservoir's pool level on the right axis, the header with the element's area.
The series are run 2's own (``series/network_<element>.csv``, each element at its own ARF area).
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent / "plugin"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

from qgis.core import QgsApplication  # noqa: E402
from qgis.PyQt.QtGui import QFont  # noqa: E402

app = QgsApplication([], True)
app.initQgis()
app.setFont(QFont("Arial", 9))  # offscreen Qt otherwise mixes in a symbol font (W64)

from w79 import RUN_NAMES, RUNS  # noqa: E402
from wadi2d_qgis.element_view import element_view  # noqa: E402
from wadi2d_qgis.line_plot import LinePlot  # noqa: E402
from wadi2d_qgis.line_view import LUMPED, Entry  # noqa: E402

FOLDER = RUNS / RUN_NAMES[2]
OUT = HERE / "run2_charts"
ELEMENTS = [
    "Bidah 03 Reservoir", "Faydh 01 Reservoir", "R5A Reservoir", "R2A Reservoir", "Z4C Reservoir",
    "FAY-J5", "RIJ-J21", "S13", "S3", "HAT-S8",
]  # fmt: skip
"""The five reservoirs; the two largest junctions (Wadi Faydh's 428.8 km2, Wadi Rijm's 334.6 km2); Bidah 03's own
subbasin and the two largest subbasins."""


def series(name: str) -> dict:
    path = FOLDER / "series" / f"network_{name.replace(' ', '_')}.csv"
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {key: [float(r[key]) for r in rows] for key in rows[0]}


def main() -> None:
    with (FOLDER / "network_peaks.csv").open(encoding="utf-8") as f:
        peaks = {r["element"]: r for r in csv.DictReader(f)}
    OUT.mkdir(exist_ok=True)
    plot = LinePlot()
    plot.resize(1100, 520)
    for name in ELEMENTS:
        row = peaks[name]
        record = series(name)
        area, arf = float(row["storm_area_km2"]), float(row["arf"])
        record["element"] = {"kind": row["kind"].lower(), "drainage_area_km2": area, "tc_minutes": None,
                             "lag_minutes": None}
        entry = Entry(LUMPED, f"{name} (run 2, Lumped: ARF {arf:.4f} at its own {area:,.2f} km2)", record=record)
        plot.show_view(element_view(entry, []), 0)
        picture = plot.grab()
        assert not picture.isNull(), name
        path = OUT / f"{name.replace(' ', '_')}.png"
        assert picture.save(str(path)), path
        print("wrote", path.name)
    print("CHARTS DONE", flush=True)
    os._exit(0)


main()
