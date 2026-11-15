"""W85 step 2: where the deep standing water of a frame is, as connected patches.

    python s03_deep_water.py <waves_XX.XXh.npz> [depth m, default 20]

Reads what ``s01_frame_waves.py`` saved. A patch is cells joined by an edge whose level over the lowest pixel passes the
depth; for each: cells, the deepest, the mean depth of the deepest cell, the largest wave and the step it would give.
"""

from __future__ import annotations

import sys

import numpy as np
from scipy import ndimage

CFL = 0.45


def main() -> None:
    a = np.load(sys.argv[1])
    cut = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    d, h, plan = a["depth"], a["mean_depth"], a["plan"]
    w = np.maximum(a["wx"], a["wy"]) + a["speed"]
    x0, y0, dx = float(a["x0"]), float(a["y0"]), float(a["dx"])
    lab, n = ndimage.label(d > cut)
    print(f"{n} patches deeper than {cut} m, {(d > cut).sum()} cells")
    rows = []
    for m in range(1, n + 1):
        sel = lab == m
        k = np.argmax(np.where(sel, d, 0.0))
        j, i = np.unravel_index(k, d.shape)
        rows.append(
            (int(sel.sum()), float(d[j, i]), float(h[j, i]), float(plan[j, i]), float(w[sel].max()),
             x0 + (i + 0.5) * dx, y0 - (j + 0.5) * dx, float((h[sel]).sum() * dx * dx))
        )  # fmt: skip
    rows.sort(key=lambda r: -r[4])
    for cells, deep, mean, pl, wave, x, y, vol in rows[:25]:
        print(
            f"   ({x:.0f}, {y:.0f}) cells {cells:6d} deepest {deep:6.1f} m (mean depth there {mean:6.2f}, wet share {pl:.3f})"
            f"  volume {vol / 1e6:8.3f} Mm3  wave {wave:5.1f} m/s  step {CFL * dx / max(wave, 3.0):.3f} s"
        )


if __name__ == "__main__":
    main()
