"""Normal depth in a straight rectangular flume by Wadi2D's own face tables, strips against local radius (W49).

A measured run (width b, bed slope S0, discharge Q, depth h, Manning n) is scaled by Froude similarity to a channel
WIDTH_M wide: lengths by L = WIDTH_M / b, discharge by L^2.5, n by L^(1/6). Manning-law flow is exactly invariant
under that scaling, so the depth ratio h_model / h_measured carries back unchanged, and the channel can sit on a
0.25 m DEM with the walls resolved. The scaled channel is built as pixels (a flat bed WIDTH_M wide, vertical walls
WALL_M high), the engine's table builder makes its faces, and the x faces of one column are summed: the conveyance
the section carries, at any cell size. Normal depth solves K(h) S0^0.5 = Q. Also given: Manning on the whole
section's hydraulic radius (walls in the perimeter) and on plan width (R = h, the strips limit).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from wadi2d.config.schema import Tables
from wadi2d.grid import TileGrid
from wadi2d.solver.cpu.kernels import face_lookup
from wadi2d.tables import ArrayBed, build_tables

WIDTH_M = 12.0
PIXEL = 0.25
WALL_M = 40.0
SIDE_M = 40.0
"""Ground beside the channel, each side, above the walls' top: dry, so the window sees the walls and no more."""
LENGTH_M = 48.0


def bed(b: float = WIDTH_M) -> np.ndarray:
    ny = int(round((b + 2 * SIDE_M) / PIXEL))
    nx = int(round(LENGTH_M / PIXEL))
    y = (np.arange(ny) + 0.5) * PIXEL - 0.5 * ny * PIXEL
    z = np.where(np.abs(y) < 0.5 * b, 0.0, WALL_M)
    return np.broadcast_to(z[:, None], (ny, nx)).astype(np.float64).copy()


def column_k(dx: float, mode: str, n: float, beta: float = 9.0):
    """K(depth) of the x faces of the middle column, a closure over the built tables. Level is over the flat bed."""
    k = round(dx / PIXEL)
    z = bed()
    ny, nx = z.shape[0] // k, z.shape[1] // k
    tg = TileGrid.from_mask(np.ones((ny, nx), bool), 0.0, 0.0, dx)
    cfg = Tables(face_conveyance=mode, local_radius_beta=beta, face_depth_max=48.0, face_depth_min=8.0)
    tab = build_tables(tg, ArrayBed(z[: ny * k, : nx * k], PIXEL, row_offset=-k, col_offset=-k), cfg, n)
    i = nx // 2 + 1
    ftab, ef, fl = (tg.from_tiles(a) for a in (tab.ftabx, tab.efx, tab.flx))
    rows = ftab.shape[-2]

    def k_of(h: float) -> float:
        total = 0.0
        for jj in range(1, ny + 1):
            zf = fl[jj, i] + tab.zmin[jj, i - 1]
            e = h - zf
            if e <= 0.0:
                continue
            _a, t, _w = face_lookup(np.float32(e), np.float32(ef[jj, i]), ftab[jj, i].reshape(-1).astype(np.float32), rows)
            total += float(t) ** (5.0 / 3.0)
        return total

    return k_of


def manning_depth(b: float, q: float, s0: float, n: float, walls: bool) -> float:
    def f(h: float) -> float:
        r = b * h / (b + 2 * h) if walls else h
        return b * h * r ** (2 / 3) * s0**0.5 / n - q

    return brentq(f, 1e-6, 1e3)


def model_depths(b: float, q: float, s0: float, n: float, cells=(12.0, 4.0, 1.0), beta: float = 9.0) -> dict:
    """Depths for one run, in the run's own units, from the scaled channel."""
    lam = WIDTH_M / b
    qs, ns = q * lam**2.5, n * lam ** (1 / 6)
    out = {"manning_R": manning_depth(b, q, s0, n, True), "manning_plan": manning_depth(b, q, s0, n, False)}
    for mode in ("strips", "local_radius"):
        for dx in cells:
            kk = column_k(dx, mode, ns, beta)
            hs = brentq(lambda h: kk(h) * s0**0.5 - qs, 1e-3, WALL_M - 1.0, xtol=1e-5)
            out[f"{mode}_{dx:g}"] = hs / lam
    return out


if __name__ == "__main__":
    # a self-check before any data: b/h from 1 to 10 in a 0.3 m flume, S0 0.001, n 0.01
    b, s0, n = 0.3, 1e-3, 0.01
    for h in (0.3, 0.1, 0.03):
        r = b * h / (b + 2 * h)
        q = b * h * r ** (2 / 3) * s0**0.5 / n
        d = model_depths(b, q, s0, n)
        print(f"b/h {b / h:5.1f}  Q {q * 1000:7.3f} l/s  " + "  ".join(f"{k} {v / h:.4f}" for k, v in d.items()))
