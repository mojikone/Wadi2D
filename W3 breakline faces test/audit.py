"""Proof of alignment: for any mesh given as polygons, how the breakline sits on the cell edges, by measurement."""
from __future__ import annotations

import numpy as np
from numba import njit


@njit
def _nearest(px, py, ex0, ey0, ex1, ey1):
    out = np.empty(px.size)
    for n in range(px.size):
        best = 1e30
        for e in range(ex0.size):
            ax, ay = ex0[e], ey0[e]
            dx, dy = ex1[e] - ax, ey1[e] - ay
            l2 = dx * dx + dy * dy
            t = 0.0
            if l2 > 0.0:
                t = min(max(((px[n] - ax) * dx + (py[n] - ay) * dy) / l2, 0.0), 1.0)
            qx, qy = ax + t * dx - px[n], ay + t * dy - py[n]
            v = qx * qx + qy * qy
            if v < best:
                best = v
        out[n] = np.sqrt(best)
    return out


@njit
def _shape(xq, yq, nv):
    """Per polygon: signed area, smallest and largest interior angle, longest over shortest edge."""
    n = xq.shape[0]
    area, amin, amax, ratio = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    for c in range(n):
        m = nv[c]
        a2 = 0.0
        for q in range(m):
            x1, y1 = xq[c, q], yq[c, q]
            x2, y2 = xq[c, (q + 1) % m], yq[c, (q + 1) % m]
            a2 += x1 * y2 - x2 * y1
        turn = 1.0 if a2 >= 0.0 else -1.0
        lo, hi = 1e9, -1e9
        l0, l1 = 1e30, 0.0
        for q in range(m):
            x0, y0 = xq[c, (q + m - 1) % m], yq[c, (q + m - 1) % m]
            x1, y1 = xq[c, q], yq[c, q]
            x2, y2 = xq[c, (q + 1) % m], yq[c, (q + 1) % m]
            ax, ay, bx, by = x2 - x1, y2 - y1, x0 - x1, y0 - y1
            ang = np.degrees(np.arctan2(turn * (ax * by - ay * bx), ax * bx + ay * by))
            ang = ang + 360.0 if ang < 0.0 else ang
            lo = min(lo, ang)
            hi = max(hi, ang)
            e = np.hypot(ax, ay)
            l0 = min(l0, e)
            l1 = max(l1, e)
        area[c], amin[c], amax[c], ratio[c] = 0.5 * a2, lo, hi, l1 / max(l0, 1e-12)
    return area, amin, amax, ratio


@njit
def _straddled(px, py, flag, xq, yq, nv):
    hit = np.zeros(xq.shape[0], np.bool_)
    for n in range(px.size):
        if not flag[n]:
            continue
        for c in range(xq.shape[0]):
            m = nv[c]
            ins = False
            for q in range(m):
                x1, y1 = xq[c, q], yq[c, q]
                x2, y2 = xq[c, (q + 1) % m], yq[c, (q + 1) % m]
                if (y1 > py[n]) != (y2 > py[n]) and px[n] < (x2 - x1) * (py[n] - y1) / (y2 - y1) + x1:
                    ins = not ins
            if ins:
                hit[c] = True
    return hit


def sample_lines(polys, step=0.5):
    xs, ys = [], []
    for poly in polys:
        poly = np.asarray(poly, dtype=np.float64)
        for a, b in zip(poly[:-1], poly[1:], strict=True):
            m = max(int(np.hypot(*(b - a)) / step), 1)
            t = np.arange(m + 1) / m
            xs.append(a[0] + (b[0] - a[0]) * t)
            ys.append(a[1] + (b[1] - a[1]) * t)
    return np.concatenate(xs), np.concatenate(ys)


def audit(polys, xq, yq, nv, dx, tol=0.01, region=None):
    """xq, yq (nc, maxv) polygon vertices; nv vertex counts. tol, m: a line sample further than this from every edge is off the mesh."""
    from scipy.spatial import cKDTree

    px, py = sample_lines(polys)
    if region is not None:
        k = region(px, py)
        px, py = px[k], py[k]
    n = xq.shape[0]
    ex0, ey0, ex1, ey1 = [], [], [], []
    for m in np.unique(nv):
        s = nv == m
        for q in range(m):
            ex0.append(xq[s, q])
            ey0.append(yq[s, q])
            ex1.append(xq[s, (q + 1) % m])
            ey1.append(yq[s, (q + 1) % m])
    ex0, ey0, ex1, ey1 = (np.concatenate(a) for a in (ex0, ey0, ex1, ey1))
    tree = cKDTree(np.stack((px, py), axis=1))
    d0, _ = tree.query(np.stack((0.5 * (ex0 + ex1), 0.5 * (ey0 + ey1)), axis=1))
    near = d0 < 3.0 * dx
    dist = _nearest(px, py, ex0[near], ey0[near], ex1[near], ey1[near])
    off = dist > tol
    area, amin, amax, ratio = _shape(xq, yq, nv)
    cx = np.array([xq[c, : nv[c]].mean() for c in range(n)])
    cy = np.array([yq[c, : nv[c]].mean() for c in range(n)])
    d1, _ = tree.query(np.stack((cx, cy), axis=1))
    along = d1 < 1.1 * dx
    hit = _straddled(px, py, off, xq[d1 < 2.0 * dx], yq[d1 < 2.0 * dx], nv[d1 < 2.0 * dx])
    sign = np.sign(np.median(area))
    return dict(
        max_dist_m=float(dist.max()), share_off_line=float(off.mean()), straddled_cells=int(hit.sum()), inverted=int((area * sign <= 0).sum()),
        amin_deg=float(amin[along].min()), amax_deg=float(amax[along].max()), area_min=float((np.abs(area[along]) / dx**2).min()),
        ratio_max=float(ratio[along].max()), n_along=int(along.sum()),
    )  # fmt: skip


def quads_of(xv, yv, band=None):
    ny, nx = xv.shape[0] - 1, xv.shape[1] - 1
    jj, ii = np.nonzero(np.ones((ny, nx), bool) if band is None else band)
    xq = np.stack((xv[jj, ii], xv[jj, ii + 1], xv[jj + 1, ii + 1], xv[jj + 1, ii]), axis=1)
    yq = np.stack((yv[jj, ii], yv[jj, ii + 1], yv[jj + 1, ii + 1], yv[jj + 1, ii]), axis=1)
    return xq, yq, np.full(jj.size, 4, np.int64)
