"""The head-to-head case, one source of truth for both models. Coordinates are in the DEM CRS (EPSG:32640)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DEM = HERE / "terrain" / "fan_window_0p5m.tif"

# West and north edges of the mesh: DEM pixel corners nearest to 437,000 E and 2,729,000 N.
X0 = 436999.98973783385
Y0 = 2728999.893463373
SIDE = 3000.0
MANNING = 0.04
SLOPE_OUT = 0.015  # energy slope of the normal-depth edges; the bed falls about 1.6 % across the window
SLOPE_IN = 0.015
DURATION_H = 6

# The hydrograph: 5 m3/s base, rising to 300 m3/s at 1.5 h, back to base at 5 h, tabulated every 15 min.
Q_BASE, Q_PEAK, T_PEAK_H, T_END_H = 5.0, 300.0, 1.5, 5.0
DT_TABLE_MIN = 15

# West-edge inflow line, on the perimeter (the wadi crosses it here; first-run map).
INFLOW_Y = (Y0 - 2750.0, Y0 - 2250.0)
# Reference sections: lattice x-lines, offset from the west edge, spanning these y ranges (m below Y0).
SECTIONS = {
    "X1000": (1000.0, 1100.0, 3000.0),
    "X2000": (2000.0, 0.0, 2200.0),
    "X2800": (2800.0, 0.0, 2200.0),
}


def hydrograph() -> tuple[np.ndarray, np.ndarray]:
    """Times in seconds, flows in m3/s."""
    n = int(DURATION_H * 60 / DT_TABLE_MIN) + 1
    t = np.arange(n) * DT_TABLE_MIN * 60.0
    h = t / 3600.0
    q = np.interp(h, [0.0, T_PEAK_H, T_END_H, DURATION_H], [Q_BASE, Q_PEAK, Q_BASE, Q_BASE])
    return t, q
