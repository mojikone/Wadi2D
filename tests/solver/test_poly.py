"""The polygon kernel on the lattice itself (W45, stage 1): still water exact, and W3's rotated channel within the rule.

The channel is W3's (`W3 breakline faces test/cases.py`): a bed falling 0.2 % along the axis, 2:1 banks, walls 5 m
high beyond, 60 m3/s on a 60 m bed, normal depth by Manning. The tables come from the engine's own builder, the same
objects for the tile model and the polygon model, so a difference is the kernel's alone.
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
S, N, WALL = 0.002, 0.03, 5.0
B, BANK, Q = 60.0, 2.0, 60.0
"""Bed width, side slope (horizontal per vertical), discharge: W3's three-cell case."""
T_END = 3000.0
RULE = 0.03
"""W3's rule: the depth at the axis within 3 % of the normal depth."""


def normal_depth_wide(b: float, bank: float, q: float) -> float:
    """What a sub-grid strip conveyance holds: no wall friction, the Lotter sum across the section (W3)."""

    def f(y):
        conv = b * y ** (5 / 3)
        if bank > 0:
            conv += 2 * bank * (3 / 8) * y ** (8 / 3)
        return conv * S**0.5 / N - q

    return brentq(f, 0.01, 20)


def channel(theta: float):
    """The grid, its tables, and the along and across coordinates of every cell centre."""
    tg = TileGrid.from_mask(np.ones((SIDE, SIDE), bool), 0.0, 0.0, DX)
    ny, nx = tg.shape
    p = DX / K
    x = tg.x0 + (np.arange(nx * K) + 0.5) * p
    y = tg.y0 - (np.arange(ny * K) + 0.5) * p
    X, Y = np.meshgrid(x, y)
    xm, ym = 0.5 * SIDE * DX, -0.5 * SIDE * DX  # the centre of the active square, not of the padded grid
    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    s = (X - xm) * ca + (Y - ym) * sa
    t = -(X - xm) * sa + (Y - ym) * ca
    above = np.clip((np.abs(t) - B / 2) / BANK, 0.0, WALL)
    z = (100.0 - s * S + above).astype(np.float32).astype(np.float64)
    bed = ArrayBed(z, p)
    tables = build_tables(tg, bed, Tables(), N)
    jj, ii = np.mgrid[0:ny, 0:nx]
    cx, cy = tg.xy_of(jj, ii)
    sc = (cx - xm) * ca + (cy - ym) * sa
    tc = -(cx - xm) * sa + (cy - ym) * ca
    return tg, tables, sc, tc


def still(theta: float, level: float):
    """Still water for 600 s on both kernels: the polygon model, its volume at the start, and the tile kernel's
    largest speed on the same tables, the float32 noise a level near 100 m leaves on a sloping bed."""
    tg, tables, _sc, _tc = channel(theta)
    mesh, index = lattice_mesh(tables)
    hb = hbar_at_level(level, tables.zmin, tg.from_tiles(tables.hc), tg.from_tiles(tables.dtab)) * tg.mask
    poly = PolyModel(mesh, Numerics(dt_every=1))
    poly.set_depth(hb[index >= 0])
    v0 = poly.volume()
    poly.advance(600.0)
    tiles = Model(tables, Numerics(dt_every=1), "cpu")
    tiles.set_depth(hb)
    tiles.advance(600.0)
    noise = max(float(np.abs(tiles.field("u")).max()), float(np.abs(tiles.field("v")).max()))
    return poly, v0, noise


@pytest.mark.parametrize("theta", [0.0, 30.0])
def test_still_water_on_the_lattice_as_polygons_stays_as_still_as_on_tiles(theta: float) -> None:
    poly, v0, noise = still(theta, 101.0)
    speed = float(np.abs(poly.u).max())
    assert speed < 2e-5, (speed, noise)
    assert speed <= 3.0 * max(noise, 1e-6), (speed, noise)
    assert poly.volume() == pytest.approx(v0, rel=1e-7)  # float32 state: the engine's books close to about 1e-8


def run_channel(theta: float, which: str):
    """The depth at the axis after T_END, over the normal depth; and the model."""
    tg, tables, sc, tc = channel(theta)
    yn = normal_depth_wide(B, BANK, Q)
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
        steps = model.stepper.nsteps
    else:
        mesh, index = lattice_mesh(tables)
        model = PolyModel(mesh, num)
        model.set_depth(hb[index >= 0])
        model.set_source(rate[index >= 0])
        model.hold_cells(index[dj, di], level[down])
        model.advance(T_END)
        d = to_grid(index, model.d.astype(np.float64))
        steps = model.nsteps
    mid = (np.abs(sc) < 0.15 * SIDE * DX) & (np.abs(tc) < 0.71 * DX) & tg.mask
    depth = float(np.mean((tables.zmin + d + sc * S - 100.0)[mid]))
    return depth / yn, steps


@pytest.mark.parametrize("theta", [0.0, 45.0])
def test_the_channel_depth_holds_the_rule_on_polygons(theta: float) -> None:
    ratio, steps = run_channel(theta, "poly")
    assert ratio == pytest.approx(1.0, abs=RULE), (ratio, steps)


def test_on_squares_the_polygon_kernel_agrees_with_the_tile_kernel() -> None:
    tiles, _ = run_channel(0.0, "tiles")
    poly, _ = run_channel(0.0, "poly")
    assert poly == pytest.approx(tiles, abs=0.01)
