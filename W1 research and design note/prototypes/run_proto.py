"""Experiments on the C-grid prototype; each prints one verdict line. Usage: run_proto.py [names...]"""
from __future__ import annotations

import sys
import time

import numpy as np
from scipy.optimize import brentq

from cgrid_proto import G, Model, level_from_hbar


def bed_from_fn(fn, nx, ny, dx, k):
    """Sub-grid bed samples at pixel centres."""
    p = dx / k
    x = (np.arange(nx * k) + 0.5) * p
    y = (np.arange(ny * k) + 0.5) * p
    X, Y = np.meshgrid(x, y)
    return fn(X, Y)


def lake(second=True):
    rng = np.random.default_rng(1)
    nx, ny, k, dx = 60, 60, 8, 10.0
    zs = rng.normal(0, 1.0, (ny * k, nx * k))
    from scipy.ndimage import gaussian_filter

    zs = gaussian_filter(zs, 6) * 40 + 1500.0 + 0.002 * np.arange(ny * k)[:, None]
    m = Model(zs, k, dx, 0.03, second=second)
    level = float(np.median(zs))
    # hbar from the sub-grid for a flat level, wet and dry cells both exist
    hb = np.maximum(level - zs, 0.0).reshape(ny, k, nx, k).mean(axis=(1, 3))
    for j in range(ny):
        for i in range(nx):
            lo, hi = 0.0, hb[j, i] * 2 + 1.0
            tgt = level - m.zmin[j, i]
            if tgt <= 0:
                hb[j, i] = 0.0
                continue
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                if level_from_hbar(mid, m.H[j, i], m.dtab[j, i]) < tgt:
                    lo = mid
                else:
                    hi = mid
            hb[j, i] = 0.5 * (lo + hi)
    m.set_hbar(hb)
    v0 = m.h.sum()
    m.run(600.0)
    print(
        f"lake: steps {m.nsteps}, max|u| {max(abs(m.u).max(), abs(m.v).max()):.2e} m/s, "
        f"mass {m.h.sum() / v0 - 1:+.1e}, wet {np.mean(m.h > 0):.2f}"
    )


def stoker_exact(x, t, hL, hR, x0):
    cL, cR = np.sqrt(G * hL), np.sqrt(G * hR)

    def f(hm):
        um = 2 * (cL - np.sqrt(G * hm))
        s = um * hm / (hm - hR)
        return um - (s - G * hR * (hR + hm) / (4 * s) * 0 - 0) + (s - (G * (hm + hR) / (2) * (hm / hR)) ** 0.5 * 1) * 0 + 0 * s + (
            (G * (hm - hR) * (hm + hR) / (2 * hR * hm)) ** 0.5 * (hm - hR) * -1 + um
        ) * 0 + (um - (hm - hR) * np.sqrt(G * (hm + hR) / (2 * hm * hR)))

    # um from both sides: left rarefaction and right shock
    def g(hm):
        return 2 * (cL - np.sqrt(G * hm)) - (hm - hR) * np.sqrt(G * (hm + hR) / (2 * hm * hR))

    hm = brentq(g, hR, hL)
    um = 2 * (cL - np.sqrt(G * hm))
    s = hm * um / (hm - hR)
    cm = np.sqrt(G * hm)
    xi = (x - x0) / max(t, 1e-9)
    h = np.where(xi < -cL, hL, 0.0)
    fan = (xi >= -cL) & (xi < um - cm)
    h = np.where(fan, (2 * cL - xi) ** 2 / (9 * G), h)
    h = np.where((xi >= um - cm) & (xi < s), hm, h)
    h = np.where(xi >= s, hR, h)
    return h, hm, s


def dam_break(hR, name, second=True, nx=400, dx=2.5):
    ny = 6
    k = 1
    zs = np.zeros((ny * k, nx * k))
    m = Model(zs, k, dx, 1e-6, second=second, sheet=False, cfl=0.45, eps_e=1e-5, phi_mode=4)
    # frictionless: conveyance huge; n tiny
    x = (np.arange(nx) + 0.5) * dx
    x0 = 0.5 * nx * dx
    hb = np.where(x < x0, 10.0, hR)
    m.set_hbar(np.tile(hb, (ny, 1)))
    t = 30.0
    m.run(t)
    num = m.h[ny // 2]
    if hR > 0:
        ex, hm, s = stoker_exact(x, t, 10.0, hR, x0)
        err = np.sqrt(np.mean((num - ex) ** 2))
        l1 = np.mean(np.abs(num - ex))
        # front
        front_num = x[np.argmax(num < 0.5 * (hm + hR))]
        print(
            f"{name}: rmse {err:.3f} L1 {l1:.3f} m; plateau {num[int((x0 + 0.5 * s * t) / dx)]:.3f} vs {hm:.3f}; "
            f"shock {front_num - x0:.1f} vs {s * t:.1f} m; steps {m.nsteps}"
        )
    else:
        c0 = np.sqrt(G * 10.0)
        xi = (x - x0) / t
        ex = np.where(xi < -c0, 10.0, (2 * c0 - xi) ** 2 / (9 * G))
        ex = np.where(xi > 2 * c0, 0.0, ex)
        err = np.sqrt(np.mean((num - ex) ** 2))
        front = x[np.nonzero(num > 0.01)[0].max()] - x0
        print(f"{name}: rmse {err:.3f} m; front {front:.1f} vs {2 * c0 * t:.1f} m; steps {m.nsteps}")


def weir(sheet=True, second=True):
    """Thin crest across a flat channel: head H upstream, dry downstream."""
    nx, ny, k, dx = 120, 4, 4, 5.0
    P = 3.0

    def bed(X, Y):
        z = np.zeros_like(X)
        z[(X > 300) & (X < 300 + dx / k)] = P
        return z

    zs = bed_from_fn(bed, nx, ny, dx, k)
    m = Model(zs, k, dx, 0.012, second=second, sheet=sheet, cfl=0.4)
    H0 = 1.0
    x = (np.arange(nx) + 0.5) * dx
    hb = np.where(x < 300, P + H0, 0.0)
    m.set_hbar(np.tile(hb, (ny, 1)))
    # keep the upstream reservoir level by a source at the far left
    i_crest = int(300 / dx)

    def hold(mm):
        mm.h[:, :2] = P + H0
        for j in range(ny):
            for i in range(2):
                mm.d[j, i] = P + H0

    m.run(300.0, on_step=hold)
    q = m.Qx[1, i_crest + 1] / dx
    hup = m.h[1, i_crest - 3] - P
    qcrit = (2.0 / 3.0) * np.sqrt(2 * G / 3.0) * hup**1.5
    print(f"weir: q {q:.3f} vs critical-flow {qcrit:.3f} m2/s (ratio {q / qcrit:.3f}), head {hup:.3f} m, crest faces {int((m.Cx > 0).sum())}, steps {m.nsteps}")


def overland(S=0.05, dx=20.0, k=20, sheet=True, n=0.05, L=2000.0, rain_mmh=50.0):
    """Rain on a long plane: steady outflow and storage against the kinematic-wave exact solution."""
    nx = int(L / dx)
    ny = 3

    def bed(X, Y):
        return (L - X) * S

    zs = bed_from_fn(bed, nx, ny, dx, k)
    # add a wall of inactive ground right of the plane is not needed: outlet is an open end via a deep sink cell
    m = Model(zs, k, dx, n, second=False, sheet=sheet, cfl=0.45)
    i = rain_mmh / 1000.0 / 3600.0
    m.src[:, :-1] = i
    tc = (n * L / (S**0.5 * i ** (2.0 / 3.0))) ** 0.6  # kinematic time of concentration
    qe = i * L
    he = (qe * n / S**0.5) ** 0.6
    # exact mean depth at equilibrium: integral of (i x n / S^.5)^.6 / L = (0.625) he
    hmean_exact = 0.625 * he
    hist = []

    def probe(mm):
        mm.h[:, -1] = 0.0
        mm.d[:, -1] = 0.0
        hist.append((mm.t, mm.Qx[1, nx - 1] / dx))

    t_end = 2.5 * tc
    t0 = time.time()
    m.run(t_end, dtmax=2.0, on_step=probe)
    hist = np.array(hist)
    qend = hist[-1, 1]
    t50 = hist[np.argmax(hist[:, 1] > 0.5 * qe), 0]
    hmean = m.h[1, :-1].mean()
    print(
        f"overland S={S} dx={dx} sheet={sheet}: tc {tc / 60:.0f} min, t50 {t50 / 60:.0f} min, q {qend:.2e} vs {qe:.2e}; "
        f"mean depth {hmean * 1000:.2f} vs {hmean_exact * 1000:.2f} mm; steps {m.nsteps}, {time.time() - t0:.1f}s"
    )


def channel(theta_deg=45.0, dx=20.0, k=20, Q=20.0, b=30.0, S=0.002, n=0.03, **kw):
    """Rectangular channel at an angle to the grid, carved 5 m into a plain tilted along the axis."""
    nx, ny = 120, 120
    th = np.radians(theta_deg)
    ca, sa = np.cos(th), np.sin(th)
    p = dx / k

    def bed(X, Y):
        xc, yc = X - 0.5 * nx * dx, Y - 0.5 * ny * dx
        s = xc * ca + yc * sa
        t = -xc * sa + yc * ca
        z = 5.0 - s * S
        return z - 5.0 * (np.abs(t) < b / 2)

    zs = bed_from_fn(bed, nx, ny, dx, k)
    m = Model(zs, k, dx, n, second=True, sheet=True, cfl=0.45, **kw)

    # normal depth
    def f(y):
        A = b * y
        R = b * y / (b + 2 * y)
        return A * R ** (2 / 3) * S**0.5 / n - Q

    yn = brentq(f, 0.01, 20)
    # initial: normal depth in the channel, sources at the upstream end, sink at the downstream end
    xc = (np.arange(nx) + 0.5) * dx - 0.5 * nx * dx
    yc = (np.arange(ny) + 0.5) * dx - 0.5 * ny * dx
    Xc, Yc = np.meshgrid(xc, yc)
    s = Xc * ca + Yc * sa
    t = -Xc * sa + Yc * ca
    # hbar from the sub-grid for a level parallel to the channel bed at yn
    lev_s = (-(((np.arange(nx * k) + 0.5) * p - 0.5 * nx * dx) * ca) * 0)  # unused
    Xs = (np.arange(nx * k) + 0.5) * p - 0.5 * nx * dx
    Ys = (np.arange(ny * k) + 0.5) * p - 0.5 * ny * dx
    XS, YS = np.meshgrid(Xs, Ys)
    ss = XS * ca + YS * sa
    level = 0.0 - ss * S + yn
    hb = np.maximum(level - zs, 0.0).reshape(ny, k, nx, k).mean(axis=(1, 3))
    m.set_hbar(hb)
    lim = 0.45 * nx * dx
    upstream = (s < -lim + 40 * 0 - 0) & (np.abs(t) < b)
    down = (s > lim - 150) & (np.abs(t) < 2 * b)
    up = (s > -lim) & (s < -lim + 150) & (np.abs(t) < b / 2 + dx)
    nup = up.sum()
    m.src[up] = Q / (nup * dx * dx)
    keep = (np.abs(t) < 3 * b)

    def drain(mm):
        # hold the downstream end at normal depth: reset cells to the initial state
        mm.h[down] = hb[down]
        for jj, ii in zip(*np.nonzero(down)):
            from cgrid_proto import level_from_hbar

            mm.d[jj, ii] = level_from_hbar(mm.h[jj, ii], mm.H[jj, ii], mm.dtab[jj, ii])

    m.run(3000.0, on_step=drain)
    mid = (np.abs(s) < 0.15 * nx * dx) & (np.abs(t) < 0.71 * dx)
    eta = m.zmin + m.d
    zb = -s * S
    dep = (eta - zb)[mid]
    # discharge through a section normal to x or y at the centre
    qsec = np.abs(m.Qx[:, nx // 2][np.abs(t[:, nx // 2]) < 3 * b]).sum()
    if theta_deg > 0:
        qsec = abs(m.Qx[:, nx // 2].sum())
    print(
        f"channel b={b} theta={theta_deg:.0f} dx={dx}: depth {np.mean(dep):.3f} +- {np.std(dep):.3f} vs normal {yn:.3f} m; "
        f"Q section {qsec:.2f} vs {Q}; steps {m.nsteps}"
    )


def main(names):
    tests = {
        "lake": lake,
        "stoker": lambda: dam_break(2.0, "stoker"),
        "stoker1": lambda: dam_break(2.0, "stoker first order", second=False),
        "ritter": lambda: dam_break(0.0, "ritter"),
        "weir": weir,
        "overland": lambda: [overland(sheet=False), overland(sheet=True)],
        "overland2": lambda: [overland(S=0.2, sheet=True), overland(S=0.01, sheet=True), overland(S=0.05, dx=40.0, sheet=True)],
        "chan2": lambda: [channel(45.0, b=60.0, Q=60.0, phi_mode=3), channel(45.0, b=120.0, Q=150.0, phi_mode=3), channel(30.0, b=60.0, Q=60.0, phi_mode=3), channel(45.0, b=60.0, Q=60.0, dx=10.0, k=10, phi_mode=3), channel(45.0, b=30.0, Q=20.0, phi_mode=3)],
        "channel": lambda: [channel(0.0, b=60.0, Q=60.0), channel(30.0, b=60.0, Q=60.0), channel(45.0, b=60.0, Q=60.0), channel(45.0, b=60.0, Q=60.0, dx=10.0, k=10)],
    }
    for n in names or tests:
        tests[n]()


if __name__ == "__main__":
    main(sys.argv[1:])
