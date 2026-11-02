"""Meshes for the polygon kernel, all from the same pixels as the baseline.

mesh_lattice: the plain lattice as a face list (variant P: Perot advection, no geometry change).
mesh_snap: option (b). Logical grid and tile topology kept; lattice vertices of a 4-connected chain moved onto each breakline.
mesh_cut: option (c). Lattice kept; a crossed cell holds one body per side of the line, a crossed face one part per side, and the two
bodies of a cell share an internal face along the chord.
"""
from __future__ import annotations

import numpy as np
from numba import njit

from graph import finish
from lattice import ROWS, cell_table, face_table


class Bed:
    """Pixel access: z is (ny*k+2, nx*k+2), one extra row and column each side, origin (x0, y0) is the lattice corner of cell (0, 0)."""

    def __init__(self, z, k, dx, ny, nx):
        self.z, self.k, self.dx, self.ny, self.nx = z, k, dx, ny, nx
        self.p = dx / k
        self.x0 = -0.5 * nx * dx
        self.y0 = -0.5 * ny * dx


@njit
def sample(z, p, x0, y0, xs, ys):
    """Nearest pixel at points."""
    out = np.empty(xs.size)
    nr, nc = z.shape
    for m in range(xs.size):
        c = int(np.floor((xs[m] - x0) / p)) + 1
        r = int(np.floor((ys[m] - y0) / p)) + 1
        out[m] = z[min(max(r, 0), nr - 1), min(max(c, 0), nc - 1)]
    return out


def face_samples(bed, ax, ay, bx, by):
    """Ground along a segment: the higher of the pixels either side, as production. Returns profile, sample length."""
    ln = float(np.hypot(bx - ax, by - ay))
    m = max(int(np.ceil(ln / bed.p)), 1)
    t = (np.arange(m) + 0.5) / m
    xs = ax + (bx - ax) * t
    ys = ay + (by - ay) * t
    nx_, ny_ = (by - ay) / max(ln, 1e-12), -(bx - ax) / max(ln, 1e-12)
    off = 0.5 * bed.p
    z1 = sample(bed.z, bed.p, bed.x0, bed.y0, xs - off * nx_, ys - off * ny_)
    z2 = sample(bed.z, bed.p, bed.x0, bed.y0, xs + off * nx_, ys + off * ny_)
    return np.maximum(z1, z2), ln / m


def _empty_cells(n):
    return dict(Ac=np.zeros(n), cx=np.zeros(n), cy=np.zeros(n), zmin=np.zeros(n), zbar=np.zeros(n), hc=np.zeros(n), dtab=np.zeros((n, ROWS)))


class FaceList:
    def __init__(self):
        self.L, self.R, self.ln, self.nx, self.ny, self.xf, self.yf, self.zf, self.ef, self.ftab = ([] for _ in range(10))

    def add(self, a, b, ln, nx, ny, xf, yf, prof, pix, n_inv, e_lo=8.0, e_hi=16.0):
        tab = np.zeros((ROWS, 2))
        zf, top = face_table(np.asarray(prof, dtype=np.float64), np.nan, pix, n_inv, 1.0, e_lo, e_hi, tab)
        self.L.append(a)
        self.R.append(b)
        self.ln.append(ln)
        self.nx.append(nx)
        self.ny.append(ny)
        self.xf.append(xf)
        self.yf.append(yf)
        self.zf.append(zf)
        self.ef.append(top)
        self.ftab.append(tab)

    def done(self):
        return dict(
            L=np.array(self.L, np.int64), R=np.array(self.R, np.int64), ln=np.array(self.ln), nx=np.array(self.nx), ny=np.array(self.ny),
            xf=np.array(self.xf), yf=np.array(self.yf), zf=np.array(self.zf), ef=np.array(self.ef), ftab=np.array(self.ftab),
        )  # fmt: skip


def mesh_lattice(bed, n, band, dx):
    """Variant P: same tables as the lattice, same geometry; only the kernel form differs."""
    ny, nx, k = bed.ny, bed.nx, bed.k
    idx = -np.ones((ny, nx), np.int64)
    idx[band] = np.arange(band.sum())
    nc = int(band.sum())
    ce = _empty_cells(nc)
    tab = np.zeros(ROWS)
    z = bed.z
    for c, (j, i) in enumerate(zip(*np.nonzero(band), strict=True)):
        r0, c0 = 1 + j * k, 1 + i * k
        zm, rel, hc = cell_table(z[r0 : r0 + k, c0 : c0 + k].copy(), ROWS, tab)
        ce["Ac"][c] = dx * dx
        ce["cx"][c] = bed.x0 + (i + 0.5) * dx
        ce["cy"][c] = bed.y0 + (j + 0.5) * dx
        ce["zmin"][c], ce["zbar"][c], ce["hc"][c] = zm, zm + rel, hc
        ce["dtab"][c] = tab
    fl = FaceList()
    n_inv = 1.0 / n
    for j, i in zip(*np.nonzero(band), strict=True):
        r0, c0 = 1 + j * k, 1 + i * k
        if i > 0 and band[j, i - 1]:
            prof = np.maximum(z[r0 : r0 + k, c0 - 1], z[r0 : r0 + k, c0])
            fl.add(idx[j, i - 1], idx[j, i], dx, 1.0, 0.0, bed.x0 + i * dx, bed.y0 + (j + 0.5) * dx, prof, bed.p, n_inv)
        if j > 0 and band[j - 1, i]:
            prof = np.maximum(z[r0 - 1, c0 : c0 + k], z[r0, c0 : c0 + k])
            fl.add(idx[j - 1, i], idx[j, i], dx, 0.0, 1.0, bed.x0 + (i + 0.5) * dx, bed.y0 + j * dx, prof, bed.p, n_inv)
    return finish(ce, fl.done(), dx)


# ---------------------------------------------------------------- option (b)
def chain(xv, yv, p0, th):
    """4-connected walk of lattice vertices nearest a line, angles 0..45 degrees. Returns (j, i) pairs."""
    ca, sa = np.cos(th), np.sin(th)
    nvx, nvy = -sa, ca
    ny1, nx1 = xv.shape
    dist = lambda j, i: (xv[j, i] - p0[0]) * nvx + (yv[j, i] - p0[1]) * nvy  # noqa: E731
    j = int(np.argmin(np.abs(dist(np.arange(ny1), 0))))
    i = 0
    out = [(j, i)]
    while True:
        cand = []
        if i + 1 < nx1:
            cand.append((abs(dist(j, i + 1)), j, i + 1))
        if j + 1 < ny1 and sa > 1e-9:
            cand.append((abs(dist(j + 1, i)), j + 1, i))
        if not cand:
            break
        _, j, i = min(cand)
        out.append((j, i))
    return out


def snap_vertices(bed, lines, smooth=0, ring=2):
    """lines: list of (p0, theta_rad). Moves chain vertices onto the lines, optional Jacobi smoothing of the rings beside the chains."""
    ny, nx, dx = bed.ny, bed.nx, bed.dx
    xs = bed.x0 + np.arange(nx + 1) * dx
    ys = bed.y0 + np.arange(ny + 1) * dx
    xv, yv = np.meshgrid(xs, ys)
    fixed = np.zeros(xv.shape, bool)
    for p0, th in lines:
        ca, sa = np.cos(th), np.sin(th)
        nvx, nvy = -sa, ca
        for j, i in chain(xv, yv, p0, th):
            d = (xv[j, i] - p0[0]) * nvx + (yv[j, i] - p0[1]) * nvy
            if fixed[j, i]:
                continue
            xv[j, i] -= d * nvx
            yv[j, i] -= d * nvy
            fixed[j, i] = True
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
    return xv, yv, fixed


@njit
def assign_pixels(xq, yq, p, x0, y0, nr, nc):
    """Pixel list per quad by the crossing rule. xq, yq: (nq, 4). Returns pixel -> quad, -1 where none."""
    owner = -np.ones((nr, nc), np.int64)
    for q in range(xq.shape[0]):
        xa, xb = xq[q].min(), xq[q].max()
        ya, yb = yq[q].min(), yq[q].max()
        c0 = max(int(np.floor((xa - x0) / p)), 0)
        c1 = min(int(np.ceil((xb - x0) / p)), nc - 1)
        r0 = max(int(np.floor((ya - y0) / p)), 0)
        r1 = min(int(np.ceil((yb - y0) / p)), nr - 1)
        for r in range(r0, r1 + 1):
            py = y0 + (r + 0.5) * p
            for c in range(c0, c1 + 1):
                px = x0 + (c + 0.5) * p
                inside = False
                for m in range(4):
                    x1, y1 = xq[q, m], yq[q, m]
                    x2, y2 = xq[q, (m + 1) % 4], yq[q, (m + 1) % 4]
                    if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
                        inside = not inside
                if inside:
                    owner[r, c] = q
    return owner


def polygon(xq, yq):
    """Signed area and centroid of a polygon."""
    x1, y1 = np.roll(xq, -1), np.roll(yq, -1)
    cr = xq * y1 - x1 * yq
    a = 0.5 * cr.sum()
    return a, ((xq + x1) * cr).sum() / (6 * a), ((yq + y1) * cr).sum() / (6 * a)


def mesh_snap(bed, n, band, lines, smooth=0, ring=2, polys=None):
    ny, nx, k, p, dx = bed.ny, bed.nx, bed.k, bed.p, bed.dx
    if polys is None:
        xv, yv, fixed = snap_vertices(bed, lines, smooth, ring)
    else:
        from meshes_poly import snap_polylines

        xv, yv, fixed, _, _ = snap_polylines(bed, polys, smooth, ring)
    jj, ii = np.nonzero(band)
    nc = jj.size
    idx = -np.ones((ny, nx), np.int64)
    idx[jj, ii] = np.arange(nc)
    xq = np.stack((xv[jj, ii], xv[jj, ii + 1], xv[jj + 1, ii + 1], xv[jj + 1, ii]), axis=1)
    yq = np.stack((yv[jj, ii], yv[jj, ii + 1], yv[jj + 1, ii + 1], yv[jj + 1, ii]), axis=1)
    owner = assign_pixels(xq, yq, p, bed.x0, bed.y0, ny * k, nx * k)
    z = bed.z[1:-1, 1:-1]
    ce = _empty_cells(nc)
    order = np.argsort(owner, axis=None)
    so = owner.ravel()[order]
    zs = z.ravel()[order]
    starts = np.searchsorted(so, np.arange(nc), side="left")
    ends = np.searchsorted(so, np.arange(nc), side="right")
    tab = np.zeros(ROWS)
    bad = 0
    for c in range(nc):
        a, cx, cy = polygon(xq[c], yq[c])
        if a <= 0.01 * dx * dx:
            bad += 1
        ce["Ac"][c], ce["cx"][c], ce["cy"][c] = max(a, 1e-3 * dx * dx), cx, cy
        pix = zs[starts[c] : ends[c]]
        if pix.size == 0:
            pix = sample(bed.z, p, bed.x0, bed.y0, np.array([cx]), np.array([cy]))
        zm, rel, hc = cell_table(pix.copy(), ROWS, tab)
        ce["zmin"][c], ce["zbar"][c], ce["hc"][c] = zm, zm + rel, hc
        ce["dtab"][c] = tab
    fl = FaceList()
    n_inv = 1.0 / n

    def add(a, b, ax, ay, bx, by):
        ln = float(np.hypot(bx - ax, by - ay))
        if ln < 1e-6:
            return
        prof, pix = face_samples(bed, ax, ay, bx, by)
        # normal from cell a to cell b
        nfx, nfy = (by - ay) / ln, -(bx - ax) / ln
        if nfx * (ce["cx"][b] - ce["cx"][a]) + nfy * (ce["cy"][b] - ce["cy"][a]) < 0:
            nfx, nfy = -nfx, -nfy
        fl.add(a, b, ln, nfx, nfy, 0.5 * (ax + bx), 0.5 * (ay + by), prof, pix, n_inv)

    for j, i in zip(jj, ii, strict=True):
        if i > 0 and band[j, i - 1]:
            add(idx[j, i - 1], idx[j, i], xv[j, i], yv[j, i], xv[j + 1, i], yv[j + 1, i])
        if j > 0 and band[j - 1, i]:
            add(idx[j - 1, i], idx[j, i], xv[j, i], yv[j, i], xv[j, i + 1], yv[j, i + 1])
    me = finish(ce, fl.done(), dx)
    me.bad = bad
    me.vertices = (xv, yv, fixed)
    return me


# ---------------------------------------------------------------- option (c)
def chord(x0, y0, dx, p0, th, tmin=-1e12, tmax=1e12):
    """Segment of a line, between tmin and tmax along it, inside the square with corner (x0, y0), or None."""
    ca, sa = np.cos(th), np.sin(th)
    t0, t1 = tmin, tmax
    for o, d, lo, hi in ((p0[0], ca, x0, x0 + dx), (p0[1], sa, y0, y0 + dx)):
        if abs(d) < 1e-12:
            if o <= lo or o >= hi:
                return None
            continue
        a, b = (lo - o) / d, (hi - o) / d
        t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
    if t1 <= t0:
        return None
    return p0[0] + t0 * ca, p0[1] + t0 * sa, p0[0] + t1 * ca, p0[1] + t1 * sa


def mesh_cut(bed, n, band, lines, fmin=0.0, code_fn=None, segs=None):
    """One body per region per cell. fmin: a body under this share of the cell is folded into its neighbour body, its faces closed."""
    ny, nx, k, p, dx = bed.ny, bed.nx, bed.k, bed.p, bed.dx
    x = bed.x0 + (np.arange(nx * k) + 0.5) * p
    y = bed.y0 + (np.arange(ny * k) + 0.5) * p
    X, Y = np.meshgrid(x, y)
    code = np.zeros(X.shape, np.int64)
    if code_fn is not None:
        code = code_fn(X, Y)
    else:
        for m, (p0, th) in enumerate(lines):
            code += (((X - p0[0]) * -np.sin(th) + (Y - p0[1]) * np.cos(th)) > 0).astype(np.int64) << m
    z = bed.z[1:-1, 1:-1]
    body = -np.ones(X.shape, np.int64)
    Ac, cx, cy, cell_of, reg = [], [], [], [], []
    tab = np.zeros(ROWS)
    zmin, zbar, hc, dtab = [], [], [], []
    per_cell = {}
    for j, i in zip(*np.nonzero(band), strict=True):
        r0, c0 = j * k, i * k
        blk = code[r0 : r0 + k, c0 : c0 + k]
        cc, counts = np.unique(blk, return_counts=True)
        keep = cc[counts >= fmin * k * k] if fmin > 0 else cc
        if keep.size == 0:
            keep = cc[[int(np.argmax(counts))]]
        big = cc[int(np.argmax(counts))]
        ids = []
        for cd in keep:
            mask = blk == cd
            if cd == big:
                mask = mask | ~np.isin(blk, keep)  # folded slivers join the larger body
            b = len(Ac)
            sub = z[r0 : r0 + k, c0 : c0 + k][mask]
            zm, rel, hh = cell_table(sub.copy(), ROWS, tab)
            Ac.append(sub.size * p * p)
            cx.append(X[r0 : r0 + k, c0 : c0 + k][mask].mean())
            cy.append(Y[r0 : r0 + k, c0 : c0 + k][mask].mean())
            zmin.append(zm)
            zbar.append(zm + rel)
            hc.append(hh)
            dtab.append(tab.copy())
            cell_of.append((j, i))
            reg.append(cd)
            body[r0 : r0 + k, c0 : c0 + k][mask] = b
            ids.append(b)
        per_cell[(j, i)] = ids
    ce = dict(Ac=np.array(Ac), cx=np.array(cx), cy=np.array(cy), zmin=np.array(zmin), zbar=np.array(zbar), hc=np.array(hc), dtab=np.array(dtab))
    reg = np.array(reg)
    fl = FaceList()
    n_inv = 1.0 / n

    def parts(bl, br, zz, xs, ys, nfx, nfy):
        """Group the samples of one lattice edge by the pair of bodies they join; pairs from different regions are the line itself."""
        for a in np.unique(bl):
            for b in np.unique(br):
                if a < 0 or b < 0 or reg[a] != reg[b]:
                    continue
                m = (bl == a) & (br == b) & (code_l == reg[a]) & (code_r == reg[b])
                if not m.any():
                    continue
                fl.add(int(a), int(b), m.sum() * p, nfx, nfy, xs[m].mean(), ys[m].mean(), zz[m], p, n_inv)

    for j, i in zip(*np.nonzero(band), strict=True):
        r0, c0 = j * k, i * k
        if i > 0 and band[j, i - 1]:
            bl, br = body[r0 : r0 + k, c0 - 1], body[r0 : r0 + k, c0]
            code_l, code_r = code[r0 : r0 + k, c0 - 1], code[r0 : r0 + k, c0]
            zz = np.maximum(z[r0 : r0 + k, c0 - 1], z[r0 : r0 + k, c0])
            xs = np.full(k, bed.x0 + i * dx)
            ys = y[r0 : r0 + k]
            parts(bl, br, zz, xs, ys, 1.0, 0.0)
        if j > 0 and band[j - 1, i]:
            bl, br = body[r0 - 1, c0 : c0 + k], body[r0, c0 : c0 + k]
            code_l, code_r = code[r0 - 1, c0 : c0 + k], code[r0, c0 : c0 + k]
            zz = np.maximum(z[r0 - 1, c0 : c0 + k], z[r0, c0 : c0 + k])
            xs = x[c0 : c0 + k]
            ys = np.full(k, bed.y0 + j * dx)
            parts(bl, br, zz, xs, ys, 0.0, 1.0)
        ids = per_cell[(j, i)]
        if len(ids) == 2:
            a, b = ids
            for seg in segs if segs is not None else [(p0, th, -1e12, 1e12) for p0, th in lines]:
                p0, th, tlo, thi = seg
                ch = chord(bed.x0 + i * dx, bed.y0 + j * dx, dx, p0, th, tlo, thi)
                if ch is None:
                    continue
                ax, ay, bx, by = ch
                ln = float(np.hypot(bx - ax, by - ay))
                prof, pix = face_samples(bed, ax, ay, bx, by)
                nfx, nfy = -np.sin(th), np.cos(th)
                if nfx * (ce["cx"][b] - ce["cx"][a]) + nfy * (ce["cy"][b] - ce["cy"][a]) < 0:
                    nfx, nfy = -nfx, -nfy
                fl.add(a, b, ln, nfx, nfy, 0.5 * (ax + bx), 0.5 * (ay + by), prof, pix, n_inv)
                if segs is None:
                    break
    me = finish(ce, fl.done(), dx)
    me.split_cells = sum(1 for v in per_cell.values() if len(v) > 1)
    return me


def quality(me, dx):
    """Skew angle between the centre line and the face normal, smallest cell, smallest dn."""
    ang = np.degrees(np.arctan2(np.hypot(me.sx, me.sy), me.dn))
    return dict(skew_max=float(ang.max()), skew_p95=float(np.percentile(ang, 95)), area_min=float(me.Ac.min() / dx**2), dn_min=float(me.dn.min() / dx))
