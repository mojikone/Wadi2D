"""Output only: the same job, before and after this work, gives the same water. Compares series and the cell maps.

Usage: s05_compare_run.py <run before> <run after>. Writes unchanged_run.json. Also class areas against W7's s06 rasters.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import rasterio

HERE = Path(__file__).resolve().parent
BEFORE, AFTER = Path(sys.argv[1]), Path(sys.argv[2])
OLD_PIXELS = Path(r"D:\Mojtaba\Renardet\Wadi2D\W7 plugin test\maps\terrain\pixel_hazard_sloped_5m.tif")


def peak(path: Path) -> float:
    with path.open(newline="", encoding="utf-8") as stream:
        return max(abs(float(row[1])) for row in list(csv.reader(stream))[1:])


out: dict = {"lines": {}}
for path in sorted((BEFORE / "series").glob("line_*.csv")):
    other = AFTER / "series" / path.name
    a = path.read_text(encoding="utf-8")
    b = other.read_text(encoding="utf-8")
    out["lines"][path.stem[5:]] = {"before_m3s": peak(path), "after_m3s": peak(other), "same_file": a == b}
for name in ("max_depth", "max_speed", "hazard"):
    with rasterio.open(BEFORE / "maps" / f"{name}.tif") as s, rasterio.open(AFTER / "maps" / f"{name}.tif") as t:
        out[f"{name}_largest_difference"] = float(np.abs(s.read(1) - t.read(1)).max())
with rasterio.open(OLD_PIXELS) as src:
    old = src.read(1)
    km2 = abs(src.transform.a * src.transform.e) / 1e6
out["s06_class_km2"] = {f"H{k}": round(float((old == k).sum()) * km2, 2) for k in range(1, 7)}
stats = json.loads((AFTER / "pixels" / "pixels.json").read_text(encoding="utf-8"))
out["engine_class_km2"] = {k: round(v, 2) for k, v in stats["class_km2"].items()}
out["smoothing_change_pct"] = stats["smooth"]["change_pct"]
out["wet_added_km2"] = stats["smooth"]["wet_added_km2"]
out["wet_removed_km2"] = stats["smooth"]["wet_removed_km2"]
print(json.dumps(out, indent=1))
(HERE / "unchanged_run.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
