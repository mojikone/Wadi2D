"""HMS's drowned gate, read off its own output: spillway flow under a fixed tailwater against candidate laws at HMS's
own pool levels, by regime of the head over the crest H against the opening B and of the tailwater.

Usage: ``python probe_drowned.py <case>``; prints rows of H, tailwater head over the crest, HMS's flow, the free law and
candidates, and the worst relative difference of each candidate by regime.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_percent import CREST, WEIR_C, WIDTH, K, law, load

SUBMERGENCE = np.array([0.76, 0.84, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98, 0.995, 1.0])
SHARE = np.array([1.0, 0.985, 0.96, 0.93, 0.88, 0.82, 0.72, 0.575, 0.38, 0.0])
B = 1.5
ORIFICE_C = 0.8
PARAMETERS = {"sluice": (0.6, 0.0, 0.0, 1.0, 0.5), "radial": (0.7, 3.0, 0.16, 0.72, 0.62)}


def share(s: np.ndarray) -> np.ndarray:
    return np.where(s >= 1.0, 0.0, np.interp(s, SUBMERGENCE, SHARE, left=1.0))


def main() -> None:
    case = sys.argv[1]
    hms = load(f"{case}.csv")
    c, t, te, be, he = PARAMETERS["radial" if "radial" in case else "sluice"]
    h = hms["elevation_m"] - CREST
    tw = hms["tailwater_m"] - CREST
    q = hms["spill_1"]
    free = law(h, np.full_like(h, B), c, t, te, be, he)
    hp = np.clip(h, 0, None)
    dh = np.clip(h - tw, 0, None)
    s = np.divide(tw, hp, out=np.ones_like(hp), where=hp > 0)
    weir = WEIR_C * WIDTH * hp**1.5
    candidates = {
        "free": free,
        "free x share(s)": free * share(s),
        "orifice Co W B k sqrt(dH)": ORIFICE_C * WIDTH * B * K * np.sqrt(dh),
        "gate C W B k sqrt(dH)": c * WIDTH * B * K * np.sqrt(dh),
        "weir x share": weir * share(s),
    }
    wet = h > 0
    print(case, "steps over the crest", wet.sum(), "tailwater head", tw[0])
    for label, mask in (
        ("H<=B", wet & (h <= B)), ("B<H<1.25B", wet & (h > B) & (h < 1.25 * B)), ("H>=1.25B", wet & (h >= 1.25 * B)),
    ):
        if not mask.any():
            continue
        print(f" {label}: {mask.sum()} steps, H {h[mask].min():.3f}..{h[mask].max():.3f}, s {s[mask].min():.3f}..{s[mask].max():.3f}")
        for name, value in candidates.items():
            rel = np.abs(value[mask] - q[mask]) / max(q.max(), 1e-9)
            print(f"    {name:28s} worst of peak {rel.max():.3e}")
    order = np.argsort(h)
    order = order[h[order] > 0]
    for k in order[:: max(len(order) // 30, 1)]:
        print(f"   H {h[k]:7.4f} s {s[k]:6.4f} Q {q[k]:10.4f} free {free[k]:10.4f} ratio {q[k] / max(free[k], 1e-12):8.5f}")


if __name__ == "__main__":
    main()
