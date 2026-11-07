"""Probe 4: why the real corridor gets 8 rows at +-30 m: the across heights along the main corridor's mid-line
under curvature adaptation on/off, uniform-layer counts and cross-spline spacings."""

from __future__ import annotations

import numpy as np
import shapely
from meshkernel import CurvilinearParameters, MeshKernel, SplinesToCurvilinearParameters

from common import bank_lines, thalwegs
from mkutil import geom_list

banks = {b["fid"]: b for b in bank_lines()}
th = max(thalwegs(), key=lambda t: t["area_km2"])["line"]


def chain(fids):
    pts = []
    for f in fids:
        c = list(banks[f]["line"].coords)
        if pts:
            d0 = np.hypot(c[0][0] - pts[-1][0], c[0][1] - pts[-1][1])
            d1 = np.hypot(c[-1][0] - pts[-1][0], c[-1][1] - pts[-1][1])
            if d1 < d0:
                c = c[::-1]
        else:
            if th.project(shapely.Point(c[-1])) < th.project(shapely.Point(c[0])):
                c = c[::-1]
        pts.extend(c)
    return shapely.LineString(pts)


L = chain((54, 7, 358))
R = chain((98, 51, 88, 68))
st = np.arange(10, L.length - 10, 10.0)
pts = []
for s in st:
    p = L.interpolate(s)
    sr = R.project(p)
    if sr <= 10 or sr >= R.length - 10:
        continue
    q = R.interpolate(sr)
    pts.append([(p.x + q.x) / 2, (p.y + q.y) / 2])
pts = np.asarray(pts)
sm = np.array([pts[max(0, i - 2): i + 3].mean(axis=0) for i in range(len(pts))])
mid = shapely.LineString(sm)
n = int(round(mid.length / 20))
mid = shapely.LineString([[q.x, q.y] for q in (mid.interpolate(t, normalized=True) for t in np.linspace(0, 1, n + 1))])
print("midline", round(mid.length, 1), "m,", len(mid.coords), "vertices")


def crosses(centre, half, every):
    out = []
    stations = list(np.arange(0.0, centre.length, every)) + [centre.length]
    for s in stations:
        p = centre.interpolate(s)
        p1 = centre.interpolate(max(s - 1.0, 0.0))
        p2 = centre.interpolate(min(s + 1.0, centre.length))
        t = np.array([p2.x - p1.x, p2.y - p1.y])
        t /= max(np.hypot(*t), 1e-9)
        nrm = np.array([-t[1], t[0]])
        out.append(np.array([[p.x, p.y] - half * nrm, [p.x, p.y] + half * nrm]))
    return out


def run(tag, half=30.0, every=100.0, curvature=1, uniform=3, aspect=0.5, width=20.0, grow=1.0, outside=False):
    mk = MeshKernel()
    mk.curvilinear_compute_orthogonal_from_splines(
        geom_list([np.asarray(mid.coords)] + crosses(mid, half, every)),
        CurvilinearParameters(m_refinement=4000, n_refinement=40),
        SplinesToCurvilinearParameters(aspect_ratio=aspect, aspect_ratio_grow_factor=grow, average_width=width,
                                       curvature_adapted_grid_spacing=curvature, grow_grid_outside=outside,
                                       maximum_num_faces_in_uniform_part=uniform, check_front_collisions=True,
                                       remove_skinny_triangles=True),
    )
    g = mk.curvilineargrid_get()
    x = np.asarray(g.node_x).reshape(g.num_n, g.num_m)
    y = np.asarray(g.node_y).reshape(g.num_n, g.num_m)
    valid = np.isfinite(x) & (x > -900)
    x = np.where(valid, x, np.nan)
    y = np.where(valid, y, np.nan)
    h = np.hypot(np.diff(x, axis=1), np.diff(y, axis=1))  # (n, m-1) across heights
    along = np.hypot(np.diff(x[:, x.shape[1] // 2]), np.diff(y[:, y.shape[1] // 2]))
    print(f"{tag}: n along {x.shape[0]}, rows {x.shape[1] - 1}; along spacing median {np.nanmedian(along):.1f} min {np.nanmin(along):.1f} max {np.nanmax(along):.1f}")
    print("   row heights median:", np.round(np.nanmedian(h, axis=0), 2), " min:", np.round(np.nanmin(h, axis=0), 2), " max:", np.round(np.nanmax(h, axis=0), 2))
    print("   valid node share per row:", np.round(valid.mean(axis=0), 3))
    return x, y


run("A curvature on, uniform 3, cross every 100")
run("B curvature off", curvature=0)
run("C curvature on, cross every 400", every=400.0)
run("D curvature on, cross only at the ends", every=1e9)
run("E curvature off, cross only at the ends", curvature=0, every=1e9)
run("F curvature on, uniform 10", uniform=10)
run("G curvature on, half 29.9", half=29.9)
run("H curvature on, aspect 0.75 (15 m), uniform 2", aspect=0.75, uniform=2)
run("I curvature off, half 29.9, cross at ends", curvature=0, half=29.9, every=1e9)
