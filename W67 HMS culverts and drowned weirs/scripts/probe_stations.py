"""Hypothesis for the part-full barrel that reaches its crown: HMS steps the profile over N equal reaches by the
standard step, and once a reach's upstream depth would pass the crown the barrel is full from that reach's
downstream station to the inlet. Prints ours - HMS on the box_oc rows whose normal depth is at the crown, per N.

Usage: ``python probe_stations.py``.
"""

from pathlib import Path

import numpy as np

from wadi2d.hydrology import culvert as cv

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
FT = cv.FEET_PER_METRE
G = cv.GRAVITY_FT
pipe = cv.Barrel(cv.BOX, 3 * FT, 3 * FT, 300 * FT, 100.3 * FT, 100 * FT, 0.02, 0.5, 1.0)
names = (DATA / "culvert_box_oc.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
data = np.loadtxt(DATA / "culvert_box_oc.csv", delimiter=",", skiprows=1)
s = {n: data[:, j] for j, n in enumerate(names)}
flow = s["outlet_1"] * cv.CFS_PER_M3S / 2
pool = s["elevation_m"] * FT


def state(q, y):
    a, _, p = pipe.section(np.array([y]))
    a, p = a[0], p[0]
    return y + q * q / (2 * G * a * a), (q * pipe.n / (cv.MANNING_FT * a * (a / p) ** (2 / 3))) ** 2


def headwater(q, reaches, rule):
    y = cv.critical_depth(pipe, q)
    dx = pipe.length / reaches
    e0, f0 = state(q, y)
    for k in range(reaches):
        # solve e1 = e0 + (0.5 (f0 + f1) - S0) dx for y1 in (y, D) on the subcritical branch
        lo, hi = y, pipe.rise * (1 - 1e-9)
        e_hi, f_hi = state(q, hi)
        if e_hi - e0 - (0.5 * (f0 + f_hi) - pipe.slope) * dx < 0:
            start = k if rule == "down" else k + 1
            head, friction = cv._full(pipe, q, pipe.length - start * dx)
            return pipe.outlet + pipe.slope * start * dx + pipe.rise + (1 + pipe.entrance) * head + friction
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            e1, f1 = state(q, mid)
            if e1 - e0 - (0.5 * (f0 + f1) - pipe.slope) * dx > 0:
                hi = mid
            else:
                lo = mid
        y = 0.5 * (lo + hi)
        e0, f0 = state(q, y)
    a = pipe.section(np.array([y]))[0][0]
    return pipe.inlet + y + (1 + pipe.entrance) * q * q / (2 * G * a * a)


rows = [j for j in range(len(flow)) if flow[j] > 0]
for rule in ("down", "up"):
    for reaches in (5, 10, 15, 20, 30, 50):
        gaps = np.array([(headwater(flow[j], reaches, rule) - pool[j]) / FT for j in rows])
        print(f"{rule} N {reaches:3d}: max {gaps.max():+.4f} min {gaps.min():+.4f} rms {np.sqrt(np.mean(gaps**2)):.4f}")
