"""Prototype that chose the guards (W29): the Todini scheme in storage form against the HMS path on Block 2 reaches.

CAP "d" is the diffusion floor kept in the engine, "k" the rejected travel-time cap, anything else the raw scheme; VMIN the
velocity floor. Run with the repo on PYTHONPATH. The engine kernel is the one of record; this is the record of the search."""

import math
from pathlib import Path

import numpy as np

from wadi2d.hms import daa_fpart, load_basin, open_dss
from wadi2d.hydrology.from_hms import basin_from_hms
from wadi2d.hydrology.routing import MuskingumCunge
from wadi2d.hydrology.routing_kernel import normal_depth

FLOOR = 0.01
VMIN = 0.1


def hydraulics(q, w, m, slope, conv, depth):
    qq = max(q, FLOOR)
    y = normal_depth(qq, w, m, conv, depth, 20, 1e-9)
    area = (w + m * y) * y
    top = w + 2 * m * y
    wet = 2 * math.sqrt(1 + m * m)
    per = w + wet * y
    c = qq / area * (5 / 3 - 2 / 3 * area / per * wet / top)
    v = max(qq / area, VMIN)
    beta = c / v
    return y, area, top, c, beta


CAP = "d"


def params(cs, ds, dt):
    k = dt / cs
    if CAP == "k":
        k = min(k, dt / (1 - ds)) if ds < 1 else k
    elif CAP == "d":
        ds = max(ds, 1.0 - cs)
    return k * (1 - ds) / 2, k * (1 + ds) / 2


def mct_cells(inflow, n_cells, dt, dx, w, m, slope, rough):
    conv = math.sqrt(slope) / rough
    up = inflow.copy()
    for _ in range(n_cells):
        out = np.empty_like(up)
        out[0] = up[0]
        depth = 1.0
        q_t = 0.5 * (up[0] + out[0])
        depth, _a, top, c, beta = hydraulics(q_t, w, m, slope, conv, depth)
        cs_t = c / beta * dt / dx
        ds_t = max(q_t, FLOOR) / (beta * top * slope * c * dx)
        ke_t, k1e_t = params(cs_t, ds_t, dt)
        for n in range(1, len(up)):
            i_old, i_new, o_old = up[n - 1], up[n], out[n - 1]
            guess = o_old + (i_new - i_old)
            for _it in range(30):
                q_n = 0.5 * (i_new + guess)
                depth, _a, top, c, beta = hydraulics(q_n, w, m, slope, conv, depth)
                cs_n = c / beta * dt / dx
                ds_n = max(q_n, FLOOR) / (beta * top * slope * c * dx)
                ke_n, k1e_n = params(cs_n, ds_n, dt)
                o_new = ((-2 * ke_n + dt) * i_new + (2 * ke_t + dt) * i_old + (2 * k1e_t - dt) * o_old) / (
                    2 * k1e_n + dt
                )
                if abs(o_new - guess) < 1e-3 * abs(o_new) + 1e-12:
                    guess = o_new
                    break
                guess = o_new
            out[n] = guess
            ke_t, k1e_t = ke_n, k1e_n
        STORE[0] += ke_t * up[-1] + k1e_t * out[-1]
        up = out
    return out


STORE = [0.0]


def mct(mc: MuskingumCunge, inflow, dt_min):
    dt = dt_min * 60
    cells, dx, sub = mc.grid(dt)
    times = np.arange(len(inflow), dtype=float)
    fine = np.arange((len(inflow) - 1) * sub + 1, dtype=float) / sub
    out = mct_cells(
        np.interp(fine, times, inflow), cells, dt / sub, dx, mc.bottom_width_m, mc.side_slope, mc.slope, mc.roughness
    )
    return out[::sub]


def report(name, mc, inflow, dt_min):
    hms = mc.route(inflow, dt_min)
    STORE[0] = 0.0
    con = mct(mc, inflow, dt_min)
    dt = dt_min * 60
    vin = np.trapezoid(inflow) * dt
    vout = np.trapezoid(con) * dt
    print(f"   identity in - out - S_end = {vin - vout - STORE[0]:.3e} m3 of {vin:.1f}; S_end {STORE[0]:.1f}")
    print(
        f"{name:12s} in {inflow.max():8.2f}@{np.argmax(inflow) * dt_min / 60:6.2f}h  "
        f"hms {hms.max():8.2f}@{np.argmax(hms) * dt_min / 60:6.2f}h out/in {hms.sum() / inflow.sum():.4f} | "
        f"mct {con.max():8.2f}@{np.argmax(con) * dt_min / 60:6.2f}h out/in {con.sum() / inflow.sum():.6f} "
        f"min {con.min():.3f} drained(<1e-6) at {np.argmax(np.r_[con, 0.0][np.argmax(con):] < 1e-6) * dt_min / 60 + np.argmax(con) * dt_min / 60:.1f}h"
    )


folder = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")
basin = basin_from_hms(load_basin(folder / "Basin_1.basin"))
with open_dss(folder / "DA_100yr_B1.dss") as dss:
    for r in ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]:
        inflow = dss.read_timeseries(r, "FLOW-COMBINE", daa_fpart("DA 100yr B1", r)).values
        q = np.r_[0.0, inflow, np.zeros(2000)]
        report(r, basin.elements[r].routing, q, 5.0)


def tri(peak, n=3000):
    return np.r_[np.linspace(0, peak, 3), np.linspace(peak, 0, 3)[1:], np.zeros(n)]


for peak in (8.0, 80.0, 800.0):
    report(f"R1 tri{peak:g}", basin.elements["R1"].routing, tri(peak), 5.0)
    report(f"R6 tri{peak:g}", basin.elements["R6"].routing, tri(peak), 5.0)
test = MuskingumCunge(3000.0, 0.01, 0.04, 10.0, 1.0, 2.0)
for peak in (8.0, 80.0, 800.0):
    report(f"test tri{peak:g}", test, tri(peak), 1.0)
