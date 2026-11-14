"""What head HMS's orifice uses: fit Q^2 = a (z - z0) on the HMS series of the orifice cases."""

import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
BARRELS, AREA, COEFFICIENT, CENTRE = 2, 1.5, 0.6, 101.0

for case in sys.argv[1:]:
    names = (DATA / f"{case}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    data = np.loadtxt(DATA / f"{case}.csv", delimiter=",", skiprows=1)
    z = data[:, names.index("elevation_m")]
    q = data[:, names.index("outlet_1")]
    tw = data[:, names.index("tailwater_m")] if "tailwater_m" in names else np.full_like(z, -np.inf)
    slope, intercept = np.polyfit(z, q**2, 1)
    z0 = -intercept / slope
    g = slope / (2.0 * (BARRELS * AREA * COEFFICIENT) ** 2)
    print(f"{case}: Q^2 = {slope:.6f} (z - {z0:.6f}); implied g {g:.6f}; tailwater {tw.min():.3f}..{tw.max():.3f}")
    for gravity in (9.81, 9.80665):
        for base in ("centre", "max(centre, tw)"):
            head = z - (np.maximum(CENTRE, tw) if base != "centre" else CENTRE)
            model = BARRELS * AREA * COEFFICIENT * np.sqrt(2.0 * gravity * np.maximum(head, 0.0))
            print(f"   g {gravity} head from {base}: max |dQ| {np.abs(model - q).max():.3e}")
