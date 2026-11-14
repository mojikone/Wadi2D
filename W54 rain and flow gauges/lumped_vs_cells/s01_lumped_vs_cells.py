"""Each Block 2 subbasin run lumped takes the rain its cells take as rain-on-grid: the check W20 made for gridded rain.

Three synthetic gauges across Block 2, each with its own depth. For every subbasin of the project's HMS basin, the
lumped areal mean (``GaugeStorm.over``: exact Thiessen area shares, or inverse distance averaged over points inside
the polygon) against the mean of the 30 m and 10 m cells whose centres fall inside the polygon, as the forcing gives
them rain. Read only: the basin's sqlite is opened immutable.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import shapely

from wadi2d.hms import sqlite as hms_sqlite
from wadi2d.hydrology.gauge_rain import GaugeCellRain
from wadi2d.storm.gauges import GaugeStorm

HERE = Path(__file__).resolve().parent
SQLITE = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\Basin_1.sqlite")
GAUGES = np.array([[420000.0, 2715000.0], [432000.0, 2728000.0], [438000.0, 2712000.0]])
TOTALS = np.array([80.0, 160.0, 40.0])
"""mm over one hour, so a subbasin's depth tells at once how it shares its gauges."""


def storm(method: str) -> GaugeStorm:
    edges = np.array([0.0, 60.0])
    cumulative = np.vstack((np.zeros(3), TOTALS))
    return GaugeStorm(("A", "B", "C"), GAUGES, edges, cumulative, method=method, samples=20000)


polygons = {row.name: row.shape() for row in hms_sqlite.subbasin_polygons(SQLITE)}
report = {}
for method in ("thiessen", "inverse_distance"):
    rain = storm(method).bind(polygons, "", "")
    rows = {}
    for dx in (30.0, 10.0):
        for name, polygon in sorted(polygons.items()):
            west, south, east, north = shapely.bounds(polygon)
            gx, gy = np.meshgrid(np.arange(west, east, dx) + dx / 2, np.arange(south, north, dx) + dx / 2)
            inside = shapely.contains_xy(polygon, gx.ravel(), gy.ravel())
            x, y = gx.ravel()[inside], gy.ravel()[inside]
            cells = GaugeCellRain(rain, x, y, np.full(x.size, np.nan), np.ones(x.size, bool))
            cell_mean = float(cells.rain_mm(60.0)[cells.pair_of].mean())
            lumped = rain.over(name).total_depth
            rows.setdefault(name, {"area_km2": round(polygon.area / 1e6, 3), "lumped_mm": round(lumped, 4)})
            rows[name][f"cells_{dx:g}m_mm"] = round(cell_mean, 4)
            rows[name][f"diff_{dx:g}m_percent"] = round(100.0 * (cell_mean - lumped) / lumped, 4)
    worst = {f"{dx:g}m": max(abs(r[f"diff_{dx:g}m_percent"]) for r in rows.values()) for dx in (30.0, 10.0)}
    report[method] = {"worst_percent": worst, "subbasins": rows}
    print(method, worst)
(HERE / "lumped_vs_cells.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
