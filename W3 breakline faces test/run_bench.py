"""Cost per cell-step, all cells wet, one thread, compile time excluded.

The lattice kernel is the port of production; the polygon kernel is a face list. So this measures arithmetic on a CPU, not a GPU. Each number is the
least of five timings, because a full-extent job runs on the same machine.
"""
import sys
import time

sys.path.insert(0, ".")
import numpy as np

import cases as C
from graph import Graph
from lattice_fast import Lattice
from meshes import Bed, mesh_cut, mesh_lattice, mesh_snap
from meshes_poly import mesh_tri

SIDE, DX, K = C.SIDE, C.DX, C.K
P = DX / K


def bed_plane():
    x = (np.arange(SIDE * K + 2) - 1 + 0.5) * P - 0.5 * SIDE * DX
    X, Y = np.meshgrid(x, x)
    return -0.001 * X - 0.0007 * Y + 0.02 * np.sin(X / 3.0) * np.cos(Y / 4.0)


def timed(m, nsteps=160):
    best = 1e9
    t = m.t
    for rep in range(6):
        steps0 = m.nsteps
        t0 = time.perf_counter()
        while m.nsteps < steps0 + nsteps:
            t += 1.0
            m.dt = 0.5
            m.advance(t)
        el = time.perf_counter() - t0
        if rep:  # the first pass compiles
            best = min(best, el / (m.nsteps - steps0))
    return best


def main():
    z = bed_plane()
    band = np.ones((SIDE, SIDE), bool)
    th = np.radians(30.0)
    nv = np.array([-np.sin(th), np.cos(th)])
    tv = np.array([np.cos(th), np.sin(th)])
    # lines every 8 cells: every cell of the domain is near one, the worst case for the metric arrays
    lines = [(tuple(nv * o), th) for o in np.arange(-1200.0, 1201.0, 160.0)]
    polys = [np.array([np.array(p) - 2000 * tv, np.array(p) + 2000 * tv]) for p, _ in lines]
    bed = Bed(z, K, DX, SIDE, SIDE)
    rows = []

    def lat(name, **kw):
        m = Lattice(z, K, DX, C.N, SIDE, SIDE, **kw)
        m.set_depth(np.full((SIDE, SIDE), 2.0))
        ts = timed(m)
        rows.append((name, SIDE * SIDE, 2 * SIDE * SIDE, ts))

    def grp(name, me, dxr, **kw):
        m = Graph(me, dxr, **kw)
        m.set_depth(np.full(me.Ac.size, 2.0))
        ts = timed(m)
        rows.append((name, me.Ac.size, me.L.size, ts))

    lat("a lattice port")
    lat("m mirror", mirror=True)
    lat("ms3 mirror + plan section", mirror=True, sheet=3)
    lat("a again, drift check")
    grp("P polygons on lattice, no skew", mesh_lattice(bed, C.N, band, DX), DX, sheet=1, skew=False)
    grp("P polygons on lattice, skew", mesh_lattice(bed, C.N, band, DX), DX, sheet=1, skew=True)
    grp("b snapped, skew", mesh_snap(bed, C.N, band, lines), DX, sheet=2, skew=True)
    me = mesh_cut(bed, C.N, band, lines)
    grp(f"c cut, {me.split_cells} split", me, DX, sheet=2, skew=True)
    half = 0.5 * SIDE * DX

    def keep(x, y, pad):
        return (np.abs(x) <= half + 1e-9) & (np.abs(y) <= half + 1e-9)

    grp("e tri h20", mesh_tri(bed, C.N, polys, 20.0, keep, (-half, half, -half, half)), 20.0, sheet=3, skew=False)
    grp("e tri h26.3", mesh_tri(bed, C.N, polys, 26.3, keep, (-half, half, -half, half)), 26.3, sheet=3, skew=False)
    base = rows[0][3] / rows[0][1]
    print(f"{'kernel':34s} {'cells':>7s} {'faces':>7s} {'ns/cell':>8s} {'ns/face':>8s} {'x base/cell':>11s} {'x base/step':>11s}")
    for n, nc, nf, t in rows:
        print(f"{n:34s} {nc:7d} {nf:7d} {t/nc*1e9:8.1f} {t/nf*1e9:8.1f} {t/nc/base:11.2f} {t/rows[0][3]:11.2f}")


if __name__ == "__main__":
    main()
