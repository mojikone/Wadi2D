"""The rotated-channel case of W1 prototypes/channel_scan.py, stand-alone: same bed, inflow, outlet and depth measure."""
from __future__ import annotations

import time

import numpy as np
from scipy.optimize import brentq

SIDE = 128
DX = 20.0
K = 20
S = 0.002
N = 0.03
WALL = 5.0
T_END = 4000.0
# width in cells: b, Q. 3 and 6 are the recorded cases; 12 keeps the unit discharge of 6
WIDTHS = {1.5: (30.0, 20.0), 3: (60.0, 60.0), 6: (120.0, 150.0), 12: (240.0, 300.0)}


def normal_depth(b, bank, Q, S=S, n=N):
    def f(y):
        area = (b + bank * y) * y
        per = b + 2 * y * np.sqrt(1 + bank**2)
        return area * (area / per) ** (2 / 3) * S**0.5 / n - Q

    return brentq(f, 0.01, 20)


def normal_depth_wide(b, bank, Q, S=S, n=N):
    """What a sub-grid strip conveyance holds: no wall friction, Lotter sum across the section."""

    def f(y):
        conv = b * y ** (5 / 3)
        if bank > 0:
            conv += 2 * bank * (3 / 8) * y ** (8 / 3)
        return conv * S**0.5 / n - Q

    return brentq(f, 0.01, 20)


def bed(theta, b, bank, offset=0.0, side=SIDE, dx=DX, k=K):
    """Pixels (side*k+2)^2, the extra row and column on each side as production; offset moves the axis across, m."""
    nx = ny = side
    p = dx / k
    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    x = (np.arange(nx * k + 2) - 1 + 0.5) * p - 0.5 * nx * dx
    y = (np.arange(ny * k + 2) - 1 + 0.5) * p - 0.5 * ny * dx
    X, Y = np.meshgrid(x, y)
    s = X * ca + Y * sa
    t = -X * sa + Y * ca - offset
    above = np.clip((np.abs(t) - b / 2) / max(bank, 1e-6), 0.0, WALL) if bank > 0 else WALL * (np.abs(t) >= b / 2)
    return -s * S + above


def centres(theta, offset=0.0, side=SIDE, dx=DX):
    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    xc = (np.arange(side) + 0.5) * dx - 0.5 * side * dx
    Xc, Yc = np.meshgrid(xc, xc)
    return Xc * ca + Yc * sa, -Xc * sa + Yc * ca - offset


def section_q(qx, qy, sc, s0):
    """Flow out of the cells below s0, whatever the angle: sum of face discharges across the mask edge, m3/s."""
    m = sc < s0
    qe = (qx[:, 1:] * (m[:, :-1] & ~m[:, 1:])).sum() - (qx[:, 1:] * (~m[:, :-1] & m[:, 1:])).sum()
    qs = (qy[1:, :] * (m[:-1, :] & ~m[1:, :])).sum() - (qy[1:, :] * (~m[:-1, :] & m[1:, :])).sum()
    return float(qe + qs)


def setup(model, theta, b, bank, Q, yn, offset=0.0, side=SIDE, dx=DX):
    """Same start, inflow and outlet as channel_scan.run."""
    sc, tc = centres(theta, offset, side, dx)
    level = -sc * S + yn
    hb = model.hbar_at_level(level)
    hb = np.where(np.abs(tc) < b / 2 + bank * yn + 2 * dx, hb, 0.0)
    model.set_depth(hb)
    lim = 0.45 * side * dx
    up = (sc > -lim) & (sc < -lim + 120) & (np.abs(tc) < b / 2 + dx)
    rate = np.zeros((side, side))
    rate[up] = Q / (up.sum() * dx * dx)
    model.set_source(rate)
    down = (sc > lim - 120) & (sc < lim) & (np.abs(tc) < b + 3 * dx)
    jj, ii = np.nonzero(down)
    model.set_boundary(jj, ii, np.maximum((level - model.zmin)[down], 0.0), hb[down])
    return sc, tc


def measure(model, sc, tc, yn, Q, side=SIDE, dx=DX):
    mid = (np.abs(sc) < 0.15 * side * dx) & (np.abs(tc) < 0.71 * dx)
    eta = model.zmin + model.field(model.d)
    dep = (eta + sc * S)[mid]
    qs = [section_q(model.field(model.qx), model.field(model.qy), sc, s0) for s0 in (-0.15 * side * dx, 0.0, 0.15 * side * dx)]
    return float(np.mean(dep)), float(np.mean(qs))


def report(tag, theta, cells, bank, depth, yn, qsec, Q, nsteps, secs, t_end, extra=None):
    r = {
        "tag": tag, "theta": theta, "cells": cells, "bank": bank, "depth": depth, "yn": yn, "err_pct": (depth / yn - 1) * 100,
        "qerr_pct": (qsec / Q - 1) * 100, "nsteps": nsteps, "dt_mean": t_end / nsteps, "secs": secs,
    }
    if extra:
        r.update(extra)
    return r
