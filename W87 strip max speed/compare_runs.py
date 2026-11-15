"""W87: two runs of one job, before and after the change: is the water the same to the digit, and what did the speed
of record become?

Water: every series file byte for byte; in ``results.h5`` every saved map's depth, mean depth and face discharges
(squares and strip) and the maxima of depth, mean depth and arrival, bit for bit; the steps, the outflow and the
storage at the end. The rain total is given beside them and not required equal to the last bit: the monitor credits
each rain window in shares cut at its progress ticks, which come by the wall clock (``Monitor.settle``), so two runs
of the same code sum it in different pieces (Faydh: 2.6e-15 apart). Record: the strip's speed and hazard maxima and
the maps' strip speed, counted over thresholds.

    .venv\\Scripts\\python "W87 strip max speed\\compare_runs.py" <run before> <run after> [<out.json>]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np

WATER_MAPS = ("depth", "mean_depth", "qx", "qy", "strip_depth", "strip_mean_depth")
WATER_MAXIMA = ("depth", "mean_depth", "arrival", "strip_depth", "strip_mean_depth")
SQUARE_RECORD = ("speed", "hazard")
LIMITS = (5.0, 10.0, 25.0, 35.36, 100.0, 1e4)


def counts(a: np.ndarray) -> dict:
    return {
        "max": float(a.max()),
        "q99_of_nonzero": float(np.quantile(a[a > 0], 0.99)) if (a > 0).any() else 0.0,
    } | {f"over_{lim:g}": int((a > lim).sum()) for lim in LIMITS}


def compare(before: Path, after: Path) -> dict:
    found: dict = {
        "before": f"{before.parent.name}/{before.name}",
        "after": f"{after.parent.name}/{after.name}",
    }
    names = sorted(p.name for p in (before / "series").glob("*.csv"))
    same = [
        n
        for n in names
        if (after / "series" / n).is_file()
        and (before / "series" / n).read_bytes() == (after / "series" / n).read_bytes()
    ]
    found["series_files"] = len(names)
    found["series_identical"] = len(same)
    with h5py.File(before / "results.h5", "r") as a, h5py.File(after / "results.h5", "r") as b:
        maps = sorted(a["maps"].keys())
        found["maps"] = len(maps)
        found["maps_same_times"] = maps == sorted(b["maps"].keys())
        differing = []
        for name in maps:
            for field in WATER_MAPS:
                if field in a["maps"][name] and not np.array_equal(
                    a["maps"][name][field][()], b["maps"][name][field][()]
                ):
                    differing.append(f"{name}/{field}")
        found["water_maps_differing"] = differing
        found["water_maxima_differing"] = [
            n
            for n in WATER_MAXIMA
            if n in a["maxima"] and not np.array_equal(a["maxima"][n][()], b["maxima"][n][()])
        ]
        found["squares_record_differing"] = [
            n for n in SQUARE_RECORD if not np.array_equal(a["maxima"][n][()], b["maxima"][n][()])
        ]
        for key in ("steps", "rain_m3", "outflow_m3", "storage_end_m3", "error_m3"):
            found[key] = [float(a.attrs[key]), float(b.attrs[key])]
        found["books_identical"] = all(
            found[k][0] == found[k][1] for k in ("steps", "outflow_m3", "storage_end_m3")
        )
        found["rain_relative_difference"] = abs(found["rain_m3"][1] - found["rain_m3"][0]) / max(
            abs(found["rain_m3"][0]), 1e-30
        )
        for label, f in (("before", a), ("after", b)):
            mx = f["maxima"]
            rec = {"squares_speed": counts(mx["speed"][()])}
            if "strip_depth" in mx:  # a job of squares alone has no strip
                wet = mx["strip_depth"][0] > 0.05
                rec |= {
                    "strip_cells": int(wet.size),
                    "strip_cells_wet": int(wet.sum()),
                    "strip_speed": counts(mx["strip_speed"][0]),
                    "strip_hazard": counts(mx["strip_hazard"][0]),
                    "strip_speed_median_wet": (
                        float(np.median(mx["strip_speed"][0][wet])) if wet.any() else 0.0
                    ),
                }
            in_maps = [f["maps"][m]["strip_speed"][0] for m in maps if "strip_speed" in f["maps"][m]]
            if in_maps:
                rec["maps_strip_speed"] = counts(np.max(in_maps, axis=0))
            found[label + "_record"] = rec
    found["water_identical"] = bool(
        found["series_identical"] == found["series_files"] and found["maps_same_times"] and not differing
        and not found["water_maxima_differing"] and found["books_identical"]
    )  # fmt: skip
    return found


if __name__ == "__main__":
    result = compare(Path(sys.argv[1]), Path(sys.argv[2]))
    text = json.dumps(result, indent=1)
    print(text)
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(text, encoding="utf-8")
