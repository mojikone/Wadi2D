"""Where do 20 m cells aligned along a thalweg over-read a flood peak on real ground while W3's straight channel passes
(W46, 2026-11-08)? Three grounds on the test harness, each run as squares and as the centre mesh, the depth at the
axis read against the normal depth of the exact section:

* control: W3's channel, a flat 60 m bed with 2:1 banks, straight;
* incised: the same with a low-flow slot 10 m wide and 1.5 m deep on the axis, where the thalweg lies on a face of
  the aligned cells and a 45 degree face samples the slot's pixels obliquely;
* sinuous: the same section along a sine-wave centreline, 120 m amplitude, 800 m wavelength (radius 135 m at the
  bends), straight-channel normal depth as the gentle-bend answer.

    .venv\\Scripts\\python "W46 centre-based mesh generator\\aligned_cells_probe.py" [case ...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import shapely
from scipy.optimize import brentq
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.solver.test_poly import BANK, DX, N, SIDE, T_END, WALL, B, K, Q, S  # noqa: E402
from wadi2d.config.schema import Numerics, Tables  # noqa: E402
from wadi2d.grid import TileGrid  # noqa: E402
from wadi2d.solver.backend import BoundaryCells  # noqa: E402
from wadi2d.solver.model import Model  # noqa: E402
from wadi2d.solver.state import level_of  # noqa: E402
from wadi2d.strips.centres import CentreSettings, Line, build_centre_mesh, stations_of  # noqa: E402
from wadi2d.strips.hybrid import HybridCpu, ghosts_for  # noqa: E402
from wadi2d.strips.tables import Pixels, build_poly_tables  # noqa: E402
from wadi2d.tables import ArrayBed, build_tables  # noqa: E402
from wadi2d.tables.builder import hbar_at_level  # noqa: E402

OUT = Path(__file__).resolve().parent / "probe"
SLOT_W, SLOT_D = 10.0, 1.5
AMP, WAVE = 120.0, 800.0
HALF = 0.3 * SIDE * DX


def section(t: np.ndarray, slot: bool) -> np.ndarray:
    """Height of the section above the bed at across-distance t: W3's, with or without the slot."""
    above = np.clip((np.abs(t) - B / 2) / BANK, 0.0, WALL)
    if slot:
        above = above - SLOT_D * (np.abs(t) < SLOT_W / 2)
    return above


def normal_depth(slot: bool) -> float:
    """Normal depth of the section by the Lotter sum, the sub-grid conveyance's own assumption: depth as the
    hydraulic radius strip by strip, no wall friction; the slot's floor sits SLOT_D below the bed."""
    t = np.linspace(-B / 2 - BANK * 10.0, B / 2 + BANK * 10.0, 20001)
    dt = t[1] - t[0]
    z = section(t, slot)

    def f(y: float) -> float:
        depth = np.clip(y - z, 0.0, None)
        return float(np.sum(depth ** (5 / 3)) * dt) * S**0.5 / N - Q

    return brentq(f, 0.01, 20.0)


def frame(x: np.ndarray, y: np.ndarray, theta: float, sinuous: bool) -> tuple[np.ndarray, np.ndarray, shapely.LineString]:
    """Along and across coordinates of points for a straight axis at ``theta`` or the sine-wave axis; and the axis."""
    xm, ym = 0.5 * SIDE * DX, -0.5 * SIDE * DX
    if not sinuous:
        th = np.radians(theta)
        ca, sa = np.cos(th), np.sin(th)
        s = (x - xm) * ca + (y - ym) * sa
        t = -(x - xm) * sa + (y - ym) * ca
        axis = shapely.LineString([(xm - HALF * ca, ym - HALF * sa), (xm + HALF * ca, ym + HALF * sa)])
        return s, t, axis
    u = np.linspace(-0.5 * SIDE * DX, 0.5 * SIDE * DX, 4001)
    curve = np.column_stack((xm + u, ym + AMP * np.sin(2 * np.pi * u / WAVE)))
    seg = np.diff(curve, axis=0)
    arc = np.concatenate(([0.0], np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))))
    arc -= arc[arc.size // 2]
    tree = cKDTree(curve)
    pts = np.column_stack((np.ravel(x), np.ravel(y)))
    d, k = tree.query(pts)
    k = np.clip(k, 1, curve.shape[0] - 2)
    tang = curve[k + 1] - curve[k - 1]
    tang /= np.maximum(np.hypot(tang[:, 0], tang[:, 1]), 1e-12)[:, None]
    rel = pts - curve[k]
    side = np.sign(-rel[:, 0] * tang[:, 1] + rel[:, 1] * tang[:, 0])
    s = arc[k].reshape(np.shape(x))
    t = (side * d).reshape(np.shape(x))
    keep = np.abs(u) <= HALF
    axis = shapely.LineString(curve[keep])
    return s, t, axis


def ground(theta: float, slot: bool, sinuous: bool):
    """The lattice grid, the bed pixels, and the along/across coordinates of pixels and of cell centres."""
    tg = TileGrid.from_mask(np.ones((SIDE, SIDE), bool), 0.0, 0.0, DX)
    ny, nx = tg.shape
    p = DX / K
    x = tg.x0 + (np.arange(nx * K) + 0.5) * p
    y = tg.y0 - (np.arange(ny * K) + 0.5) * p
    X, Y = np.meshgrid(x, y)
    s, t, axis = frame(X, Y, theta, sinuous)
    z = (100.0 - s * S + section(t, slot)).astype(np.float32).astype(np.float64)
    jj, ii = np.mgrid[0:ny, 0:nx]
    cx, cy = tg.xy_of(jj, ii)
    sc, tc, _axis = frame(cx, cy, theta, sinuous)
    return tg, z, p, sc, tc, axis


def run_case(theta: float, slot: bool, sinuous: bool, aligned: bool, floor_m: float = 70.0) -> dict:
    t0 = time.perf_counter()
    tg_full, z, p, sc, tc, axis = ground(theta, slot, sinuous)
    yn = normal_depth(slot)
    bed_level = 100.0 - sc * S  # the bed the normal depth is measured from: the 60 m bed, the slot below it
    strip = None
    mask = np.ones((SIDE, SIDE), bool)
    if aligned:
        s = CentreSettings(dx=DX)
        line = Line("axis", np.asarray(axis.coords), 50.0)
        pts, _n, _w = stations_of(line, s)
        strip = build_centre_mesh(tg_full, [line], [(np.full(pts.shape[0], floor_m), np.full(pts.shape[0], floor_m))], s)
        jj, ii = strip.masked
        mask[jj - 1, ii - 1] = False
    tg = TileGrid.from_mask(mask, 0.0, 0.0, DX)
    tables = build_tables(tg, ArrayBed(z, p), Tables(), N)
    model = Model(tables, Numerics(), "cpu")
    hc, dtab = tg.from_tiles(tables.hc), tg.from_tiles(tables.dtab)
    level = bed_level + yn
    wet = (np.abs(tc) < B / 2 + BANK * yn + 2 * DX) & tg.mask
    hb = np.where(wet, hbar_at_level(level, tables.zmin, hc, dtab), 0.0)
    model.set_depth(hb)
    hybrid = None
    if aligned:
        ghosts = ghosts_for(strip.geometry, model, tables)
        mesh, _kept = build_poly_tables(strip.geometry, Pixels(z, tg.x0, tg.y0, p), Tables(), DX, N, ghosts=ghosts)
        hybrid = HybridCpu(model, mesh, 1)
        n = hybrid.nreal
        s_cell, t_cell, _a = frame(mesh.cx[:n], mesh.cy[:n], theta, sinuous)
        strip_level = 100.0 - s_cell * S + yn
        strip_wet = np.abs(t_cell) < B / 2 + BANK * yn + 2 * DX
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
    # the water surface is the cell's level from its own table, not zmin plus the mean depth: on an incised bed the
    # two differ by the slot's share of the cell (the first reading put the strip 4.9 normal depths deep)
    if hybrid is not None:
        hybrid.advance(T_END)
        n = hybrid.nreal
        middle = (np.abs(s_cell) < 0.15 * SIDE * DX) & (np.abs(t_cell) < 0.51 * DX)
        surface = mesh.zmin[:n] + level_of(hybrid.state.d[:n].astype(np.float64), mesh.hc[:n], mesh.dtab[:n])
        depth = float(np.mean((surface - (100.0 - s_cell * S))[middle]))
        steps = model.stepper.nsteps
    else:
        model.advance(T_END)
        d = model.field("d").astype(np.float64)
        middle = (np.abs(sc) < 0.15 * SIDE * DX) & (np.abs(tc) < 0.51 * DX) & tg.mask
        surface = tables.zmin + level_of(d, hc, dtab)
        depth = float(np.mean((surface - bed_level)[middle]))
        steps = model.stepper.nsteps
    return {"depth_over_normal": depth / yn, "normal_depth_m": yn, "depth_m": depth, "steps": steps, "cells_read": int(middle.sum()), "wall_s": round(time.perf_counter() - t0, 1)}


CASES = {
    "control_0": dict(theta=0.0, slot=False, sinuous=False),
    "control_45": dict(theta=45.0, slot=False, sinuous=False),
    "incised_0": dict(theta=0.0, slot=True, sinuous=False),
    "incised_45": dict(theta=45.0, slot=True, sinuous=False),
    "sinuous": dict(theta=0.0, slot=False, sinuous=True),
    "sinuous_incised": dict(theta=0.0, slot=True, sinuous=True),
}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    names = sys.argv[1:] or list(CASES)
    results = {}
    for name in names:
        case = CASES[name]
        for aligned in (False, True):
            key = f"{name}/{'centres' if aligned else 'squares'}"
            try:
                r = run_case(aligned=aligned, **case)
            except Exception as error:  # noqa: BLE001  a probe reports, it does not stop
                r = {"error": f"{type(error).__name__}: {error}"}
            results[key] = r
            print(key, json.dumps(r), flush=True)
    (OUT / "aligned_cells_probe.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
