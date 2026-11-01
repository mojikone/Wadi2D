"""The lumped engine as the reference at any storm area (0.002 % of HMS on all 520 peaks, hms_replication.md)."""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import HMS, storm as storm_dict  # noqa: E402

from wadi2d.forcing import build_storm  # noqa: E402
from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.hms import load_basin  # noqa: E402
from wadi2d.hydrology.from_hms import basin_from_hms  # noqa: E402
from wadi2d.hydrology.model import TimeGrid  # noqa: E402
from wadi2d.hydrology.network import LumpedEngine  # noqa: E402

GRID = TimeGrid(5.0, 576)
ENGINE = LumpedEngine(basin_from_hms(load_basin(HMS / "Basin_1.basin")))
TIMES_H = GRID.minutes / 60.0


def run_at(area: float, met: str = "FM_100yr.met"):
    """Every element under the storm of this storm area."""
    cfg = RunConfig.model_validate({"storm": storm_dict(area, met)})
    return ENGINE.run(build_storm(cfg), GRID)


def stats(q: np.ndarray) -> dict[str, float]:
    return {"peak": float(q.max()), "t_h": float(TIMES_H[int(np.argmax(q))]),
            "vol_m3": float(np.trapezoid(q) * GRID.dt_seconds)}


def inflow_at(point: str, analysis_met: str) -> np.ndarray:
    """A depth-area inflow at a point, grid storms included, through the replication's own path."""
    from wadi2d.hydrology.depth_area import analyse_point
    from wadi2d.hydrology.replication import _point_storm, _Project

    proj = _Project(HMS / "HEC_HMS_Block_02.hms")
    hms_basin, engine = proj.model("Basin 1")
    fn = _point_storm(HMS / analysis_met, proj.tables, hms_basin, engine.basin, HMS / "Basin_1.basin",
                      "HEC_HMS_Block_02")
    return analyse_point(engine, fn, GRID, point).outflow
