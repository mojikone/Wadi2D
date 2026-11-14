"""How the rain differs, per dam: the subbasins' spread of the grid depth, and the time pattern of the FM PMP storm
against the grid's catchment pattern (share of the depth in the wettest 1 h and 6 h). Writes results/rain_shape.json."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from wadi2d.hms.sqlite import subbasin_polygons
from wadi2d.hydrology.replication import _Project
from wadi2d.io.rain import read_rain
from wadi2d.storm.gridded import GriddedStorm
from wadi2d.storm.rain_frames import RainSpec

HERE = Path(__file__).resolve().parents[1]
HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\HEC_HMS_Block_02.hms")
GRID = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Grid\DSS\Precipitation_PMP_10min.dss")


def wettest(cumulative: np.ndarray, steps: int) -> float:
    return float((cumulative[steps:] - cumulative[:-steps]).max() / cumulative[-1])


project = _Project(HMS)
hms_basin, engine = project.model("Basin 3")
crs = hms_basin.spatial.coordinate_system if hms_basin.spatial is not None else ""
shapes = {p.name: p.shape() for p in subbasin_polygons(HMS.parent / "Basin_3.sqlite")}
storm = GriddedStorm(read_rain(GRID, RainSpec(), start="2000-01-01T00:00:00")).bind(shapes, crs)
inputs = json.loads((HERE / "results" / "pmf_inputs.json").read_text(encoding="utf-8"))
fm = project.tables.patterns["FM PMP"]
minutes = np.arange(0.0, 1440.0 + 1e-9, 10.0)
fm_cumulative = fm.fraction(minutes / 1440.0)
out = {"fm_pmp_pattern": {"wettest_1h": wettest(fm_cumulative, 6), "wettest_6h": wettest(fm_cumulative, 36)}}
for dam, row in inputs.items():
    depths = {name: float(storm.over(name).total_depth) for name in row["subbasins"]}
    cumulative = np.asarray(row["pattern_depth_percent"])
    out[dam] = {
        "subbasin_depth_min_mm": min(depths.values()), "subbasin_depth_max_mm": max(depths.values()),
        "grid_wettest_1h": wettest(cumulative, 6), "grid_wettest_6h": wettest(cumulative, 36),
    }
    print(dam, out[dam])
print("FM PMP", out["fm_pmp_pattern"])
(HERE / "results" / "rain_shape.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
