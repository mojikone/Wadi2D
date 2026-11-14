"""The drowned-gate law identified on HMS's output, checked at HMS's own pool levels on every W76 drowned case.

The law: with a tailwater over the crest, r = (pool - tailwater) / opening; up to r = 1 the free law of W62 on the head
over the crest times W67's submergence share at s = (tailwater - crest) / (pool - crest); from r = 1.25 the gate law
on the head over the tailwater times sqrt(3), the Orifice Coefficient unused; linear in r between.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_drowned import CREST, WIDTH, K, law, load, share

SQRT3 = np.sqrt(3.0)
CASES = {
    "gate_sluice_tw_low": (0.6, 1.5, 0, 0, 1, 0.5), "gate_sluice_tw_lip": (0.6, 1.5, 0, 0, 1, 0.5),
    "gate_sluice_tw_high": (0.6, 1.5, 0, 0, 1, 0.5), "gate_radial_tw_low": (0.7, 1.5, 3, 0.16, 0.72, 0.62),
    "gate_radial_tw_lip": (0.7, 1.5, 3, 0.16, 0.72, 0.62), "gate_sluice_tw_a": (0.6, 0.8, 0, 0, 1, 0.5),
    "gate_sluice_tw_b": (0.5, 0.8, 0, 0, 1, 0.5), "gate_sluice_tw_c": (0.5, 1.0, 0, 0, 1, 0.5),
    "gate_radial_tw_a": (0.7, 0.8, 3, 0.16, 0.72, 0.62), "gate_radial_tw_b": (0.6, 0.8, 3, 0.16, 0.72, 0.62),
}


def drowned(h: np.ndarray, tw: float, c: float, b: float, t: float, te: float, be: float, he: float) -> np.ndarray:
    hp = np.clip(h, 0.0, None)
    s = np.divide(tw, hp, out=np.ones_like(hp), where=hp > 0)
    low = law(h, np.full_like(h, b), c, t, te, be, he) * share(s)
    dh = np.clip(h - tw, 0.0, None)
    high = SQRT3 * c * K * WIDTH * (t**te if te else 1.0) * b**be * dh**he
    ratio = dh / b
    blend = np.clip((ratio - 1.0) / 0.25, 0.0, 1.0)
    return np.where(hp <= 0, 0.0, low + blend * (high - low))


def main() -> None:
    for case, parameters in CASES.items():
        hms = load(f"{case}.csv")
        h = hms["elevation_m"] - CREST
        tw = hms["tailwater_m"][0] - CREST
        q = hms["spill_1"]
        error = np.abs(drowned(h, tw, *parameters) - q) / q.max()
        print(f"{case:22s} peak {q.max():9.3f}  worst of peak {error.max():.2e}  max (pool-tw)/B {((h - tw) / parameters[1]).max():.2f}")


if __name__ == "__main__":
    main()
