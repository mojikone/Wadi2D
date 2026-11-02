"""Does water paint a dry freeboard? A straight channel of known surface, 45 m wide on 30 m cells, bank tops a set freeboard
above the true water surface. Flat level per cell against the guarded sloped surface. Any wet bank pixel is false."""

from __future__ import annotations

import warnings

warnings.simplefilter("ignore")
import cupy as cp  # noqa: E402
import numpy as np  # noqa: E402

import s06_pixel_hazard as hz  # noqa: E402

CELL, SCALE, PIX = 30.0, 6, 5.0
NX, NY = 40, 9
WIDTH = 45.0


def case(slope: float, freeboard: float, depth: float = 2.0) -> dict:
    nx, ny = NX * SCALE, NY * SCALE
    x = (np.arange(nx) + 0.5) * PIX
    y = (np.arange(ny) + 0.5) * PIX
    gx, gy = np.meshgrid(x, y)
    centre = NY * CELL / 2 + 7.5  # so the walls fall inside cells
    channel = np.abs(gy - centre) <= WIDTH / 2
    water = 100.0 - slope * gx
    ground = np.where(channel, water - depth, water + freeboard)
    # a cell's level is the mean water surface over its wet pixels
    level = np.full((NY, NX), np.nan)
    for j in range(NY):
        for i in range(NX):
            win = (slice(j * SCALE, (j + 1) * SCALE), slice(i * SCALE, (i + 1) * SCALE))
            if channel[win].any():
                level[j, i] = water[win][channel[win]].mean()
    wet = np.isfinite(level)
    flat = np.nan_to_num(np.kron(level, np.ones((SCALE, SCALE))), nan=-1e6)
    corners = hz.level_corners(cp.asarray(np.nan_to_num(level, nan=-1e6), cp.float32), cp.asarray(wet))
    basis = hz.corner_basis().reshape(SCALE, SCALE, 4)
    sloped = np.full((ny, nx), -1e6)
    c = [cp.asnumpy(a) for a in corners]
    for j in range(NY):
        for i in range(NX):
            if wet[j, i]:
                vals = np.array([a[j, i] for a in c])
                sloped[j * SCALE : (j + 1) * SCALE, i * SCALE : (i + 1) * SCALE] = basis @ vals
    inner = (gx > 3 * CELL) & (gx < (NX - 3) * CELL)
    bank = ~channel & inner
    row = {"slope": slope, "freeboard": freeboard}
    for name, surface in (("flat", flat), ("sloped", sloped)):
        deep = surface - ground
        row[f"false_bank_pixels_{name}_pct"] = round(float((deep[bank] >= hz.DEPTH_MIN).mean() * 100), 1)
        row[f"channel_surface_error_{name}_m"] = round(float(np.abs(surface - water)[channel & inner].max()), 2)
    return row


for s, f in ((0.01, 0.2), (0.05, 0.3), (0.05, 0.6), (0.05, 1.0), (0.10, 1.0), (0.10, 2.0)):
    print(case(s, f), flush=True)
