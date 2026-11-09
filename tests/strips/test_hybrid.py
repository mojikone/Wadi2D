"""Tiles and a strip in one step (W45, stage 3): a lattice patch replaced by the same squares as a strip gives the
all-tiles answer, still water across the join stays still, and a closed box keeps its water."""

from __future__ import annotations

import numpy as np
import pytest

from tests.solver.test_poly import BANK, DX, SIDE, T_END, B, K, Q, S, channel, normal_depth
from wadi2d.config.schema import Numerics, Tables
from wadi2d.solver.backend import BoundaryCells
from wadi2d.solver.model import Model
from wadi2d.solver.state import level_of
from wadi2d.strips.geometry import MeshGeometry
from wadi2d.strips.hybrid import ghosts_for, make_hybrid
from wadi2d.strips.tables import Pixels, build_poly_tables
from wadi2d.tables.builder import hbar_at_level

PATCH = slice(43, 53)
"""The ten by ten cells of the active area that become the strip; the channel axis runs through them."""


def patch_mask() -> np.ndarray:
    patch = np.zeros((SIDE, SIDE), bool)
    patch[PATCH, PATCH] = True
    return patch


def squares_of(tg, patch_padded: np.ndarray) -> tuple[MeshGeometry, np.ndarray, np.ndarray]:
    """The patch cells as a polygon mesh of squares; and their (j, i) on the padded grid, in cell order."""
    jj, ii = np.nonzero(patch_padded)
    corner: dict[tuple[int, int], int] = {}
    xs, ys, rings = [], [], []
    for j, i in zip(jj, ii, strict=True):
        ring = []
        for cj, ci in ((j + 1, i), (j + 1, i + 1), (j, i + 1), (j, i)):  # SW, SE, NE, NW: counter-clockwise
            if (cj, ci) not in corner:
                corner[(cj, ci)] = len(xs)
                xs.append(tg.x0 + ci * tg.dx)
                ys.append(tg.y0 - cj * tg.dx)
            ring.append(corner[(cj, ci)])
        rings.append(np.array(ring))
    return MeshGeometry.from_rings(np.array(xs), np.array(ys), rings), jj, ii


def hybrid_case(theta: float, num: Numerics | None = None, backend: str = "cpu"):
    """The channel with the patch masked out of the tiles and carried by a strip of the same squares."""
    patch = patch_mask()
    tg, tables, sc, tc = channel(theta, ~patch)
    padded = np.zeros(tg.shape, bool)
    padded[1 : 1 + SIDE, 1 : 1 + SIDE] = patch
    geo, jj, ii = squares_of(tg, padded)
    model = Model(tables, num or Numerics(), backend)
    ghosts = ghosts_for(geo, model, tables)
    assert ghosts.count == 40  # the ring of tile cells round a 10 x 10 patch
    _, _, _, _, z = _bed(theta)
    mesh, _kept = build_poly_tables(geo, Pixels(z, tg.x0, tg.y0, DX / K), Tables(), DX, 0.03, ghosts=ghosts)
    hybrid = make_hybrid(model, mesh)
    return tg, tables, sc, tc, model, hybrid, (jj, ii)


def _bed(theta: float):
    """The same bed `channel` builds, for the strip's pixels."""
    tg, _tables, sc, tc = channel(theta)
    ny, nx = tg.shape
    p = DX / K
    x = tg.x0 + (np.arange(nx * K) + 0.5) * p
    y = tg.y0 - (np.arange(ny * K) + 0.5) * p
    X, Y = np.meshgrid(x, y)
    xm, ym = 0.5 * SIDE * DX, -0.5 * SIDE * DX
    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    s = (X - xm) * ca + (Y - ym) * sa
    t = -(X - xm) * sa + (Y - ym) * ca
    above = np.clip((np.abs(t) - B / 2) / BANK, 0.0, 5.0)
    return tg, sc, tc, p, (100.0 - s * S + above).astype(np.float32).astype(np.float64)


def composed_depth(tg, hybrid, cells) -> np.ndarray:
    """The level above zmin on the whole grid: the tiles', and the strip's on its cells."""
    d = hybrid.model.field("d").astype(np.float64)
    jj, ii = cells
    d[jj, ii] = hybrid.strip_host("d")[: hybrid.nreal].astype(np.float64)
    return d


def run_hybrid_channel(theta: float, backend: str = "cpu") -> tuple[float, int]:
    tg, tables, sc, tc, model, hybrid, cells = hybrid_case(theta, backend=backend)
    yn = normal_depth(B, BANK, Q)
    hc, dtab = tg.from_tiles(tables.hc), tg.from_tiles(tables.dtab)
    level = 100.0 - sc * S + yn
    wet = (np.abs(tc) < B / 2 + BANK * yn + 2 * DX) & tg.mask
    hb = np.where(wet, hbar_at_level(level, tables.zmin, hc, dtab), 0.0)
    model.set_depth(hb)
    jj, ii = cells
    strip_level = level[jj, ii]
    strip_wet = np.abs(tc[jj, ii]) < B / 2 + BANK * yn + 2 * DX
    hybrid.set_strip_depth(np.where(strip_wet, hybrid.strip_hbar_at_level(strip_level), 0.0))
    lim = 0.45 * SIDE * DX
    up = (sc > -lim) & (sc < -lim + 6 * DX) & (np.abs(tc) < B / 2 + DX) & tg.mask
    model.set_source(np.where(up, Q / (up.sum() * DX * DX), 0.0))
    down = (sc > lim - 6 * DX) & (sc < lim) & (np.abs(tc) < B + 3 * DX) & tg.mask
    dj, di = np.nonzero(down)
    d0 = level_of(hb[down], hc[down], dtab[down])
    held = np.array([model.cell_state_index(int(j), int(i)) for j, i in zip(dj, di, strict=True)], np.int32)
    zero = np.zeros(held.size, np.int32)
    model.set_boundary(BoundaryCells(held, zero, zero.copy(), d0.astype(np.float32), hb[down].astype(np.float32)))
    hybrid.advance(T_END)
    d = composed_depth(tg, hybrid, cells)
    on_patch = np.zeros(tg.shape, bool)
    on_patch[jj, ii] = True
    mid = (np.abs(sc) < 0.15 * SIDE * DX) & (np.abs(tc) < 0.71 * DX) & (tg.mask | on_patch)
    depth = float(np.mean((tables.zmin + d + sc * S - 100.0)[mid]))
    return depth / yn, model.stepper.nsteps


@pytest.mark.parametrize(("theta", "tolerance"), [(0.0, 0.002), (45.0, 0.01)])
def test_a_patch_carried_by_a_strip_of_the_same_squares_gives_the_all_tiles_answer(theta: float, tolerance: float) -> None:
    from tests.solver.test_poly import run_channel

    tiles, _ = run_channel(theta, "tiles")
    hybrid, steps = run_hybrid_channel(theta)
    assert hybrid == pytest.approx(tiles, abs=tolerance), (hybrid, tiles, steps)


def test_still_water_across_the_join_stays_still_and_keeps_its_volume() -> None:
    tg, tables, _sc, _tc, model, hybrid, _cells = hybrid_case(30.0, Numerics(dt_every=1))
    hc, dtab = tg.from_tiles(tables.hc), tg.from_tiles(tables.dtab)
    hb = hbar_at_level(101.0, tables.zmin, hc, dtab) * tg.mask
    model.set_depth(hb)
    hybrid.set_strip_depth(hybrid.strip_hbar_at_level(101.0))
    v0 = hybrid.volume()
    hybrid.advance(600.0)
    speed = max(float(np.abs(model.field("u")).max()), float(np.abs(model.field("v")).max()))
    assert speed < 2e-5
    assert float(np.abs(hybrid.strip_host("u")).max()) < 2e-5
    assert hybrid.volume() == pytest.approx(v0, rel=1e-7)


def test_a_closed_box_sloshing_across_the_join_keeps_its_water() -> None:
    tg, tables, sc, _tc, model, hybrid, cells = hybrid_case(0.0, Numerics(dt_every=1))
    hc, dtab = tg.from_tiles(tables.hc), tg.from_tiles(tables.dtab)
    level = 101.0 + 0.3 * np.tanh(sc / 100.0)  # a step of 0.6 m across the patch, released
    hb = hbar_at_level(level, tables.zmin, hc, dtab) * tg.mask
    model.set_depth(hb)
    jj, ii = cells
    hybrid.set_strip_depth(hybrid.strip_hbar_at_level(level[jj, ii]))
    v0 = hybrid.volume()
    hybrid.advance(300.0)
    assert float(np.abs(hybrid.strip_host("q")).max()) > 0.1  # water crossed the join
    assert hybrid.volume() == pytest.approx(v0, rel=1e-7)
