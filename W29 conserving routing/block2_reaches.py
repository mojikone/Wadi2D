"""Both schemes on Block 2's eight reaches with HMS's own inflows, and on the W25 short floods. Reads the project;
writes ``block2_reaches.json`` and prints the README tables.

    .venv\\Scripts\\python "W29 conserving routing\\block2_reaches.py"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import numpy as np  # noqa: E402

from wadi2d.config.schema import REACH_CONSERVING, REACH_HMS  # noqa: E402
from wadi2d.hms import daa_fpart, load_basin, open_dss  # noqa: E402
from wadi2d.hydrology.from_hms import basin_from_hms  # noqa: E402
from wadi2d.hydrology.routing import MuskingumCunge  # noqa: E402

FOLDER = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")
ANALYSIS = "DA 100yr B1"
STEP_MIN = 5.0
TAIL_HOURS = 160.0
REACHES = [f"R{n}" for n in range(1, 9)]
TEST_REACH = MuskingumCunge(3000.0, 0.01, 0.04, 10.0, 1.0, 2.0)


def volume(q: np.ndarray, dt_min: float) -> float:
    return float(np.trapezoid(q)) * dt_min * 60.0


def drained_at(q: np.ndarray, dt_min: float, cut: float = 1e-6) -> float:
    """Hours until the outflow stays below ``cut`` after its peak; the tail's length as the drain sees it."""
    k = int(np.argmax(q))
    below = np.flatnonzero(np.r_[q, 0.0][k:] < cut)
    return (k + int(below[0])) * dt_min / 60.0


def both(faithful: MuskingumCunge, inflow: np.ndarray, dt_min: float) -> dict:
    conserving = MuskingumCunge(**{**faithful.__dict__, "scheme": REACH_CONSERVING})
    hms = faithful.route(inflow, dt_min)
    con, storage = conserving.route_conserving(inflow, dt_min)
    entered = volume(inflow, dt_min)
    return {
        "inflow_peak": round(float(inflow.max()), 1),
        "inflow_at_h": round(float(np.argmax(inflow)) * dt_min / 60.0, 2),
        "hms_peak": round(float(hms.max()), 1),
        "hms_at_h": round(float(np.argmax(hms)) * dt_min / 60.0, 2),
        "hms_out_in": round(volume(hms, dt_min) / entered, 5),
        "conserving_peak": round(float(con.max()), 1),
        "conserving_at_h": round(float(np.argmax(con)) * dt_min / 60.0, 2),
        "conserving_out_in": round(volume(con, dt_min) / entered, 7),
        "identity_m3": float(entered - volume(con, dt_min) - storage),
        "conserving_min": float(con.min()),
        "conserving_drained_h": round(drained_at(con, dt_min), 1),
        "cells": faithful.grid(dt_min * 60.0)[0],
    }


def triangle(peak: float, dt_min: float, base_min: float = 20.0) -> np.ndarray:
    t = np.arange(int(TAIL_HOURS * 60.0 / dt_min) + 1) * dt_min
    return np.interp(t, [0.0, 0.5 * base_min, base_min], [0.0, peak, 0.0])


def main() -> None:
    basin = basin_from_hms(load_basin(FOLDER / "Basin_1.basin"), reach_routing=REACH_HMS)
    tail = np.zeros(int(TAIL_HOURS * 60.0 / STEP_MIN))
    rows = {}
    with open_dss(FOLDER / "DA_100yr_B1.dss") as dss:
        for name in REACHES:
            inflow = dss.read_timeseries(name, "FLOW-COMBINE", daa_fpart(ANALYSIS, name)).values
            rows[name] = both(basin.elements[name].routing, np.r_[0.0, inflow, tail], STEP_MIN)
    short = {}
    for label, reach, dt_min in (("Block 2 R1", basin.elements["R1"].routing, 5.0),
                                 ("Block 2 R6", basin.elements["R6"].routing, 5.0),
                                 ("test reach 3 km", TEST_REACH, 1.0)):  # fmt: skip
        for peak in (8.0, 80.0, 800.0):
            short[f"{label} peak {peak:g} dt {dt_min:g} min"] = both(reach, triangle(peak, dt_min), dt_min)
    (HERE / "block2_reaches.json").write_text(json.dumps({"hms_inflows": rows, "short_floods": short}, indent=1), encoding="utf-8")

    print("| Reach | Cells | Inflow peak, m3/s at h | HMS peak at h | HMS out/in | Conserving peak at h | Conserving out/in | Identity, m3 | Drained, h |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, r in rows.items():
        print(f"| {name} | {r['cells']} | {r['inflow_peak']} at {r['inflow_at_h']} | {r['hms_peak']} at {r['hms_at_h']} | {r['hms_out_in']:.4f} "
              f"| {r['conserving_peak']} at {r['conserving_at_h']} | {r['conserving_out_in']:.6f} | {r['identity_m3']:.1e} | {r['conserving_drained_h']} |")
    print()
    print("| Flood | HMS peak at h | HMS out/in | Conserving peak at h | Conserving out/in | Lowest ordinate, m3/s | Drained, h |")
    print("|---|---|---|---|---|---|---|")
    for name, r in short.items():
        print(f"| {name} | {r['hms_peak']} at {r['hms_at_h']} | {r['hms_out_in']:.3f} | {r['conserving_peak']} at {r['conserving_at_h']} "
              f"| {r['conserving_out_in']:.6f} | {r['conserving_min']:.3g} | {r['conserving_drained_h']} |")


if __name__ == "__main__":
    main()
