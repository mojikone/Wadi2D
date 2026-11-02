"""Where to zoom: the densest H6 on the plain inside a 4 km window, spread along the coast. Writes video_hotspots.json."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

HERE = Path(__file__).resolve().parent
T = HERE / "terrain"
PLAIN_LEVEL = 150.0  # m; mountain wadis above this are H6 by speed alone
WINDOW_M = 4000.0
SPACING_M = 45000.0
COUNT = 4

with rasterio.open(T / "pixel_hazard_20m.tif") as s:
    cls = s.read(1)
    tr = s.transform
with rasterio.open(HERE / "runs" / "full_30m_200yr" / "maps" / "max_level.tif") as s:
    lvl = s.read(1, masked=True).filled(1e9)
    lt = s.transform
ys = tr.f + (np.arange(cls.shape[0]) + 0.5) * tr.e
xs = tr.c + (np.arange(cls.shape[1]) + 0.5) * tr.a
ri = np.clip(((ys - lt.f) / lt.e).astype(int), 0, lvl.shape[0] - 1)
ci = np.clip(((xs - lt.c) / lt.a).astype(int), 0, lvl.shape[1] - 1)
plain = lvl[np.ix_(ri, ci)] < PLAIN_LEVEL
density = ndimage.uniform_filter(((cls == 6) & plain).astype("float32"), size=int(WINDOW_M / 20.0))
chosen = []
work = density.copy()
work[np.ix_(ys > 2736000.0, xs < 442000.0)] = 0.0  # the Copernicus patch: no zoom on 30 m ground
for _ in range(COUNT):
    r, c = np.unravel_index(np.argmax(work), work.shape)
    x, y = float(xs[c]), float(ys[r])
    chosen.append({"x": x, "y": y, "h6_share": float(density[r, c]), "h6_km2_in_window": float(density[r, c] * (WINDOW_M / 1000) ** 2)})
    gap = int(SPACING_M / 20.0)
    work[max(r - gap, 0) : r + gap, max(c - gap, 0) : c + gap] = 0.0
chosen.sort(key=lambda h: h["x"])  # north-west to south-east along the coast
print(json.dumps(chosen, indent=1))
(HERE / "video_hotspots.json").write_text(json.dumps(chosen, indent=1), encoding="utf-8")
