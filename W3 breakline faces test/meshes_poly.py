"""Polylines for option (b) and the conforming triangles of option (e).

snap_polylines: lattice vertices moved onto any polyline, bends and junctions included; records what it cannot do.
generate_tri / mesh_tri: Delaunay triangles whose edges contain every line. scipy has plain Delaunay only, so conformity comes from the point set:
each line resampled at h, an offset row each side, the background kept off them, and any line segment still missing is split until it is an edge.
"""
from __future__ import annotations

import numpy as np

from graph import finish
from lattice import ROWS, cell_table
from meshes import FaceList, _empty_cells, assign_pixels, face_samples, sample


def seg_point_dist(px, py, ax, ay, bx, by):
    dx_, dy_ = bx - ax, by - ay
    l2 = dx_ * dx_ + dy_ * dy_
    t = np.clip(((px - ax) * dx_ + (py - ay) * dy_) / max(l2, 1e-24), 0.0, 1.0)
    return np.hypot(px - ax - t * dx_, py - ay - t * dy_), ax + t * dx_, ay + t * dy_


def steps_between(a, b):
    """Corners after a on the way to b, nearest the straight line: the production rule of wadi2d/terrain/crest.py _steps."""
    cj, ci = a
    dj, di = b[0] - a[0], b[1] - a[1]
    nj, ni = abs(dj), abs(di)
    sj, si = int(np.sign(dj)), int(np.sign(di))
    ix = iy = 0
    out = []
    while ix < ni or iy < nj:
        if (1 + 2 * ix) * nj < (1 + 2 * iy) * ni:
            ci += si
            ix += 1
        else:
            cj += sj
            iy += 1
        out.append((cj, ci))
    return out


def snap_polylines(bed, polys, smooth=0, ring=2):
    """Each polyline vertex takes the nearest lattice vertex exactly; the walk between takes the nearest corners, each moved to its foot on the
    segment. Returns vertices, fixed mask, chains and conflicts: a vertex two lines both want, which can sit on only one of them."""
    ny, nx, dx = bed.ny, bed.nx, bed.dx
    xs = bed.x0 + np.arange(nx + 1) * dx
    ys = bed.y0 + np.arange(ny + 1) * dx
    xv, yv = np.meshgrid(xs, ys)
    owner = -np.ones(xv.shape, np.int64)
    conflicts = 0
    chains = []

    def inside(c):
        return 0 <= c[0] <= ny and 0 <= c[1] <= nx

    for ln, poly in enumerate(polys):
        poly = np.asarray(poly, dtype=np.float64)
        corners = [(round((p[1] - bed.y0) / dx), round((p[0] - bed.x0) / dx)) for p in poly]
        walk = [corners[0]]
        seg_of = [0]
        for s in range(len(corners) - 1):
            for c in steps_between(walk[-1], corners[s + 1]):
                walk.append(c)
                seg_of.append(s)
        hard = {0: poly[0]}
        for s in range(len(corners) - 1):
            stretch = [n for n, q in enumerate(seg_of) if q == s]
            hard[stretch[-1]] = poly[s + 1]
        for n, c in enumerate(walk):
            if not inside(c):
                continue
            j, i = c
            if n in hard:
                tx, ty = hard[n]
            else:
                s = seg_of[n]
                _, tx, ty = seg_point_dist(xs[i], ys[j], *poly[s], *poly[s + 1])
            if owner[j, i] >= 0 and owner[j, i] != ln:
                conflicts += 1
                continue
            if owner[j, i] < 0:
                xv[j, i], yv[j, i] = tx, ty
                owner[j, i] = ln
        chains.append([c for c in walk if inside(c)])
    fixed = owner >= 0
    if smooth:
        near = fixed.copy()
        for _ in range(ring):
            g = near.copy()
            g[1:, :] |= near[:-1, :]
            g[:-1, :] |= near[1:, :]
            g[:, 1:] |= near[:, :-1]
            g[:, :-1] |= near[:, 1:]
            near = g
        free = near & ~fixed
        free[0, :] = free[-1, :] = False
        free[:, 0] = free[:, -1] = False
        for _ in range(smooth):
            ax = 0.25 * (xv[:-2, 1:-1] + xv[2:, 1:-1] + xv[1:-1, :-2] + xv[1:-1, 2:])
            ay = 0.25 * (yv[:-2, 1:-1] + yv[2:, 1:-1] + yv[1:-1, :-2] + yv[1:-1, 2:])
            f = free[1:-1, 1:-1]
            xv[1:-1, 1:-1][f] = ax[f]
            yv[1:-1, 1:-1][f] = ay[f]
    return xv, yv, fixed, chains, conflicts


def _line_points(poly, h):
    poly = np.asarray(poly, dtype=np.float64)
    pts, offs = [], []
    r = h * np.sqrt(3.0) / 2.0
    for a, b in zip(poly[:-1], poly[1:], strict=True):
        ln = float(np.hypot(*(b - a)))
        m = max(int(round(ln / h)), 1)
        t = (b - a) / ln
        nv = np.array([-t[1], t[0]])
        for q in range(m):
            pts.append(a + (b - a) * q / m)
        for q in range(m):
            c = a + (b - a) * (q + 0.5) / m
            offs.append(c + r * nv)
            offs.append(c - r * nv)
    pts.append(poly[-1])
    return np.array(pts), np.array(offs)


SMOOTH_ITERS = 12


def generate_tri(polys, h, keep, box):
    """Points: a triangular background in the global frame (never rotated to the line), each line at h, one offset row each side. Delaunay, Laplace
    on the free points, then any line segment that is not an edge is split. Returns points, triangles, segments, Steiner count, unresolved."""
    from scipy.spatial import Delaunay, cKDTree

    xmin, xmax, ymin, ymax = box
    r = h * np.sqrt(3.0) / 2.0
    ys = np.arange(ymin, ymax + r, r)
    bg = []
    for n, y in enumerate(ys):
        xs = np.arange(xmin + (0.5 * h if n % 2 else 0.0), xmax + h, h)
        bg.append(np.stack((xs, np.full(xs.size, y)), axis=1))
    bg = np.concatenate(bg)
    bg = bg[keep(bg[:, 0], bg[:, 1], 2.5 * h)]
    lines = [_line_points(p, h) for p in polys]
    lpts = np.concatenate([a for a, _ in lines])
    lpts = np.unique(np.round(lpts, 6), axis=0)
    # line points run past the domain edge: a line that stops at its last interior point leaves a gap at the end
    pad = 3.0 * h
    inb = (lpts[:, 0] >= xmin - pad) & (lpts[:, 0] <= xmax + pad) & (lpts[:, 1] >= ymin - pad) & (lpts[:, 1] <= ymax + pad)
    lpts = lpts[inb]
    offs = np.concatenate([b for _, b in lines])
    offs = offs[keep(offs[:, 0], offs[:, 1], 2.5 * h)]
    d, _ = cKDTree(lpts).query(offs)
    offs = offs[d > 0.75 * h]
    tree = cKDTree(offs)
    alive = np.ones(offs.shape[0], bool)
    for a, b in sorted(tree.query_pairs(0.7 * h)):
        if alive[a] and alive[b]:
            alive[b] = False
    offs = offs[alive]
    anchor = np.concatenate((lpts, offs))
    d, _ = cKDTree(anchor).query(bg)
    bg = bg[d > 0.8 * h]
    n_fix = lpts.shape[0]  # only line points are held; offset rows relax with the rest
    pts = np.concatenate((anchor, bg))
    for _ in range(SMOOTH_ITERS):
        tri = Delaunay(pts)
        nb = [set() for _ in range(pts.shape[0])]
        for s in tri.simplices:
            for u in range(3):
                nb[s[u]].update((s[(u + 1) % 3], s[(u + 2) % 3]))
        new = pts.copy()
        rim = keep(pts[:, 0], pts[:, 1], 1.2 * h)
        for q in range(n_fix, pts.shape[0]):
            if rim[q] and len(nb[q]) >= 5:
                new[q] = pts[list(nb[q])].mean(axis=0)
        pts = new
    # slivers come from free points too close to a neighbour: drop them, relax again
    for _ in range(6):
        tri = Delaunay(pts)
        e = np.concatenate((tri.simplices[:, [0, 1]], tri.simplices[:, [1, 2]], tri.simplices[:, [2, 0]]))
        e = np.unique(np.sort(e, axis=1), axis=0)
        ln = np.hypot(*(pts[e[:, 0]] - pts[e[:, 1]]).T)
        short = e[ln < 0.62 * h]
        drop = np.zeros(pts.shape[0], bool)
        for a, b in short:
            if drop[a] or drop[b]:
                continue
            if b >= n_fix:
                drop[b] = True
            elif a >= n_fix:
                drop[a] = True
        pts = pts[~drop]
        for _ in range(6):
            tri = Delaunay(pts)
            nb = [set() for _ in range(pts.shape[0])]
            for s in tri.simplices:
                for u in range(3):
                    nb[s[u]].update((s[(u + 1) % 3], s[(u + 2) % 3]))
            new = pts.copy()
            rim = keep(pts[:, 0], pts[:, 1], 1.2 * h)
            for q in range(n_fix, pts.shape[0]):
                if rim[q] and len(nb[q]) >= 5:
                    new[q] = pts[list(nb[q])].mean(axis=0)
            pts = new
    lookup = {tuple(np.round(p, 6)): n for n, p in enumerate(pts[: lpts.shape[0]])}
    segs = []
    for p in polys:
        a = _line_points(p, h)[0]
        ids = [lookup.get(tuple(np.round(q, 6)), -1) for q in a]
        for u, v in zip(ids[:-1], ids[1:], strict=True):
            if u >= 0 and v >= 0:
                segs.append((u, v))
    steiner = 0
    missing = []
    for _ in range(12):
        tri = Delaunay(pts)
        edges = set()
        for s in tri.simplices:
            for u in range(3):
                a, b = int(s[u]), int(s[(u + 1) % 3])
                edges.add((min(a, b), max(a, b)))
        missing = [e for e in segs if (min(e), max(e)) not in edges]
        if not missing:
            break
        add = []
        next_id = pts.shape[0]
        ok = [e for e in segs if (min(e), max(e)) in edges]
        for u, v in missing:
            add.append(0.5 * (pts[u] + pts[v]))
            ok += [(u, next_id), (next_id, v)]
            next_id += 1
        steiner += len(add)
        pts = np.concatenate((pts, np.array(add)))
        segs = ok
    return pts, tri.simplices.copy(), segs, steiner, len(missing)


def circumcentres(pts, tris):
    a, b, c = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    bx, by = b[:, 0] - a[:, 0], b[:, 1] - a[:, 1]
    cx, cy = c[:, 0] - a[:, 0], c[:, 1] - a[:, 1]
    d = 2.0 * (bx * cy - by * cx)
    ux = (cy * (bx * bx + by * by) - by * (cx * cx + cy * cy)) / d
    uy = (bx * (cx * cx + cy * cy) - cx * (bx * bx + by * by)) / d
    return a[:, 0] + ux, a[:, 1] + uy, 0.5 * np.abs(d)


def mesh_tri(bed, n, polys, h, keep, box, centre="circum"):
    """Staggered scheme on circumcentres: the line between two centres is normal to the shared face, so the skew term vanishes by construction."""
    p, k, ny, nx = bed.p, bed.k, bed.ny, bed.nx
    pts, tris, segs, steiner, unresolved = generate_tri(polys, h, keep, box)
    g = pts[tris].mean(axis=1)
    mask = keep(g[:, 0], g[:, 1], 0.0)
    e1, e2 = pts[tris[:, 1]] - pts[tris[:, 0]], pts[tris[:, 2]] - pts[tris[:, 0]]
    area = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
    mask &= (area > 1e-6 * h * h) & (area < 6.0 * 0.433 * h * h)  # the upper bound drops hull triangles at the band edge
    q = pts[tris]
    xmin, xmax, ymin, ymax = box
    mask &= (q[:, :, 0].min(axis=1) >= xmin - 1e-9) & (q[:, :, 0].max(axis=1) <= xmax + 1e-9)  # no cell beyond the terrain: its edges would read no ground
    mask &= (q[:, :, 1].min(axis=1) >= ymin - 1e-9) & (q[:, :, 1].max(axis=1) <= ymax + 1e-9)
    tris = tris[mask]
    area = area[mask]
    nc = tris.shape[0]
    a_ = pts[tris]
    xq = np.concatenate((a_[:, :, 0], a_[:, 2:3, 0]), axis=1)
    yq = np.concatenate((a_[:, :, 1], a_[:, 2:3, 1]), axis=1)
    owner = assign_pixels(xq, yq, p, bed.x0, bed.y0, ny * k, nx * k)
    z = bed.z[1:-1, 1:-1]
    order = np.argsort(owner, axis=None)
    so = owner.ravel()[order]
    zs = z.ravel()[order]
    starts = np.searchsorted(so, np.arange(nc), side="left")
    ends = np.searchsorted(so, np.arange(nc), side="right")
    ce = _empty_cells(nc)
    ux, uy, _ = circumcentres(pts, tris)
    gx, gy = a_[:, :, 0].mean(axis=1), a_[:, :, 1].mean(axis=1)
    tab = np.zeros(ROWS)
    for c in range(nc):
        ce["Ac"][c] = area[c]
        ce["cx"][c], ce["cy"][c] = (ux[c], uy[c]) if centre == "circum" else (gx[c], gy[c])
        pix = zs[starts[c] : ends[c]]
        if pix.size == 0:
            pix = sample(bed.z, p, bed.x0, bed.y0, np.array([gx[c]]), np.array([gy[c]]))
        zm, rel, hc = cell_table(pix.copy(), ROWS, tab)
        ce["zmin"][c], ce["zbar"][c], ce["hc"][c] = zm, zm + rel, hc
        ce["dtab"][c] = tab
    emap = {}
    for c in range(nc):
        s = tris[c]
        for u in range(3):
            a, b = int(s[u]), int(s[(u + 1) % 3])
            emap.setdefault((min(a, b), max(a, b)), []).append((c, int(s[(u + 2) % 3])))
    fl = FaceList()
    n_inv = 1.0 / n
    for (a, b), who in emap.items():
        if len(who) != 2:
            continue
        (c1, opp), (c2, _) = who
        pa, pb = pts[a], pts[b]
        ln = float(np.hypot(*(pb - pa)))
        prof, pix = face_samples(bed, pa[0], pa[1], pb[0], pb[1])
        nfx, nfy = (pb[1] - pa[1]) / ln, -(pb[0] - pa[0]) / ln
        if (pts[opp][0] - pa[0]) * nfx + (pts[opp][1] - pa[1]) * nfy > 0:
            nfx, nfy = -nfx, -nfy
        fl.add(c1, c2, ln, nfx, nfy, 0.5 * (pa[0] + pb[0]), 0.5 * (pa[1] + pb[1]), prof, pix, n_inv)
    faces = fl.done()
    raw_dn = (ce["cx"][faces["R"]] - ce["cx"][faces["L"]]) * faces["nx"] + (ce["cy"][faces["R"]] - ce["cy"][faces["L"]]) * faces["ny"]
    me = finish(ce, faces, h)
    me.tri_pts, me.tris, me.segs, me.steiner, me.unresolved = pts, tris, segs, steiner, unresolved
    me.gx, me.gy = gx, gy  # a circumcentre can lie across the line: which side a cell is on is read from the centroid
    me.clipped_dn = float(np.mean(raw_dn < 0.15 * h))
    me.neg_dn = float(np.mean(raw_dn <= 0.0))
    return me
