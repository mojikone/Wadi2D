"""Probe: what curvilinear_compute_orthogonal_from_splines (advancing front) makes of a centre spline, with and
without cross splines, and what the transfinite call needs. Prints grid sizes and layer heights; writes probe_splines.png.
"""

from __future__ import annotations

import time
import traceback

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from meshkernel import (
    CurvilinearParameters,
    GeometryList,
    MeshKernel,
    SplinesToCurvilinearParameters,
)

from common import HERE, bank_lines

SEP = -999.0


def splines_geom(lines: list[np.ndarray]) -> GeometryList:
    xs, ys = [], []
    for i, ln in enumerate(lines):
        if i:
            xs.append(SEP)
            ys.append(SEP)
        xs.extend(ln[:, 0])
        ys.extend(ln[:, 1])
    return GeometryList(np.asarray(xs, float), np.asarray(ys, float))


def grow(lines, average_width=20.0, aspect_ratio=0.375, uniform=2, grow_factor=1.0, m_ref=2000, n_ref=40, outside=False,
         curvature=1, check_collisions=False):
    mk = MeshKernel()
    cp = CurvilinearParameters(m_refinement=m_ref, n_refinement=n_ref)
    sp = SplinesToCurvilinearParameters(
        aspect_ratio=aspect_ratio,
        aspect_ratio_grow_factor=grow_factor,
        average_width=average_width,
        curvature_adapted_grid_spacing=curvature,
        grow_grid_outside=outside,
        maximum_num_faces_in_uniform_part=uniform,
        check_front_collisions=check_collisions,
        remove_skinny_triangles=True,
    )
    t0 = time.perf_counter()
    mk.curvilinear_compute_orthogonal_from_splines(splines_geom(lines), cp, sp)
    g = mk.curvilineargrid_get()
    dt = time.perf_counter() - t0
    return mk, g, dt


def describe(tag, g, dt):
    x = np.asarray(g.node_x).reshape(g.num_n, g.num_m) if g.num_m * g.num_n == len(g.node_x) else None
    print(f"{tag}: num_m={g.num_m} num_n={g.num_n} nodes={len(g.node_x)} ({dt*1e3:.0f} ms)")
    if x is None:
        print("  node count does not match num_m*num_n")
        return None, None
    y = np.asarray(g.node_y).reshape(g.num_n, g.num_m)
    valid = np.isfinite(x) & (x > -900)
    print("  valid nodes", valid.sum(), "of", valid.size)
    # layer heights along n at the middle m
    jm = g.num_m // 2
    col = [(x[i, jm], y[i, jm]) for i in range(g.num_n) if valid[i, jm]]
    if len(col) > 1:
        d = [np.hypot(col[i + 1][0] - col[i][0], col[i + 1][1] - col[i][1]) for i in range(len(col) - 1)]
        print("  layer heights at mid m:", np.round(d, 2))
    row = [(x[0, j], y[0, j]) for j in range(g.num_m) if valid[0, j]]
    if len(row) > 1:
        d = [np.hypot(row[i + 1][0] - row[i][0], row[i + 1][1] - row[i][1]) for i in range(len(row) - 1)]
        print(f"  m spacing on row 0: min {min(d):.2f} median {np.median(d):.2f} max {max(d):.2f} n={len(d)}")
    return x, y


def draw(ax, x, y, title):
    if x is None:
        return
    valid = np.isfinite(x) & (x > -900)
    xm = np.where(valid, x, np.nan)
    ym = np.where(valid, y, np.nan)
    for i in range(xm.shape[0]):
        ax.plot(xm[i], ym[i], color="k", lw=0.4)
    for j in range(xm.shape[1]):
        ax.plot(xm[:, j], ym[:, j], color="k", lw=0.4)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=8)


fig, axes = plt.subplots(2, 3, figsize=(18, 11))
axes = axes.ravel()

# 1. a straight line, 2 km, no cross splines
straight = np.array([[0.0, 0.0], [1000.0, 0.0], [2000.0, 0.0]])
try:
    mk, g, dt = grow([straight])
    x, y = describe("straight, no cross splines, ar 0.375 uniform 2", g, dt)
    draw(axes[0], x, y, "straight, no cross splines")
    axes[0].set_xlim(900, 1100)
except Exception:
    traceback.print_exc()

# 2. straight with cross splines of +-15 m at the ends and the middle
cross = [np.array([[s, -15.0], [s, 15.0]]) for s in (0.0, 1000.0, 2000.0)]
try:
    mk, g, dt = grow([straight, *cross])
    x, y = describe("straight + 3 cross splines +-15 m, ar 0.375 uniform 2", g, dt)
    draw(axes[1], x, y, "straight + cross +-15 m")
    axes[1].set_xlim(900, 1100)
except Exception:
    traceback.print_exc()

# 3. the same with grow_grid_outside
try:
    mk, g, dt = grow([straight, *cross], outside=True)
    x, y = describe("straight + cross, grow outside", g, dt)
    draw(axes[2], x, y, "straight + cross, grow outside")
    axes[2].set_xlim(900, 1100)
except Exception:
    traceback.print_exc()

# 4. bank 7 alone, no cross splines
banks = {b["fid"]: b for b in bank_lines()}
b7 = np.asarray(banks[7]["line"].coords)
try:
    mk, g, dt = grow([b7])
    x, y = describe("bank 7, no cross splines", g, dt)
    draw(axes[3], x, y, "bank 7, no cross splines")
    axes[3].plot(b7[:, 0], b7[:, 1], color="r", lw=0.8)
except Exception:
    traceback.print_exc()

# 5. bank 7 with cross splines every ~500 m, +-15 m along the normal
from shapely import LineString

ln = LineString(b7)
cross7 = []
for s in np.linspace(0.0, ln.length, 6):
    p = ln.interpolate(s)
    p1 = ln.interpolate(max(s - 1.0, 0.0))
    p2 = ln.interpolate(min(s + 1.0, ln.length))
    t = np.array([p2.x - p1.x, p2.y - p1.y])
    t /= np.hypot(*t)
    nrm = np.array([-t[1], t[0]])
    cross7.append(np.array([[p.x, p.y] - 15 * nrm, [p.x, p.y] + 15 * nrm]))
try:
    mk, g, dt = grow([b7, *cross7])
    x, y = describe("bank 7 + 6 cross splines +-15 m", g, dt)
    draw(axes[4], x, y, "bank 7 + cross +-15 m")
    axes[4].plot(b7[:, 0], b7[:, 1], color="r", lw=0.8)
except Exception:
    traceback.print_exc()

# 6. bank 7 with cross splines, curvature adapted off, check collisions on
try:
    mk, g, dt = grow([b7, *cross7], curvature=0, check_collisions=True)
    x, y = describe("bank 7 + cross, no curvature adaptation, collisions checked", g, dt)
    draw(axes[5], x, y, "bank 7 + cross, no curvature adapt")
    axes[5].plot(b7[:, 0], b7[:, 1], color="r", lw=0.8)
except Exception:
    traceback.print_exc()

fig.tight_layout()
fig.savefig(HERE / "probe_splines.png", dpi=110)
print("wrote probe_splines.png")
