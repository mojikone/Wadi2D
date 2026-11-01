"""Water against the closed edges of a Wadi2D run: every pond of connected edge-side cells, deepest first.

usage: edge_check.py RUN_FOLDER
"""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np
from scipy import ndimage

run = Path(sys.argv[1])
with h5py.File(run / "results.h5", "r") as f:
    print(dict(f.attrs).keys())
    x0, y0, dx = (float(f.attrs[k]) for k in ("x0", "y0", "dx"))
    d = f["maxima/depth"][:].astype(np.float64)
    keys = sorted(f["maps"], key=lambda k: float(f["maps"][k].attrs["t_s"]))
    last = f["maps"][keys[-1]]
    dend = last["depth"][:].astype(np.float64)
    hend = last["mean_depth"][:].astype(np.float64)
    tend = float(last.attrs["t_s"])
mask = np.isfinite(d) & (d > 0.0)
edge = mask & ~ndimage.binary_erosion(mask, border_value=0)
print("edge cells", int(edge.sum()), "of", int(mask.sum()))
for th in (0.5, 1.0, 2.0, 3.0):
    print(f"edge cells with max depth over {th} m:", int((d[edge] > th).sum()))
print(f"at t = {tend / 3600:.2f} h, stored in cells: {np.nansum(hend) * dx**2:.0f} m3")
deep = dend > 0.5
lab, n = ndimage.label(deep)
rows = []
for k in range(1, n + 1):
    c = lab == k
    touches = bool((c & edge).any())
    j, i = np.unravel_index(np.argmax(np.where(c, dend, -1.0)), dend.shape)
    rows.append((float(hend[c].sum() * dx**2), int(c.sum()), float(dend[j, i]), x0 + (i + 0.5) * dx, y0 - (j + 0.5) * dx, touches))
rows.sort(reverse=True)
print("volume m3, cells, deepest m, x, y, on an edge, at the end of the run:")
for r in rows[:15]:
    print(f"  {r[0]:9.0f} {r[1]:5d} {r[2]:6.2f} {r[3]:10.1f} {r[4]:11.1f} {r[5]}")
