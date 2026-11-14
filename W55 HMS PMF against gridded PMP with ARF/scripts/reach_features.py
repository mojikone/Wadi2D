"""Features of the short reaches of Basin 3, to find what sets HMS's doubled grid on RIJ-R11 and RIJ-R17."""

from __future__ import annotations

import math
from pathlib import Path

from scipy.optimize import brentq

from wadi2d.hydrology.replication import _Project

HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\HEC_HMS_Block_02.hms")
DT = 300.0
_, engine = _Project(HMS).model("Basin 3")


def hydraulics(r, depth):
    b, z, s, n = r.bottom_width_m, r.side_slope, r.slope, r.roughness
    area = depth * (b + z * depth)
    perimeter = b + 2 * depth * math.sqrt(1 + z * z)
    top = b + 2 * z * depth
    q = area ** (5 / 3) / perimeter ** (2 / 3) * math.sqrt(s) / n
    return q, top, area


def celerity(r, depth, h=1e-6):
    q1, _, a1 = hydraulics(r, depth)
    q2, _, a2 = hydraulics(r, depth + h)
    return (q2 - q1) / (a2 - a1)


for name, element in engine.basin.elements.items():
    r = getattr(element, "routing", None)
    if r is None or not hasattr(r, "index_celerity"):
        continue
    ratio = r.length_m / (r.index_celerity * DT)
    if ratio > 1.3:
        continue
    depth = brentq(lambda y: celerity(r, y) - r.index_celerity, 1e-6, 100.0)
    q, top, _ = hydraulics(r, depth)
    d = q / (top * r.slope * r.index_celerity)
    cells, dx, k = r.grid(DT)
    courant = r.index_celerity * DT / k / dx
    x = 0.5 * (1 - d / dx)
    print(f"{name:9s} ratio={ratio:5.3f} S={r.slope:.5f} B={r.bottom_width_m:6.1f} y={depth:6.3f} Q={q:8.2f}"
          f" D={d:8.1f} D/dx={d / dx:6.3f} X={x:+.3f} C={courant:.3f} C+X? {courant + 2 * x:.3f}")
