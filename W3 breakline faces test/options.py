"""One entry point for every option: build, run, measure. All options read the same pixels, inflow, outlet and depth measure."""
from __future__ import annotations

import time

import numpy as np

import cases as C
from graph import Graph
from lattice import Lattice
from meshes import Bed, mesh_cut, mesh_lattice, mesh_snap, quality
from meshes_poly import mesh_tri

SAMPLES = np.arange(3600.0, 4001.0, 100.0)


def lines_for(theta, b, offset):
    """The two breaklines at the toes (walls), as (point, angle)."""
    th = np.radians(theta)
    nv = np.array([-np.sin(th), np.cos(th)])
    return [(tuple(nv * (offset + b / 2)), th), (tuple(nv * (offset - b / 2)), th)]


def band_of(theta, b, bank, offset):
    _, tc = C.centres(theta, offset)
    return np.abs(tc) < b / 2 + bank * C.WALL + 6 * C.DX


def graph_setup(m, theta, b, bank, Q, yn, offset):
    """As cases.setup, on centroids. The source stays inside the channel: on bodies behind a wall it would strand."""
    me = m.me
    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    sc = me.cx * ca + me.cy * sa
    tc = -me.cx * sa + me.cy * ca - offset
    gx, gy = getattr(me, "gx", me.cx), getattr(me, "gy", me.cy)
    sg = gx * ca + gy * sa
    tg = -gx * sa + gy * ca - offset
    level = -sc * C.S + yn
    hb = m.hbar_at_level(level)
    hb = np.where(np.abs(tg) < b / 2 + bank * yn + 2 * C.DX, hb, 0.0)
    m.set_depth(hb)
    lim = 0.45 * C.SIDE * C.DX
    up = (sg > -lim) & (sg < -lim + 120) & (np.abs(tg) < b / 2 - 0.5)
    m.src[:] = 0.0
    m.src[up] = Q / me.Ac[up].sum()
    down = (sg > lim - 120) & (sg < lim) & (np.abs(tg) < b + 3 * C.DX)
    cells = np.nonzero(down)[0]
    m.bcell = cells.astype(np.int64)
    m.bkind = np.zeros(cells.size, np.int64)
    m.bd0 = np.maximum((level - m.zmin)[down], 0.0)
    m.bh0 = hb[down]
    return sc, tc


def graph_measure(m, sc, tc):
    me = m.me
    mid = (np.abs(sc) < 0.15 * C.SIDE * C.DX) & (np.abs(tc) < 0.71 * C.DX)
    dep = (m.zmin + m.d + sc * C.S)[mid]
    qs = []
    for s0 in (-0.15 * C.SIDE * C.DX, 0.0, 0.15 * C.SIDE * C.DX):
        below = sc < s0
        a, b = below[me.L], below[me.R]
        qs.append(float(m.q[a & ~b].sum() - m.q[~a & b].sum()))
    return float(np.mean(dep)), float(np.mean(qs))


def run(option, theta, cells, bank, offset=0.0, t_end=4000.0, **kw):
    """option: a or d... (lattice kernel, kw go to Lattice); P (lattice as polygons); b (snap); c (cut). Returns a record."""
    b, Q = C.WIDTHS[cells]
    yn = C.normal_depth(b, bank, Q)
    yw = C.normal_depth_wide(b, bank, Q)
    z = C.bed(theta, b, bank, offset)
    band = band_of(theta, b, bank, offset)
    t0 = time.time()
    extra = {}
    samples = SAMPLES if t_end == 4000.0 else t_end - 400.0 + np.arange(0.0, 401.0, 100.0)
    if option == "lattice":
        m = Lattice(z, C.K, C.DX, C.N, C.SIDE, C.SIDE, band=band, **kw)
        sc, tc = C.setup(m, theta, b, bank, Q, yn, offset)
        nelem = int(m.alist.size)
        rd = lambda: C.measure(m, sc, tc, yn, Q)  # noqa: E731
    else:
        bed = Bed(z, C.K, C.DX, C.SIDE, C.SIDE)
        lines = lines_for(theta, b, offset)
        gkw = {q: kw.pop(q) for q in list(kw) if q in ("sheet", "adv", "skew", "cfl", "a_min")}
        if option == "P":
            me = mesh_lattice(bed, C.N, band, C.DX)
        elif option == "b":
            me = mesh_snap(bed, C.N, band, lines, **kw)
            extra["bad_cells"] = me.bad
        elif option == "c":
            me = mesh_cut(bed, C.N, band, lines, **kw)
            extra["split_cells"] = me.split_cells
        elif option == "tri":
            h = kw.pop("h")
            half = 0.5 * C.SIDE * C.DX
            width = b / 2 + bank * C.WALL + 6 * C.DX
            th = np.radians(theta)
            ca, sa = np.cos(th), np.sin(th)

            def keep(x, y, pad):
                tt = -x * sa + y * ca - offset
                return (np.abs(tt) < width + pad) & (np.abs(x) <= half + 1e-9) & (np.abs(y) <= half + 1e-9)

            polys = [np.array([np.array(p0) - 2000.0 * np.array([ca, sa]), np.array(p0) + 2000.0 * np.array([ca, sa])]) for p0, _ in lines]
            me = mesh_tri(bed, C.N, polys, h, keep, (-half, half, -half, half))
            extra.update(steiner=me.steiner, unresolved=me.unresolved, clipped_dn=me.clipped_dn, neg_dn=me.neg_dn, nfaces=me.L.size)
            gkw["dxref"] = h
        else:
            raise ValueError(option)
        extra.update(quality(me, C.DX))
        extra["nfaces"] = me.L.size
        dxref = gkw.pop("dxref", C.DX)
        m = Graph(me, dxref, **gkw)
        sc, tc = graph_setup(m, theta, b, bank, Q, yn, offset)
        nelem = me.Ac.size
        rd = lambda: graph_measure(m, sc, tc)  # noqa: E731
    t1 = time.time()
    deps, qs = [], []
    blew = ""
    try:
        for t in samples:
            m.advance(float(t))
            d_, q_ = rd()
            deps.append(d_)
            qs.append(q_)
    except FloatingPointError as e:
        blew = str(e)
    t2 = time.time()
    if not deps or not np.isfinite(deps[-1]):
        return dict(option=option, theta=theta, cells=cells, bank=bank, offset=offset, err=np.nan, err_strip=np.nan, qerr=np.nan, dt=np.nan, blew=blew or "nan", **extra)
    dep = float(np.mean(deps))
    return dict(
        option=option, theta=theta, cells=cells, bank=bank, offset=offset, err=(dep / yn - 1) * 100, err_strip=(dep / yw - 1) * 100,
        qerr=(float(np.mean(qs)) / Q - 1) * 100, dt=m.t / m.nsteps, nsteps=m.nsteps, nelem=nelem, build_s=t1 - t0, run_s=t2 - t1,
        ns_per_cellstep=(t2 - t1) / (m.nsteps * nelem) * 1e9, blew=blew, **extra,
    )  # fmt: skip


def directional_scale(theta, b, bank, offset, band):
    """Option d3: a per-face friction factor folded into the table, no kernel change.

    For flow parallel to the line a face needs dEta/D, with D = t.(cR - cL) / t_n and c the channel-side centroid of each cell. Faces of uncut
    cells get D = dx. Vertical walls and bank toes use the same line. Cost: table build only; zero bytes.
    """
    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    ny = nx = C.SIDE
    k, dx = C.K, C.DX
    p = dx / k
    x = -0.5 * nx * dx + (np.arange(nx * k) + 0.5) * p
    X, Y = np.meshgrid(x, x)
    T = -X * sa + Y * ca - offset
    wet = np.abs(T) < b / 2
    S = X.reshape(ny, k, nx, k).sum(axis=(1, 3)) * 0 + 0
    w = wet.reshape(ny, k, nx, k)
    cnt = w.sum(axis=(1, 3)).astype(float)
    cx = (X * wet).reshape(ny, k, nx, k).sum(axis=(1, 3)) / np.maximum(cnt, 1)
    cy = (Y * wet).reshape(ny, k, nx, k).sum(axis=(1, 3)) / np.maximum(cnt, 1)
    fx = np.ones((ny, nx))
    fy = np.ones((ny, nx))
    has = cnt > 0
    ax = has[:, 1:] & has[:, :-1]
    tdc = ca * (cx[:, 1:] - cx[:, :-1]) + sa * (cy[:, 1:] - cy[:, :-1])
    if ca > 1e-6:
        fx[:, 1:] = np.where(ax, np.clip(tdc / ca / dx, 0.25, 4.0), 1.0)
    ay = has[1:, :] & has[:-1, :]
    tdc = ca * (cx[1:, :] - cx[:-1, :]) + sa * (cy[1:, :] - cy[:-1, :])
    if sa > 1e-6:
        fy[1:, :] = np.where(ay, np.clip(tdc / sa / dx, 0.25, 4.0), 1.0)
    return fx, fy


def run_dir(theta, cells, bank, offset=0.0, **kw):
    b, _ = C.WIDTHS[cells]
    band = band_of(theta, b, bank, offset)
    fx, fy = directional_scale(theta, b, bank, offset, band)
    r = run("lattice", theta, cells, bank, offset, fscx=fx, fscy=fy, **kw)
    return r
