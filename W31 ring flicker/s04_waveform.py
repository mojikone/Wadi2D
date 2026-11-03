"""The shape of the flicker: its period, the depths at the cells that take the inflow, and whether the two move
against each other. Reads the series of an ``s02`` variant; prints one block per ringed subbasin.

usage: python s04_waveform.py <variant> [hours round the peak, default 0.5]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
G = 9.81
DX = 40.0


def series(folder: Path, kind: str, name: str) -> tuple[np.ndarray, np.ndarray]:
    rows = np.loadtxt(folder / "series" / f"{kind}_{name}.csv", delimiter=",", skiprows=1, ndmin=2)
    return rows[:, 0], rows[:, 1]


def period(t: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    """Dominant period, s, by the spectrum of the detrended signal, and the share of variance it holds."""
    dt = float(np.median(np.diff(t)))
    width = round(300.0 / dt) | 1
    x = x - np.convolve(x, np.ones(width) / width, "same")
    x = x - x.mean()
    spectrum = np.abs(np.fft.rfft(x)) ** 2
    freq = np.fft.rfftfreq(x.size, dt)
    spectrum[0] = 0.0
    k = int(spectrum.argmax())
    return (1.0 / freq[k] if freq[k] > 0 else np.inf), float(spectrum[k] / spectrum.sum())


def main(argv: list[str]) -> None:
    variant = argv[0]
    half = float(argv[1]) * 3600.0 if len(argv) > 1 else 1800.0
    folder = HERE / "runs" / f"block2_{variant}"
    found = json.loads((HERE / "injection_cells.json").read_text(encoding="utf-8"))
    out = {}
    for name, item in found.items():
        t, q = series(folder, "line", f"{name}_ring")
        q = np.abs(q)
        k = int(q.argmax())
        window = (t >= t[k] - half) & (t <= t[k] + half)
        tw, qw = t[window], q[window]
        ring_period, share = period(tw, qw)
        row = {
            "peak": round(float(q[k]), 1), "hour": round(float(t[k]) / 3600.0, 2),
            "ring_period_s": round(ring_period, 1), "ring_period_share": round(share, 2),
            "ring_swing": round(float(qw.max() - qw.min()), 1), "cells": [],
        }  # fmt: skip
        depths = []
        for n, cell in enumerate(item["cells"]):
            label = f"{name}_cell{n}_{'in' if cell['inside_ring'] else 'out'}"
            try:
                tp, d = series(folder, "point", label)
            except OSError:
                continue
            dw = d[(tp >= t[k] - half) & (tp <= t[k] + half)]
            p, s = period(tp[(tp >= t[k] - half) & (tp <= t[k] + half)], dw)
            depths.append(dw)
            row["cells"].append({
                "cell": label, "zmin": cell["zmin"], "depth_mean": round(float(dw.mean()), 2),
                "depth_swing": round(float(dw.max() - dw.min()), 2), "period_s": round(p, 1), "share": round(s, 2),
            })  # fmt: skip
        if len(depths) == 2 and depths[0].size == depths[1].size:
            a, b = depths[0] - depths[0].mean(), depths[1] - depths[1].mean()
            row["cells_correlation"] = round(float(np.corrcoef(a, b)[0, 1]), 2)
        if depths:
            h = float(np.mean([d.mean() for d in depths]))
            row["sloshing_period_2dx_over_c_s"] = round(2.0 * DX / np.sqrt(G * max(h, 1e-3)), 1)
        out[name] = row
        print(name, json.dumps(row))
    (HERE / f"waveform_{variant}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
