"""Alignment proved: straight lines, bends, junctions, on the lattice, the snapped lattice and the triangles. Mesh only, no flow.

Cut cells (c) are audited in the same table by construction: their internal face is the chord, so distance is zero while a cell holds at most two
bodies; `cells_over_2` counts lattice cells that a junction or a bend would need more than two bodies in.
"""
import csv
import sys

sys.path.insert(0, ".")
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from audit import audit, quads_of, sample_lines
from meshes import Bed
from meshes_poly import generate_tri, snap_polylines

DX = 20.0
N = 128
HALF = N * DX / 2
BOX = (-HALF, HALF, -HALF, HALF)


def straight(theta, off=0.0):
    th = np.radians(theta)
    t = np.array([np.cos(th), np.sin(th)])
    nv = np.array([-t[1], t[0]])
    c = nv * off
    return [np.array([c - t * 1000, c + t * 1000])]


def bent(defl, a0=7.0):
    """Two reaches meeting near the origin; the first at a0 degrees, so neither reach is on the lattice by luck."""
    t1 = np.radians(a0)
    t2 = np.radians(a0 + defl)
    p = np.array([3.3, 4.7])
    return [np.array([p - 800 * np.array([np.cos(t1), np.sin(t1)]), p, p + 800 * np.array([np.cos(t2), np.sin(t2)])])]


def junction(angle, a0=11.0):
    """A second line ends on the first, at `angle` between them."""
    t1 = np.radians(a0)
    p = np.array([3.3, 4.7])
    main = np.array([p - 800 * np.array([np.cos(t1), np.sin(t1)]), p + 800 * np.array([np.cos(t1), np.sin(t1)])])
    t2 = np.radians(a0 + angle)
    arm = np.array([p, p + 800 * np.array([np.cos(t2), np.sin(t2)])])
    return [main, arm]


CASES = []
for th in (0, 15, 22.5, 30, 45):
    for off in (0.0, 7.3):
        CASES.append((f"straight {th} off {off}", straight(th, off)))
for d in (15, 30, 45, 60, 90, 120, 135, 150, 165):
    CASES.append((f"bend {d}", bent(d)))
for a in (90, 60, 45, 30, 20, 10):
    CASES.append((f"junction {a}", junction(a)))


def box(px, py):
    return (np.abs(px) < 900) & (np.abs(py) < 900)


def cells_over_two(polys):
    """Lattice cells holding more than one line stretch that would need three or more bodies: cells where two lines both pass."""
    per = []
    for p in polys:
        x, y = sample_lines([p], 0.5)
        k = box(x, y)
        per.append(set(zip(np.floor((y[k] + HALF) / DX).astype(int).tolist(), np.floor((x[k] + HALF) / DX).astype(int).tolist(), strict=True)))
    if len(per) < 2:
        return 0
    return len(per[0] & per[1])


def one(a):
    name, polys = a
    bed = Bed(np.zeros((N * 20 + 2, N * 20 + 2)), 20, DX, N, N)
    rows = []
    xs = bed.x0 + np.arange(N + 1) * DX
    xv, yv = np.meshgrid(xs, xs)
    xq, yq, nv = quads_of(xv, yv)
    rows.append(dict(case=name, option="a lattice", conflicts=0, cells2=cells_over_two(polys), **audit(polys, xq, yq, nv, DX, region=box)))
    for sm in (0, 8):
        xv, yv, fixed, chains, conf = snap_polylines(bed, polys, smooth=sm)
        xq, yq, nv = quads_of(xv, yv)
        rows.append(dict(case=name, option=f"b snap sm{sm}", conflicts=conf, cells2=0, **audit(polys, xq, yq, nv, DX, region=box)))

    def keep(x, y, pad):
        return (np.abs(x) <= HALF + 1e-9) & (np.abs(y) <= HALF + 1e-9)

    pts, tris, segs, st, unres = generate_tri(polys, DX, keep, BOX)
    q = pts[tris]
    rows.append(dict(case=name, option="e tri h20", conflicts=unres, steiner=st, cells2=0, **audit(polys, q[:, :, 0], q[:, :, 1], np.full(tris.shape[0], 3, np.int64), DX, region=box)))
    return rows


if __name__ == "__main__":
    with ProcessPoolExecutor(11) as ex:
        res = list(ex.map(one, CASES))
    rows = [r for g in res for r in g]
    keys = ["case", "option", "max_dist_m", "share_off_line", "straddled_cells", "inverted", "amin_deg", "amax_deg", "area_min", "ratio_max", "conflicts", "steiner", "cells2", "n_along"]
    with open("results/alignment.csv", "w", newline="") as f:
        w = csv.DictWriter(f, keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"{'case':22s} {'option':12s} {'maxdist':>8s} {'off%':>6s} {'strad':>6s} {'inv':>4s} {'amin':>6s} {'amax':>6s} {'Amin':>6s} {'L/l':>7s} {'conf':>4s} {'stein':>5s} {'c>2':>4s}")
    for r in rows:
        print(f"{r['case']:22s} {r['option']:12s} {r['max_dist_m']:8.3f} {r['share_off_line']*100:6.1f} {r['straddled_cells']:6d} {r['inverted']:4d} {r['amin_deg']:6.1f} {r['amax_deg']:6.1f} {r['area_min']:6.3f} {r['ratio_max']:7.1f} {r['conflicts']:4d} {r.get('steiner',0):5d} {r['cells2']:4d}")
