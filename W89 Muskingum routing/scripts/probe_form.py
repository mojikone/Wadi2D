"""Which form HEC-HMS 4.12 computes: the plain coefficient form of its Technical Reference Manual (eq. 6), each
subreach with K / n and the same X, at the control step, against HMS's own series; and variants where they part.

Usage: ``python probe_form.py``; reads ``tests/data/hms_muskingum``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_muskingum"
DT_HOURS = 5.0 / 60.0


def plain(inflow: np.ndarray, k: float, x: float, steps: int, clip: bool = False, start: str = "inflow") -> np.ndarray:
    ks = k / steps
    denominator = 2.0 * ks * (1.0 - x) + DT_HOURS
    c1 = (DT_HOURS - 2.0 * ks * x) / denominator
    c2 = (DT_HOURS + 2.0 * ks * x) / denominator
    c3 = (2.0 * ks * (1.0 - x) - DT_HOURS) / denominator
    flow = inflow.copy()
    for _ in range(steps):
        out = np.empty_like(flow)
        out[0] = flow[0] if start == "inflow" else 0.0
        for t in range(1, len(flow)):
            out[t] = c1 * flow[t] + c2 * flow[t - 1] + c3 * out[t - 1]
            if clip and out[t] < 0.0:
                out[t] = 0.0
        flow = out
    return flow


def main() -> None:
    cases = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))
    for case, p in cases.items():
        table = np.genfromtxt(DATA / f"{case}.csv", delimiter=",", names=True)
        inflow, hms = table["inflow"], table["outflow"]
        ours = plain(inflow, p["k_hours"], p["x"], p["subreaches"])
        clipped = plain(inflow, p["k_hours"], p["x"], p["subreaches"], clip=True)
        worst = int(np.argmax(np.abs(ours - hms)))
        print(
            f"{case:14s} K {p['k_hours']:5.2f} X {p['x']:4.2f} n {p['subreaches']:3d}  HMS peak {hms.max():10.5f} "
            f"min {hms.min():9.5f}  plain: max|d| {np.abs(ours - hms).max():.3e} at step {worst} (ours {ours[worst]:.5f}, "
            f"HMS {hms[worst]:.5f}), ours min {ours.min():.5f}; clipped at 0: max|d| {np.abs(clipped - hms).max():.3e}"
        )
        print("   first 8 HMS :", np.round(hms[:8], 5))
        print("   first 8 ours:", np.round(ours[:8], 5))


if __name__ == "__main__":
    main()
