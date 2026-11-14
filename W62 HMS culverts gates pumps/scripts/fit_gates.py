"""The gate law HMS applies, read off its own output: spillway flow against candidate laws at HMS's own pool levels.

Prints, by regime of the head over the crest H against the opening B, the worst relative difference of each candidate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
G = 9.80665
CREST, B, WIDTH, WEIR_C = 108.0, 1.5, 20.0, 1.6


def load(case: str) -> dict[str, np.ndarray]:
    path = DATA / f"{case}.csv"
    names = path.read_text(encoding="utf-8").splitlines()[0].split(",")
    data = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    return {n: data[:, k] for k, n in enumerate(names)}


def sluice(h: np.ndarray) -> dict[str, np.ndarray]:
    hp = np.clip(h, 0.0, None)
    return {
        "C W B sqrt(2gH)": 0.6 * WIDTH * B * np.sqrt(2 * G * hp),
        "C W B sqrt(2g(H-B/2))": 0.6 * WIDTH * B * np.sqrt(2 * G * np.clip(h - B / 2, 0, None)),
        "weir Cw L H^1.5": WEIR_C * WIDTH * hp**1.5,
    }


def radial(h: np.ndarray) -> dict[str, np.ndarray]:
    hp = np.clip(h, 0.0, None)
    return {
        "C sqrt(2g) W T^TE B^BE H^HE": 0.7 * np.sqrt(2 * G) * WIDTH * 3.0**0.16 * B**0.72 * hp**0.62,
        "weir Cw L H^1.5": WEIR_C * WIDTH * hp**1.5,
    }


def main() -> None:
    case = sys.argv[1]
    hms = load(case)
    h = hms["elevation_m"] - CREST
    q = hms["spill_1"]
    laws = radial(h) if "radial" in case else sluice(h)
    for label, mask in (("H<=0", h <= 0), ("0<H<B", (h > 0) & (h < B)), ("H>=B", h >= B)):
        if not mask.any():
            continue
        print(f"{label}: {mask.sum()} steps, H {h[mask].min():.3f}..{h[mask].max():.3f}, Q {q[mask].min():.3f}..{q[mask].max():.3f}")
        for name, value in laws.items():
            rel = np.abs(value[mask] - q[mask]) / np.maximum(np.abs(q[mask]), 1e-9)
            print(f"   {name:32s} worst rel {rel.max():.3e}")
    order = np.argsort(h)
    for k in order[:: max(len(order) // 25, 1)]:
        print(f"   H {h[k]:8.4f} Q {q[k]:10.4f} " + " ".join(f"{v[k]:10.4f}" for v in laws.values()))


if __name__ == "__main__":
    main()
