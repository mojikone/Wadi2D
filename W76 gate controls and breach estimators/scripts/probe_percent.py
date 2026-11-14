"""Which opening HMS applies at a reported time on a Percent Time Series gate: HMS's spillway flow against W62's gate
law at HMS's own pool levels, the opening taken as the maximum times the gage's percent at candidate times.

Usage: ``python probe_percent.py`` (both cases). Prints the worst relative difference of each candidate by regime.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
K = 4.42869
CREST, WIDTH, WEIR_C, MAX_B = 108.0, 20.0, 1.6, 2.0
LAWS = {
    "gate_percent_sluice": (0.6, 0.0, 0.0, 1.0, 0.5),
    "gate_percent_radial": (0.7, 3.0, 0.16, 0.72, 0.62),
}


def load(name: str) -> dict[str, np.ndarray]:
    path = DATA / name
    names = path.read_text(encoding="utf-8").splitlines()[0].split(",")
    data = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    return {n: data[:, k] for k, n in enumerate(names)}


def law(h: np.ndarray, b: np.ndarray, c: float, t: float, te: float, be: float, he: float) -> np.ndarray:
    hp = np.clip(h, 0.0, None)
    weir = WEIR_C * WIDTH * hp**1.5
    gate = c * K * WIDTH * (t**te if te else 1.0) * b**be * hp**he
    ratio = np.divide(hp, b, out=np.zeros_like(hp), where=b > 0)
    share = np.clip((ratio - 1.0) / 0.25, 0.0, 1.0)
    return np.where(hp <= 0, 0.0, weir + share * (gate - weir))


def main() -> None:
    gage = load("w76_percent.csv")
    for case, parameters in LAWS.items():
        hms = load(f"{case}.csv")
        minutes = np.arange(len(hms["elevation_m"])) * 5.0
        h = hms["elevation_m"] - CREST
        q = hms["spill_1"]
        candidates = {
            "linear at t": np.interp(minutes, gage["hour"] * 60, gage["percent"]),
            "linear at t-5": np.interp(minutes - 5, gage["hour"] * 60, gage["percent"]),
            "previous hour": np.interp(np.floor(minutes / 60) * 60, gage["hour"] * 60, gage["percent"]),
            "next hour": np.interp(np.ceil(minutes / 60) * 60, gage["hour"] * 60, gage["percent"]),
        }
        print(case, "peak", q.max())
        for name, percent in candidates.items():
            b = MAX_B * percent / 100.0
            value = law(h, b, *parameters)
            rel = np.abs(value - q) / max(q.max(), 1e-9)
            worst = int(np.argmax(rel))
            print(f"   {name:14s} worst of peak {rel.max():.3e} at step {worst} (H/B {h[worst] / b[worst]:.3f})")


if __name__ == "__main__":
    main()
