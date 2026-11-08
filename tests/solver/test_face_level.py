"""The level a cell holds in steady uniform flow (W47, 2026-11-08).

A face reads its section at a depth. Read at the upwind cell's level over the face's own invert, the depth is taken
half a cell upstream of the face, so on a slope every cell holds its surface about half the bed's drop within the
cell too low and stores too little: 9 % of the water on Faydh's gorge at 20 m (W46). Here W3's channel at a slope of
1 % with 300 m3/s, where that reading is 0.1 m on a normal depth of 1.27 m, on the tile kernel and on the polygon
kernel laid over the same lattice: the depth at the axis within 1.5 % of the normal depth at 20 m.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import brentq

from wadi2d.config.schema import Numerics, Tables
from wadi2d.grid import TileGrid
from wadi2d.solver.backend import BoundaryCells
from wadi2d.solver.model import Model
from wadi2d.solver.poly.from_tiles import lattice_mesh, to_grid
from wadi2d.solver.poly.model import PolyModel
from wadi2d.solver.state import level_of
from wadi2d.tables import ArrayBed, build_tables
from wadi2d.tables.builder import hbar_at_level

SIDE, DX, K = 96, 20.0, 10
S, N, WALL = 0.01, 0.03, 5.0
B, BANK, Q = 60.0, 2.0, 300.0
T_END = 3000.0
RULE = 0.015


def normal_depth() -> float:
    """The Lotter sum across the section, as the sub-grid conveyance holds it: no wall friction."""
    return brentq(lambda y: (B * y ** (5 / 3) + 2 * BANK * (3 / 8) * y ** (8 / 3)) * S**0.5 / N - Q, 0.01, 20)


def channel():
    tg = TileGrid.from_mask(np.ones((SIDE, SIDE), bool), 0.0, 0.0, DX)
    ny, nx = tg.shape
    p = DX / K
    x = tg.x0 + (np.arange(nx * K) + 0.5) * p
    y = tg.y0 - (np.arange(ny * K) + 0.5) * p
    X, Y = np.meshgrid(x, y)
    xm, ym = 0.5 * SIDE * DX, -0.5 * SIDE * DX
    s, t = X - xm, Y - ym
    above = np.clip((np.abs(t) - B / 2) / BANK, 0.0, WALL)
    z = (100.0 - s * S + above).astype(np.float32).astype(np.float64)
    tables = build_tables(tg, ArrayBed(z, p), Tables(), N)
    jj, ii = np.mgrid[0:ny, 0:nx]
    cx, cy = tg.xy_of(jj, ii)
    return tg, tables, cx - xm, cy - ym


def depth_over_normal(which: str) -> float:
    tg, tables, sc, tc = channel()
    yn = normal_depth()
    hc, dtab = tg.from_tiles(tables.hc), tg.from_tiles(tables.dtab)
    level = 100.0 - sc * S + yn
    hb = hbar_at_level(level, tables.zmin, hc, dtab)
    hb = np.where((np.abs(tc) < B / 2 + BANK * yn + 2 * DX) & tg.mask, hb, 0.0)
    lim = 0.45 * SIDE * DX
    up = (sc > -lim) & (sc < -lim + 6 * DX) & (np.abs(tc) < B / 2 + DX) & tg.mask
    rate = np.where(up, Q / (up.sum() * DX * DX), 0.0)
    down = (sc > lim - 6 * DX) & (sc < lim) & (np.abs(tc) < B + 3 * DX) & tg.mask
    dj, di = np.nonzero(down)
    d0 = level_of(hb[down], hc[down], dtab[down])
    num = Numerics()
    if which == "tiles":
        model = Model(tables, num, "cpu")
        model.set_depth(hb)
        model.set_source(rate)
        cells = np.array([model.cell_state_index(int(j), int(i)) for j, i in zip(dj, di, strict=True)], np.int32)
        zero = np.zeros(cells.size, np.int32)
        model.set_boundary(BoundaryCells(cells, zero, zero.copy(), d0.astype(np.float32), hb[down].astype(np.float32)))
        model.advance(T_END)
        d = model.field("d").astype(np.float64)
    else:
        mesh, index = lattice_mesh(tables)
        model = PolyModel(mesh, num)
        model.set_depth(hb[index >= 0])
        model.set_source(rate[index >= 0])
        model.hold_cells(index[dj, di], level[down])
        model.advance(T_END)
        d = to_grid(index, model.d.astype(np.float64))
    mid = (np.abs(sc) < 0.15 * SIDE * DX) & (np.abs(tc) < 0.71 * DX) & tg.mask
    # the cell's level over the bed at its own centre, against the normal depth
    return float(np.mean((tables.zmin + d + sc * S - 100.0)[mid])) / yn


@pytest.mark.parametrize("which", ["tiles", "polygons"])
def test_steady_uniform_flow_holds_the_normal_depth_at_20_m(which: str) -> None:
    ratio = depth_over_normal(which)
    assert abs(ratio - 1.0) < RULE, f"{which}: depth {ratio:.4f} of the normal depth, the rule is {RULE:.1%}"
