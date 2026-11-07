"""Probe 2: does the advancing front follow the local cross-spline length (one-sided growth, unequal heights),
and how do the layer heights relate to aspect_ratio, average_width and maximum_num_faces_in_uniform_part.
Writes probe_front.png.
"""

from __future__ import annotations

import traceback

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from meshkernel import CurvilinearParameters, MeshKernel, SplinesToCurvilinearParameters

from common import HERE
from mkutil import geom_list


def grow(lines, **kw):
    p = dict(aspect_ratio=0.5, aspect_ratio_grow_factor=1.0, average_width=20.0, curvature_adapted_grid_spacing=1,
             grow_grid_outside=False, maximum_num_faces_in_uniform_part=3, check_front_collisions=False,
             remove_skinny_triangles=True)
    p.update(kw)
    mk = MeshKernel()
    mk.curvilinear_compute_orthogonal_from_splines(geom_list(lines), CurvilinearParameters(m_refinement=2000, n_refinement=40),
                                                   SplinesToCurvilinearParameters(**p))
    g = mk.curvilineargrid_get()
    x = np.asarray(g.node_x).reshape(g.num_n, g.num_m)
    y = np.asarray(g.node_y).reshape(g.num_n, g.num_m)
    valid = np.isfinite(x) & (x > -900)
    return np.where(valid, x, np.nan), np.where(valid, y, np.nan), mk


def show(ax, x, y, title, xlim=None):
    for i in range(x.shape[0]):
        ax.plot(x[i], y[i], color="k", lw=0.5)
    for j in range(x.shape[1]):
        ax.plot(x[:, j], y[:, j], color="k", lw=0.5)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=8)
    if xlim:
        ax.set_xlim(*xlim)


def report(tag, x, y):
    print(tag, "shape (n along, m across):", x.shape)
    jm = x.shape[1] // 2
    # the across coordinates at a few stations along: distances from the first across node
    for i in (0, x.shape[0] // 4, x.shape[0] // 2, x.shape[0] - 1):
        row = np.column_stack([x[i], y[i]])
        row = row[np.isfinite(row[:, 0])]
        d = np.hypot(*np.diff(row, axis=0).T)
        print(f"  station {i}: {len(row)} nodes across, cell heights {np.round(d, 2)}")


straight = np.array([[0.0, 0.0], [1000.0, 0.0], [2000.0, 0.0]])
fig, axes = plt.subplots(2, 3, figsize=(18, 10))
axes = axes.ravel()

cases = [
    ("A: cross +-30, ar 0.5 (10 m), uniform 3", [straight] + [np.array([[s, -30.0], [s, 30.0]]) for s in (0, 1000, 2000)], {}),
    ("B: one-sided cross 0..+30", [straight] + [np.array([[s, 0.0], [s, 30.0]]) for s in (0, 1000, 2000)], {}),
    ("C: cross +-30 at ends, +-15 mid (does height follow?)",
     [straight, np.array([[0, -30.0], [0, 30.0]]), np.array([[1000, -15.0], [1000, 15.0]]), np.array([[2000, -30.0], [2000, 30.0]])], {}),
    ("D: cross +-30, uniform 1, grow 1.5", [straight] + [np.array([[s, -30.0], [s, 30.0]]) for s in (0, 1000, 2000)],
     dict(maximum_num_faces_in_uniform_part=1, aspect_ratio_grow_factor=1.5)),
    ("E: cross +-25 (not a multiple of 10)", [straight] + [np.array([[s, -25.0], [s, 25.0]]) for s in (0, 1000, 2000)], {}),
    ("F: cross -10..+30 (asymmetric)", [straight] + [np.array([[s, -10.0], [s, 30.0]]) for s in (0, 1000, 2000)], {}),
]
for ax, (tag, lines, kw) in zip(axes, cases):
    try:
        x, y, mk = grow(lines, **kw)
        report(tag, x, y)
        show(ax, x, y, tag, xlim=(900, 1100))
    except Exception:
        print(tag, "FAILED")
        traceback.print_exc()
fig.tight_layout()
fig.savefig(HERE / "probe_front.png", dpi=110)

# G: a curved centre spline (quarter circle R=100 m) with +-30 m cross splines: does the inside collide?
th = np.linspace(0, np.pi / 2, 9)
arc = np.column_stack([100 * np.cos(th), 100 * np.sin(th)])
cross = []
for t in (0, np.pi / 4, np.pi / 2):
    p = np.array([100 * np.cos(t), 100 * np.sin(t)])
    n = np.array([np.cos(t), np.sin(t)])
    cross.append(np.array([p - 30 * n, p + 30 * n]))
for chk in (False, True):
    try:
        x, y, mk = grow([arc] + cross, check_front_collisions=chk)
        report(f"G: arc R=100 +-30, collisions {chk}", x, y)
    except Exception:
        print("G FAILED", chk)
        traceback.print_exc()
# H: the spline's fit: how far is the spline from a polyline with 60 m segments and 30 deg turns?
pts = [np.array([0.0, 0.0])]
ang = 0.0
rng = np.random.default_rng(1)
for k in range(30):
    ang += np.radians(rng.uniform(-30, 30))
    pts.append(pts[-1] + 60 * np.array([np.cos(ang), np.sin(ang)]))
pl = np.array(pts)
try:
    x, y, mk = grow([pl, np.array([pl[0] + [0, -30], pl[0] + [0, 30]]), np.array([pl[-1] + [0, -30], pl[-1] + [0, 30]])])
    report("H: zigzag polyline 60 m / +-30 deg", x, y)
    import shapely

    line = shapely.LineString(pl)
    jm = x.shape[1] // 2
    centre = np.column_stack([x[:, jm], y[:, jm]])
    centre = centre[np.isfinite(centre[:, 0])]
    d = np.array([line.distance(shapely.Point(p)) for p in centre])
    print(f"  centre grid line vs polyline: median {np.median(d):.2f} p90 {np.percentile(d, 90):.2f} max {d.max():.2f} m")
    fig2, ax2 = plt.subplots(figsize=(12, 8))
    show(ax2, x, y, "H: spline through a 60 m / +-30 deg zigzag")
    ax2.plot(pl[:, 0], pl[:, 1], "r-", lw=1)
    fig2.savefig(HERE / "probe_front_zigzag.png", dpi=110)
except Exception:
    print("H FAILED")
    traceback.print_exc()
