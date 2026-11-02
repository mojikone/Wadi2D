"""The dry-face fix on the production GPU engine: rotated channels, fix off and on, over lateral position.

Pass mark carried from W3: normal-depth error within 3 % at 3 cells wide, 45 degrees, vertical walls. W3's reference is
Manning with the wetted perimeter, and so is this. Writes channel_gpu.json.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

warnings.simplefilter("ignore")
import numpy as np  # noqa: E402
from scipy.optimize import brentq  # noqa: E402

from wadi2d.config.schema import Numerics, Tables  # noqa: E402
from wadi2d.grid import TileGrid  # noqa: E402
from wadi2d.solver.backend import BoundaryCells  # noqa: E402
from wadi2d.solver.model import Model  # noqa: E402
from wadi2d.tables import ArrayBed, build_tables  # noqa: E402
from wadi2d.tables.builder import hbar_at_level  # noqa: E402

HERE = Path(__file__).resolve().parent
OFFSETS = (0.0, 2.5, 5.0, 7.5, 10.0, 12.5, 15.0, 17.5)


def run(theta, b, bank, Q, offset, mirror, dx=20.0, k=20, S=0.002, n=0.03, side=128):
    tg = TileGrid.from_mask(np.ones((side, side), bool), 0.0, 0.0, dx)
    ny, nx = tg.shape
    p = dx / k
    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    x = (np.arange(nx * k + 2) - 1 + 0.5) * p - 0.5 * nx * dx
    y = (np.arange(ny * k + 2) - 1 + 0.5) * p - 0.5 * ny * dx
    X, Y = np.meshgrid(x, y)
    s = X * ca + Y * sa
    t = -X * sa + Y * ca - offset
    above = np.clip((np.abs(t) - b / 2) / max(bank, 1e-6), 0.0, 5.0) if bank > 0 else 5.0 * (np.abs(t) >= b / 2)
    z = -s * S + above

    def f(yn):
        area = (b + bank * yn) * yn
        per = b + 2 * yn * np.sqrt(1 + bank**2)
        return area * (area / per) ** (2 / 3) * S**0.5 / n - Q

    yn = brentq(f, 0.01, 20)
    tab = build_tables(tg, ArrayBed(z, p, 1, 1), Tables(), n)
    m = Model(tab, Numerics(mirror_dry_faces=mirror), "gpu")
    xc = (np.arange(nx) + 0.5) * dx - 0.5 * nx * dx
    yc = (np.arange(ny) + 0.5) * dx - 0.5 * ny * dx
    Xc, Yc = np.meshgrid(xc, yc)
    sc = Xc * ca + Yc * sa
    tc = -Xc * sa + Yc * ca - offset
    level = -sc * S + yn
    hb = hbar_at_level(level, tab.zmin, tg.from_tiles(tab.hc), tg.from_tiles(tab.dtab))
    hb = np.where(np.abs(tc) < b / 2 + bank * yn + 2 * dx, hb, 0.0)
    m.set_depth(hb)
    lim = 0.45 * side * dx * (1.0 if theta == 0 else 1.0)
    if theta == 0:
        lim = 0.4 * side * dx
    up = (sc > -lim) & (sc < -lim + 120) & (np.abs(tc) < b / 2 + dx)
    rate = np.zeros(tg.shape)
    rate[up] = Q / (up.sum() * dx * dx)
    m.set_source(rate)
    down = (sc > lim - 120) & (sc < lim) & (np.abs(tc) < b + 3 * dx)
    cells = np.array([m.cell_state_index(int(j), int(i)) for j, i in zip(*np.nonzero(down), strict=True)], np.int32)
    n_b = cells.size
    dd = (level - tab.zmin)[down]
    m.set_boundary(BoundaryCells(cells, np.zeros(n_b, np.int32), np.zeros(n_b, np.int32), np.maximum(dd, 0).astype(np.float32), hb[down].astype(np.float32)))
    m.advance(4000.0)
    mid = (np.abs(sc) < 0.15 * side * dx) & (np.abs(tc) < 0.71 * dx)
    eta = tab.zmin + m.field("d")
    return float(np.mean((eta + sc * S)[mid]) / yn - 1.0) * 100.0


rows = []
for theta, b, bank, Q, label in ((45, 60.0, 0.0, 60.0, "45 deg vertical 3 cells"), (45, 120.0, 0.0, 150.0, "45 deg vertical 6 cells"), (30, 60.0, 0.0, 60.0, "30 deg vertical 3 cells"), (45, 60.0, 2.0, 60.0, "45 deg 2:1 banks 3 cells")):
    for mirror in (False, True):
        e = [run(theta, b, bank, Q, o, mirror) for o in OFFSETS]
        rows.append({"case": label, "fix": mirror, "by_offset": [round(v, 2) for v in e], "min": round(min(e), 2), "max": round(max(e), 2), "mean": round(float(np.mean(e)), 2)})
        print(rows[-1], flush=True)
(HERE / "channel_gpu.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
