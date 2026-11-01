"""Rotated channels on the production solver: normal depth against angle, width and bank slope."""
import sys
import warnings

warnings.simplefilter("ignore")
import numpy as np  # noqa: E402
from scipy.optimize import brentq  # noqa: E402

from wadi2d.config.schema import Numerics, Tables  # noqa: E402
from wadi2d.grid import TileGrid  # noqa: E402
from wadi2d.solver.backend import BoundaryCells  # noqa: E402
from wadi2d.solver.model import Model  # noqa: E402
from wadi2d.tables import ArrayBed, build_tables  # noqa: E402
from wadi2d.tables.builder import hbar_at_level  # noqa: E402

backend = "gpu"


def run(theta, b, bank, Q, dx=20.0, k=20, S=0.002, n=0.03, num=None, side=128):
    tg = TileGrid.from_mask(np.ones((side, side), bool), 0.0, 0.0, dx)
    ny, nx = tg.shape
    p = dx / k
    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    x = (np.arange(nx * k + 2) - 1 + 0.5) * p - 0.5 * nx * dx
    y = (np.arange(ny * k + 2) - 1 + 0.5) * p - 0.5 * ny * dx
    X, Y = np.meshgrid(x, y)
    s = X * ca + Y * sa
    t = -X * sa + Y * ca
    above = np.clip((np.abs(t) - b / 2) / max(bank, 1e-6), 0.0, 5.0) if bank > 0 else 5.0 * (np.abs(t) >= b / 2)
    z = -s * S + above

    def f(yn):
        area = (b + bank * yn) * yn
        per = b + 2 * yn * np.sqrt(1 + bank**2)
        return area * (area / per) ** (2 / 3) * S**0.5 / n - Q

    yn = brentq(f, 0.01, 20)
    tab = build_tables(tg, ArrayBed(z, p, 1, 1), Tables(), n)
    m = Model(tab, num or Numerics(), backend)
    xc = (np.arange(nx) + 0.5) * dx - 0.5 * nx * dx
    yc = (np.arange(ny) + 0.5) * dx - 0.5 * ny * dx
    Xc, Yc = np.meshgrid(xc, yc)
    sc = Xc * ca + Yc * sa
    tc = -Xc * sa + Yc * ca
    level = -sc * S + yn
    hb = hbar_at_level(level, tab.zmin, tg.from_tiles(tab.hc), tg.from_tiles(tab.dtab))
    # start from the normal state in the channel only
    hb = np.where(np.abs(tc) < b / 2 + bank * yn + 2 * dx, hb, 0.0)
    m.set_depth(hb)
    lim = 0.45 * side * dx
    up = (sc > -lim) & (sc < -lim + 120) & (np.abs(tc) < b / 2 + dx)
    rate = np.zeros(tg.shape)
    rate[up] = Q / (up.sum() * dx * dx)
    m.set_source(rate)
    down = (sc > lim - 120) & (sc < lim) & (np.abs(tc) < b + 3 * dx)
    cells = np.array([m.cell_state_index(int(j), int(i)) for j, i in zip(*np.nonzero(down), strict=True)], np.int32)
    n_b = cells.size
    dd = (level - tab.zmin)[down]
    m.set_boundary(
        BoundaryCells(
            cells, np.zeros(n_b, np.int32), np.zeros(n_b, np.int32),
            np.maximum(dd, 0).astype(np.float32), hb[down].astype(np.float32),
        )  # fmt: skip
    )
    m.advance(4000.0)
    mid = (np.abs(sc) < 0.15 * side * dx) & (np.abs(tc) < 0.71 * dx)
    eta = tab.zmin + m.field("d")
    dep = (eta + sc * S)[mid]
    r = np.mean(dep) / yn - 1.0
    print(f"theta {theta:3.0f} b {b:4.0f} bank {bank:.1f}:1 Q {Q:4.0f} dx {dx:.0f}: depth {np.mean(dep):.3f} normal {yn:.3f} error {r * 100:+.1f}%  steps {m.stepper.nsteps}", flush=True)
    return r


if __name__ == "__main__":
    for theta in (0, 30, 45):
        run(theta, 60.0, 0.0, 60.0)
        run(theta, 60.0, 2.0, 60.0)
    run(45, 120.0, 0.0, 150.0)
    run(45, 120.0, 2.0, 150.0)
    run(45, 30.0, 2.0, 20.0)
