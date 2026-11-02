"""Still water, dry bank behind a line, crest overtopping, for every option.

Still water: rough bed at 1,500 m, walls at 30 degrees off the lattice phase, uniform level, some cells dry. Largest speed after 300 s.
Dry bank: flat ground, a thin dyke 2 m wide and 3 m high, water raised against it to 2.7 m. Volume and largest depth on the far side after 1,000 s.
Overtopping: same dyke, level held 0.3 m over the crest on one side, free on the other; discharge per true metre of line over ideal critical flow.
On the lattice the dyke is today's crest line: a staircase of faces with a length factor. On aligned meshes it is the bed under the edges on the line.
"""
import csv
import sys

sys.path.insert(0, ".")
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import cases as C
from graph import Graph
from lattice import CW, Lattice
from meshes import Bed, mesh_cut, mesh_lattice, mesh_snap
from meshes_poly import mesh_tri, steps_between

SIDE, DX, K = C.SIDE, C.DX, C.K
P = DX / K
OPTS = ("a", "m", "ms3", "b", "c", "t20", "t26")
SETTINGS = {"b": dict(sheet=2), "c": dict(sheet=2), "t20": dict(sheet=3), "t26": dict(sheet=3)}


def coords(side=SIDE):
    x = (np.arange(side * K + 2) - 1 + 0.5) * P - 0.5 * side * DX
    return np.meshgrid(x, x)


def build(opt, z, lines, band, polys, keepw, thdeg, off):
    bed = Bed(z, K, DX, SIDE, SIDE)
    if opt == "b":
        return mesh_snap(bed, C.N, band, lines), DX
    if opt == "c":
        return mesh_cut(bed, C.N, band, lines), DX
    h = 20.0 if opt == "t20" else 26.3
    half = 0.5 * SIDE * DX
    th = np.radians(thdeg)
    ca, sa = np.cos(th), np.sin(th)

    def keep(x, y, pad):
        tt = -x * sa + y * ca - off
        return (np.abs(tt) < keepw + pad) & (np.abs(x) <= half + 1e-9) & (np.abs(y) <= half + 1e-9)

    return mesh_tri(bed, C.N, polys, h, keep, (-half, half, -half, half)), h


def still(opt):
    theta, b, off = 30.0, 60.0, 5.0
    rng = np.random.default_rng(1)
    X, Y = coords()
    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    z = C.bed(theta, b, 0.0, off) + 1500.0
    z += 0.4 * np.sin(X / 37.0) * np.cos(Y / 53.0) + 0.1 * rng.standard_normal(z.shape)
    level = 1500.1
    sc, tc = C.centres(theta, off)
    band = np.abs(tc) < b / 2 + 6 * DX
    nv = np.array([-sa, ca])
    lines = [(tuple(nv * (off + b / 2)), th), (tuple(nv * (off - b / 2)), th)]
    t2 = np.array([ca, sa])
    polys = [np.array([np.array(p0) - 2000 * t2, np.array(p0) + 2000 * t2]) for p0, _ in lines]
    if opt in ("a", "m", "ms3"):
        m = Lattice(z, K, DX, C.N, SIDE, SIDE, band=band, mirror=opt != "a", sheet=3 if opt == "ms3" else 1)
        m.set_depth(m.hbar_at_level(np.full((SIDE, SIDE), level)))
        h0 = m.h.copy()
        m.advance(300.0)
        umax = max(np.abs(m.u).max(), np.abs(m.v).max())
        return dict(option=opt, umax=float(umax), dvol=float(np.abs(m.h - h0).max()), dry=float((m.field(m.h)[band] == 0).mean()))
    me, dxr = build(opt, z, lines, band, polys, b / 2 + 6 * DX, theta, off)
    m = Graph(me, dxr, **SETTINGS[opt])
    m.set_depth(m.hbar_at_level(np.full(me.Ac.size, level)))
    h0 = m.h.copy()
    m.advance(300.0)
    return dict(option=opt, umax=float(np.abs(m.u).max()), dvol=float(np.abs(m.h - h0).max()), dry=float((m.h == 0).mean()))


def staircase_faces(theta, off):
    """Today's crest line: walk the lattice with the production rule; returns west-face and north-face masks and length factors."""
    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    nv = np.array([-sa, ca]) * off
    a = nv - 1900 * np.array([ca, sa])
    b = nv + 1900 * np.array([ca, sa])
    half = 0.5 * SIDE * DX
    c0 = (round((a[1] + half) / DX), round((a[0] + half) / DX))
    c1 = (round((b[1] + half) / DX), round((b[0] + half) / DX))
    walk = [c0, *steps_between(c0, c1)]
    wx = np.zeros((SIDE, SIDE), bool)
    wy = np.zeros((SIDE, SIDE), bool)
    n_edges = 0
    for p, q in zip(walk[:-1], walk[1:], strict=True):
        dj, di = q[0] - p[0], q[1] - p[1]
        if dj == 0:
            j, i = p[0], min(p[1], q[1])
            if 0 <= j < SIDE and 0 <= i < SIDE:
                wy[j, i] = True
                n_edges += 1
        else:
            j, i = min(p[0], q[0]), p[1]
            if 0 <= j < SIDE and 0 <= i < SIDE:
                wx[j, i] = True
                n_edges += 1
    factor = 1.0 / (abs(ca) + abs(sa))
    return wx, wy, factor


def side_cells(wx, wy, seed):
    """Flood fill over faces not on the staircase, from a seed cell."""
    seen = np.zeros((SIDE, SIDE), bool)
    stack = [seed]
    seen[seed] = True
    while stack:
        j, i = stack.pop()
        for jn, inn, blocked in (
            (j, i + 1, wx[j, i + 1] if i + 1 < SIDE else True),
            (j, i - 1, wx[j, i]),
            (j + 1, i, wy[j + 1, i] if j + 1 < SIDE else True),
            (j - 1, i, wy[j, i]),
        ):
            if 0 <= jn < SIDE and 0 <= inn < SIDE and not blocked and not seen[jn, inn]:
                seen[jn, inn] = True
                stack.append((jn, inn))
    return seen


def dyke(opt, theta, off):
    crest = 3.0
    X, Y = coords()
    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    T = -X * sa + Y * ca - off
    z = np.where(np.abs(T) <= 1.0, crest, 0.0)
    sc, tc = C.centres(theta, off)
    band = np.abs(tc) < 200.0
    half_len = 900.0
    out = dict(option=opt, theta=theta, offset=off)
    nv = np.array([-sa, ca]) * off
    lines = [(tuple(nv), th)]
    t2 = np.array([ca, sa])
    polys = [np.array([nv - 2000 * t2, nv + 2000 * t2])]
    if opt in ("a", "m", "ms3"):
        wx, wy, f = staircase_faces(theta, off)
        xcrest = np.where(wx, crest, np.nan)
        ycrest = np.where(wy, crest, np.nan)
        flat = np.zeros_like(z)  # on the lattice the crest is the face object, as production
        mk = lambda: Lattice(  # noqa: E731
            flat, K, DX, C.N, SIDE, SIDE, mask=band, mirror=opt != "a", sheet=3 if opt == "ms3" else 1, xcrest=xcrest, ycrest=ycrest, xlen=np.where(wx, f, 1.0),
            ylen=np.where(wy, f, 1.0), xc=np.where(wx, CW, 0.0), yc=np.where(wy, CW, 0.0),
        )  # fmt: skip
        j0, i0 = np.unravel_index(np.argmin(np.abs(tc - 100.0) + np.abs(sc)), tc.shape)
        wet = side_cells(wx, wy, (int(j0), int(i0))) & band
        far = band & ~wet
        m = mk()
        hb = np.where(wet, 2.0, 0.0)
        m.set_depth(hb)
        rate = np.where(wet & (np.abs(tc) > 40) & (np.abs(tc) < 180), 0.7 / 600.0 * 200.0 / 140.0, 0.0)
        m.set_source(rate)
        m.advance(600.0)
        m.set_source(np.zeros((SIDE, SIDE)))
        m.advance(1000.0)
        hf = m.field(m.h)
        out.update(far_vol=float(hf[far].sum() * DX * DX), far_dmax=float(hf[far].max()), near_level=float(hf[wet & (np.abs(tc) < 100)].mean()))
        # overtopping
        m = mk()
        up = wet & (tc > 120)
        dn_ = far & (tc < -120)
        m.set_depth(np.where(wet, 3.3, 0.0))
        jj, ii = np.nonzero(up)
        j2, i2 = np.nonzero(dn_)
        m.set_boundary(np.concatenate((jj, j2)), np.concatenate((ii, i2)), np.concatenate((np.full(jj.size, 3.3), np.zeros(j2.size))),
                       np.concatenate((np.full(jj.size, 3.3), np.zeros(j2.size))), np.concatenate((np.zeros(jj.size, np.int64), np.ones(j2.size, np.int64))))  # fmt: skip
        qs = []
        for t in (500.0, 600.0, 700.0, 800.0):
            m.advance(t)
            qx, qy = m.field(m.qx), m.field(m.qy)
            s_mid = np.abs(sc) < half_len * 0.6
            a = wet
            q = ((qx[:, 1:] * (a[:, :-1] & ~a[:, 1:] & s_mid[:, 1:])).sum() - (qx[:, 1:] * (~a[:, :-1] & a[:, 1:] & s_mid[:, 1:])).sum())
            q += ((qy[1:, :] * (a[:-1, :] & ~a[1:, :] & s_mid[1:, :])).sum() - (qy[1:, :] * (~a[:-1, :] & a[1:, :] & s_mid[1:, :])).sum())
            qs.append(abs(float(q)))
        length = (s_mid * (np.abs(tc) < DX)).sum() * DX * DX / (2 * DX)
        out.update(q_ratio=float(np.mean(qs[-2:]) / (length * CW * 0.3**1.5)))
        return out
    me, dxr = build(opt, z, lines, band, polys, 200.0, theta, off)
    gx, gy = getattr(me, "gx", me.cx), getattr(me, "gy", me.cy)
    t_c = -gx * sa + gy * ca - off
    s_c = gx * ca + gy * sa
    wet = t_c > 0.0
    far = t_c < 0.0
    m = Graph(me, dxr, **SETTINGS[opt])
    m.set_depth(np.where(wet, m.hbar_at_level(np.full(me.Ac.size, 2.0)), 0.0))
    m.src[:] = np.where(wet & (np.abs(t_c) > 40) & (np.abs(t_c) < 180), 0.7 / 600.0 * 200.0 / 140.0, 0.0)
    m.advance(600.0)
    m.src[:] = 0.0
    m.advance(1000.0)
    out.update(far_vol=float((m.h * me.Ac)[far].sum()), far_dmax=float(m.h[far].max()), near_level=float(m.h[wet & (np.abs(t_c) < 100)].mean()))
    m = Graph(me, dxr, **SETTINGS[opt])
    m.set_depth(np.where(wet, m.hbar_at_level(np.full(me.Ac.size, 3.3)), 0.0))
    up = t_c > 120
    dn_ = t_c < -120
    cells = np.nonzero(up | dn_)[0]
    m.bcell = cells.astype(np.int64)
    m.bkind = np.zeros(cells.size, np.int64)
    m.bd0 = np.where(up[cells], 3.3, 0.0)
    m.bh0 = np.where(up[cells], 3.3, 0.0)
    s_mid = np.abs(s_c) < half_len * 0.6
    qs = []
    for t in (500.0, 600.0, 700.0, 800.0):
        m.advance(t)
        a = wet[me.L]
        b = wet[me.R]
        sel = (a != b) & s_mid[me.L]
        qs.append(abs(float((m.q[sel] * np.where(a[sel], 1.0, -1.0)).sum())))
    out.update(q_ratio=float(np.mean(qs[-2:]) / (2 * half_len * 0.6 * CW * 0.3**1.5)))
    return out


def job(a):
    try:
        return a[0], still(a[1]) if a[0] == "still" else dyke(a[1], a[2], a[3])
    except Exception as e:  # recorded, not hidden
        return a[0], dict(option=a[1], theta=a[2] if len(a) > 2 else None, offset=a[3] if len(a) > 3 else None, failed=f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    jobs = [("still", o) for o in OPTS] + [("dyke", o, th, off) for o in OPTS for th in (30.0, 45.0) for off in (0.0, 5.0)]
    with ProcessPoolExecutor(11) as ex:
        res = list(ex.map(job, jobs))
    print("still water: option, largest speed m/s, largest depth change m, dry share")
    for k, r in res:
        if k == "still":
            print(r)
    print("dyke: option theta offset | far side volume m3, far largest mean depth m, near level m, overtopping ratio")
    for k, r in res:
        if k == "dyke":
            print(r)
    with open("results/still_dry.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["kind", "option", "theta", "offset", "umax", "dvol", "dry", "far_vol", "far_dmax", "near_level", "q_ratio", "failed"], extrasaction="ignore")
        w.writeheader()
        for k, r in res:
            w.writerow(dict(kind=k, **r))
