"""Where nearest gauge and inverse distance part on the dock check's two gauges: rain along a west-east transect.

The gauges of dock_gauges.py: West (433000, 2725500) 40 mm, East (438500, 2725500) 10 mm, the bisector at x 435,750.
Rain at points on the gauges' row and 2 km north of it, as the run gives a cell centred there.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from wadi2d.hydrology.gauge_rain import GaugeCellRain
from wadi2d.storm.gauges import GaugeStorm

xy = np.array([[433000.0, 2725500.0], [438500.0, 2725500.0]])
x = np.arange(431000.0, 440001.0, 1000.0)
out = {"x_m": x.tolist()}
for method in ("thiessen", "inverse_distance"):
    storm = GaugeStorm(("West", "East"), xy, np.array([0.0, 60.0]), np.array([[0.0, 0.0], [40.0, 10.0]]), method=method)
    for dy in (0.0, 2000.0):
        y = np.full(x.size, 2725500.0 + dy)
        cells = GaugeCellRain(storm, x, y, np.full(x.size, np.nan), np.ones(x.size, bool))
        out[f"{method}_mm_row_plus_{dy:g}m"] = np.round(cells.rain_mm(60.0)[cells.pair_of], 2).tolist()
Path(__file__).with_name("transect.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
for key, values in out.items():
    print(f"{key:32s}", " ".join(f"{v:7.1f}" if key != "x_m" else f"{v/1000:7.0f}" for v in values))
