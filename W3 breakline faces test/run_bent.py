"""A bent channel. Two straight reaches meeting at a mitre, walls on the polylines; bed a plane dipping along the bisector, so both reaches have the
same slope and no step in the bed. Downstream reach: Manning normal depth holds. Upstream reach: depth carries the bend's head loss, so its
reference is the 5 m lattice with the fix, 12 cells across. Every option sees the same pixels.
"""
import csv
import sys

sys.path.insert(0, ".")
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import cases as C
from graph import Graph
from lattice import Lattice
from meshes import Bed, mesh_cut, mesh_lattice, mesh_snap
from meshes_poly import mesh_tri

S_R = 0.002
L = 1050.0
B, Q = 60.0, 60.0
WINDOW_UP = (-700.0, -300.0)
WINDOW_DN = (300.0, 700.0)


class Bend:
    def __init__(self, a1, a2):
        self.a1, self.a2 = np.radians(a1), np.radians(a2)
        self.phi = self.a2 - self.a1
        self.beta = 0.5 * (self.a1 + self.a2)
        self.S0 = S_R / np.cos(self.phi / 2)
        self.t1 = np.array([np.cos(self.a1), np.sin(self.a1)])
        self.t2 = np.array([np.cos(self.a2), np.sin(self.a2)])
        self.n1 = np.array([-self.t1[1], self.t1[0]])
        self.n2 = np.array([-self.t2[1], self.t2[0]])
        self.nb = np.array([-np.sin(self.beta), np.cos(self.beta)])

    def frame(self, x, y):
        """Along-centreline coordinate (0 at the bend), signed distance from it, mitred at the bisector."""
        first = x * (self.t1[0] + self.t2[0]) + y * (self.t1[1] + self.t2[1]) < 0
        s = np.where(first, x * self.t1[0] + y * self.t1[1], x * self.t2[0] + y * self.t2[1])
        t = np.where(first, x * self.n1[0] + y * self.n1[1], x * self.n2[0] + y * self.n2[1])
        return s, t

    def plane(self, x, y):
        return -self.S0 * (x * np.cos(self.beta) + y * np.sin(self.beta))

    def polys(self):
        out = []
        m = self.nb * (B / 2) / np.cos(self.phi / 2)
        for sgn in (1.0, -1.0):
            out.append(np.array([-(L + 300) * self.t1 + sgn * self.n1 * B / 2, sgn * m, (L + 300) * self.t2 + sgn * self.n2 * B / 2]))
        return out


def pixels(bd, side, dx, k):
    p = dx / k
    x = (np.arange(side * k + 2) - 1 + 0.5) * p - 0.5 * side * dx
    X, Y = np.meshgrid(x, x)
    s, t = bd.frame(X, Y)
    return bd.plane(X, Y) + C.WALL * (np.abs(t) >= B / 2)


def run_one(a):
    name, a1, a2 = a
    bd = Bend(a1, a2)
    yn = C.normal_depth(B, 0.0, Q, S=S_R)
    fine = name.startswith("ref")
    dx = 5.0 if fine else 20.0
    side = 512 if fine else 128
    k = int(dx)
    z = pixels(bd, side, dx, k)
    xc = (np.arange(side) + 0.5) * dx - 0.5 * side * dx
    Xc, Yc = np.meshgrid(xc, xc)
    Sc, Tc = bd.frame(Xc, Yc)
    band = np.abs(Tc) < B / 2 + 6 * dx
    if name in ("a", "m", "ref a", "ref m"):
        m = Lattice(z, k, dx, C.N, side, side, band=band, mirror=name.endswith("m"))
        sc, tc = Sc, Tc
        cx, cy = Xc, Yc
        nc = int(band.sum())
        level = bd.plane(cx, cy) + yn
        hb = np.where(np.abs(tc) < B / 2 + 2 * dx, m.hbar_at_level(level), 0.0)
        m.set_depth(hb)
        up = (sc > -L) & (sc < -L + 120) & (np.abs(tc) < B / 2 + dx)
        rate = np.zeros((side, side))
        rate[up] = Q / (up.sum() * dx * dx)
        m.set_source(rate)
        down = (sc > L - 120) & (sc < L) & (np.abs(tc) < B + 3 * dx)
        jj, ii = np.nonzero(down)
        m.set_boundary(jj, ii, np.maximum((level - m.zmin)[down], 0.0), hb[down])
        rd = lambda: m.zmin + m.field(m.d)  # noqa: E731
    else:
        bed = Bed(z, k, dx, side, side)
        polys = bd.polys()
        half = 0.5 * side * dx
        if name == "P":
            me, dxr, kw = mesh_lattice(bed, C.N, band, dx), dx, dict(sheet=1)
        elif name == "b":
            me, dxr, kw = mesh_snap(bed, C.N, band, None, polys=polys), dx, dict(sheet=2)
        elif name == "c":

            def code_fn(X, Y):
                _, t = bd.frame(X, Y)
                return (t > B / 2).astype(np.int64) + 2 * (t > -B / 2).astype(np.int64)

            segs = []
            for poly in polys:
                for a_, b_ in zip(poly[:-1], poly[1:], strict=True):
                    ln = float(np.hypot(*(b_ - a_)))
                    segs.append((tuple(a_), float(np.arctan2(*(b_ - a_)[::-1])), 0.0, ln))
            me, dxr, kw = mesh_cut(bed, C.N, band, None, code_fn=code_fn, segs=segs), dx, dict(sheet=2)
        else:
            h = 20.0 if name == "t20" else 26.3

            def keep(x, y, pad):
                _, t = bd.frame(x, y)
                return (np.abs(t) < B / 2 + 6 * dx + pad) & (np.abs(x) <= half + 1e-9) & (np.abs(y) <= half + 1e-9)

            me, dxr, kw = mesh_tri(bed, C.N, polys, h, keep, (-half, half, -half, half)), h, dict(sheet=3)
        m = Graph(me, dxr, **kw)
        cx, cy = me.cx, me.cy
        sc, tc = bd.frame(cx, cy)
        nc = me.Ac.size
        level = bd.plane(cx, cy) + yn
        hb = np.where(np.abs(tc) < B / 2 + 2 * dx, m.hbar_at_level(level), 0.0)
        m.set_depth(hb)
        up = (sc > -L) & (sc < -L + 120) & (np.abs(tc) < B / 2 - 0.5)
        m.src[up] = Q / me.Ac[up].sum()
        down = (sc > L - 120) & (sc < L) & (np.abs(tc) < B + 3 * dx)
        cells = np.nonzero(down)[0]
        m.bcell = cells.astype(np.int64)
        m.bkind = np.zeros(cells.size, np.int64)
        m.bd0 = np.maximum((level - m.zmin)[down], 0.0)
        m.bh0 = hb[down]
        rd = lambda: m.zmin + m.d  # noqa: E731
    du, dd = [], []
    try:
        for t in np.arange(3600.0, 4001.0, 100.0):
            m.advance(float(t))
            eta = rd()
            dep = eta - bd.plane(cx, cy)
            core = np.abs(tc) < 0.71 * dx if not fine else np.abs(tc) < 15.0
            du.append(dep[(sc > WINDOW_UP[0]) & (sc < WINDOW_UP[1]) & core].mean())
            dd.append(dep[(sc > WINDOW_DN[0]) & (sc < WINDOW_DN[1]) & core].mean())
    except FloatingPointError as e:
        return dict(name=name, defl=a2 - a1, up=np.nan, dn=np.nan, err_dn=np.nan, dt=np.nan, nc=nc, blew=str(e))
    return dict(name=name, defl=a2 - a1, up=float(np.mean(du)), dn=float(np.mean(dd)), err_dn=(float(np.mean(dd)) / yn - 1) * 100, dt=m.t / m.nsteps, nc=nc, blew="")


if __name__ == "__main__":
    pairs = ((15.0, 45.0), (15.0, 75.0), (7.0, 97.0), (5.0, 140.0))
    names = ("ref m", "ref a", "a", "m", "P", "b", "c", "t20", "t26")
    jobs = [(n, a, b) for a, b in pairs for n in names]
    with ProcessPoolExecutor(11) as ex:
        res = list(ex.map(run_one, jobs))
    with open("results/bent.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["name", "defl", "up", "dn", "err_dn", "dt", "nc", "blew"])
        w.writeheader()
        w.writerows(res)
    ref = {r["defl"]: r for r in res if r["name"] == "ref m"}
    print("deflection option | downstream reach error vs Manning % | upstream depth minus 5 m reference, m | dt | cells")
    for r in res:
        print(f"{r['defl']:6.0f} {r['name']:6s} {r['err_dn']:+7.2f} {r['up'] - ref[r['defl']]['up']:+7.3f} {r['dt']:6.3f} {r['nc']:6d} {r['blew']}")
