"""Does the fix hurt anything? Baseline and mirror on the cases where a zero-velocity face is common: fronts, shocks, thin rain, a real rain-on-grid.

Ritter dam break onto dry ground, Stoker onto a wet bed, rain on a 5 % plane against the kinematic wave, and the synthetic valley of run_valley at 20 m.
Run on one thread beside the matrix.
"""
import sys

sys.path.insert(0, ".")
import numpy as np
from scipy.optimize import brentq

from lattice import G, Lattice
from run_valley import H, N_MAN, RAIN, SECTIONS, T_END, T_RAIN, W, WADI_X, terrain


def strip(h0_fn, nx, dx, t_end, mirror):
    ny = 4
    k = 2
    z = np.zeros((ny * k + 2, nx * k + 2))
    m = Lattice(z, k, dx, 1e-4, ny, nx, mirror=mirror)
    xc = (np.arange(nx) + 0.5) * dx - 0.5 * nx * dx
    m.set_depth(np.tile(h0_fn(xc), (ny, 1)))
    m.advance(t_end)
    return xc, m.field(m.h)[1]


def ritter(x, t, h0=4.0):
    c = np.sqrt(G * h0)
    h = np.where(x <= -c * t, h0, 0.0)
    fan = (x > -c * t) & (x < 2 * c * t)
    h[fan] = (2 * c - x[fan] / t) ** 2 / (9 * G)
    return h


def stoker(x, t, hl=4.0, hr=1.0):
    def f(cm):
        hm = cm * cm / G
        return 2 * (np.sqrt(G * hl) - cm) - (hm - hr) * np.sqrt(0.5 * G * (hm + hr) / (hm * hr))

    cm = brentq(f, np.sqrt(G * hr) * 1.0001, np.sqrt(G * hl))
    hm = cm * cm / G
    um = 2 * (np.sqrt(G * hl) - cm)
    ss = um * hm / (hm - hr)
    c0 = np.sqrt(G * hl)
    h = np.where(x <= -c0 * t, hl, hr)
    fan = (x > -c0 * t) & (x <= (um - cm) * t)
    h[fan] = (2 * c0 - x[fan] / t) ** 2 / (9 * G)
    h[(x > (um - cm) * t) & (x <= ss * t)] = hm
    return h, hm


def plane(mirror, sheet=1):
    """Rain on a 5 % plane: storage against the kinematic wave at equilibrium, dx 20 m."""
    nx, ny, k, dx = 40, 8, 20, 20.0
    S, n = 0.05, 0.05
    x = (np.arange(nx * k + 2) - 1 + 0.5) * dx / k
    z = np.tile(-S * x, (ny * k + 2, 1))
    m = Lattice(z, k, dx, n, ny, nx, mirror=mirror, sheet=sheet)
    r = 50e-3 / 3600.0
    m.set_source(np.full((ny, nx), r))
    m.set_boundary(np.full(ny, 0) + np.arange(ny), np.full(ny, nx - 1), np.zeros(ny), np.zeros(ny), np.ones(ny, np.int64))
    m.advance(6000.0)
    L = (nx - 1) * dx
    q = lambda xx: r * xx  # noqa: E731
    xs = np.linspace(0, L, 2000)
    y = (q(xs) * n / np.sqrt(S)) ** 0.6
    vol = np.trapezoid(y, xs) * ny * dx
    return m.field(m.h)[:, :-1].sum() * dx * dx / vol


def valley(mirror, dx=20.0):
    z = terrain()
    k = int(dx)
    ny, nx = int(H / dx), int(W / dx)
    zp = np.pad(z, 1, mode="edge")[: ny * k + 2, : nx * k + 2]
    m = Lattice(zp, k, dx, N_MAN, ny, nx, mirror=mirror)
    m.set_source(np.where(np.arange(ny)[:, None] > 0, RAIN, 0.0) * np.ones((ny, nx)))
    m.set_boundary(np.zeros(nx, np.int64), np.arange(nx), np.zeros(nx), np.zeros(nx), np.ones(nx, np.int64))
    t = 0.0
    qmax = 0.0
    dmax = 0.0
    j, i = int(SECTIONS[0] / dx), int(WADI_X / dx)
    zb = z[int(SECTIONS[0]), int(WADI_X)]
    last = 0.0
    while t < T_END - 1e-6:
        t += 30.0
        if last < T_RAIN <= t:
            m.advance(T_RAIN)
            m.set_source(np.zeros((ny, nx)))
        m.advance(t)
        last = t
        q = float(m.field(m.qy)[1, :].sum())
        qmax = max(qmax, abs(q))
        dmax = max(dmax, float(m.zmin[j, i] + m.field(m.d)[j, i] - zb))
    return qmax, dmax, m.nsteps


if __name__ == "__main__":
    nx, dx = 400, 1.0
    for mirror in (False, True):
        tag = "mirror" if mirror else "base"
        x, h = strip(lambda xc: np.where(xc < 0, 4.0, 0.0), nx, dx, 12.0, mirror)
        print(f"{tag:7s} Ritter  L1/h0 {np.mean(np.abs(h - ritter(x, 12.0))) / 4.0:.5f}", flush=True)
        x, h = strip(lambda xc: np.where(xc < 0, 4.0, 1.0), nx, dx, 12.0, mirror)
        hs, hm = stoker(x, 12.0)
        print(f"{tag:7s} Stoker  L1/h0 {np.mean(np.abs(h - hs)) / 4.0:.5f} plateau {np.median(h[(x > 15) & (x < 20)]):.3f} analytic {hm:.3f}", flush=True)
        print(f"{tag:7s} plane 5 % storage / kinematic wave {plane(mirror):.4f}, section s3 {plane(mirror, 3):.4f}", flush=True)
        q, d, ns = valley(mirror)
        print(f"{tag:7s} valley 20 m: peak {q:.3f} m3/s, wadi depth {d:.4f} m, steps {ns}", flush=True)
