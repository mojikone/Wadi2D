"""Numbers for the map sheets, read from the run. Writes facts.json."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RUN = Path(sys.argv[1])
rows = [json.loads(s) for s in (RUN / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
done = [r for r in rows if r.get("ev") == "done"][-1]
b = done["balance"]
warn = [r["message"] for r in rows if r.get("ev") == "warn"]
peaks = {}
for name in ("Faydh_01", "Bidah_03", "R5A", "R2A", "Z4C"):
    with (RUN / "series" / f"line_{name}.csv").open() as h:
        d = np.array([[float(v) for v in r] for r in list(csv.reader(h))[1:]])
    k = int(np.argmax(np.abs(d[:, 1])))
    peaks[name.replace("_", " ")] = (round(float(abs(d[k, 1]))), round(float(d[k, 0] / 3600), 1))
stats = json.loads((HERE / "pixel_hazard_sloped_stats.json").read_text())["class_km2"]
total = sum(stats.values())
lines = "\n".join(f"{k}: {v[0]:,} m3/s at hour {v[1]}" for k, v in peaks.items())
classes = "\n".join(f"{k}: {v:,.1f} km2" for k, v in stats.items())
water = f"Water: {b['inflow_m3'] / 1e6:,.1f} Mm3 from the lumped hills, {b['rain_m3'] / 1e6:,.1f} Mm3 of rain on the 2D area after losses, {b['outflow_m3'] / 1e6:,.1f} Mm3 out. Mass error {abs(b['relative_error']):.0e}."
caution = "Not a design result. No gauge, no culverts, 20 m cells."
facts = {
    "water": water,
    "depth": f"Peak flow at the dam sections\n\n{lines}\n\n{water}\n\n{caution}",
    "hazard": f"Area by class, {total:,.1f} km2 in all\n\n{classes}\n\nAIDR limits and rule as the Majlas dam-break study: a pixel takes the highest class any limit gives.\n\n{caution}",
    "warnings": warn,
    "peaks": peaks,
    "balance": b,
    "loop_s": done["loop_s"],
}
(HERE / "facts.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")
print(water)
print(lines)
print(classes)
print(warn)
