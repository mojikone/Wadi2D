"""The runs of ``run_engine.py`` as the README's tables, and the rules of W53 checked on them.

usage: summarise.py RUNS.json [OTHER_RUNS.json]      (venv python)

With a second file (the same plan run again), every run's Bidah 03 peak, steps and stored water are compared between
the two: a GPU shared with other work must give the same numbers twice.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

NAMES = ("RP5", "RP10", "RP25", "RP50", "RP100", "RP200", "RP500", "RP1000", "RP2000", "RP5000", "RP10000", "PMP")
FACTOR_AT_S13 = 0.976 + (0.965 - 0.976) * (20.971 - 20.0) / 10.0
"""ARF FM read by hand at 20.971 km2, linear in area as HMS reads it; its DA log says 200.251 of 205.4 mm."""
MASS = 1e-6


def peak(run: dict) -> float:
    return run.get("line", {}).get("peak_m3s", float("nan"))


def main() -> None:
    found = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["runs"]
    bad = [n for n, r in found.items() if r["exit_code"] or abs(r["balance"]["relative_error"]) > MASS]
    print(f"{len(found)} runs; failed or mass error over {MASS:g}: {bad or 'none'}")
    print("\n| Storm | NetCDF peak m3/s | DSS peak m3/s | DSS/NC peak | DSS/NC rain booked | peak h (NC) |")
    print("|---|---|---|---|---|---|")
    for name in NAMES:
        a, b = found.get(f"full_{name}_nc"), found.get(f"full_{name}_dss")
        if a and b:
            r = b["balance"]["rain_m3"] / a["balance"]["rain_m3"] - 1.0
            print(f"| {name} | {peak(a):.1f} | {peak(b):.1f} | {peak(b) / peak(a) - 1.0:+.2%} | {r:+.2%} | {a['line']['peak_h']:.2f} |")
    print(f"\nARF at 20.971 km2 by hand: {FACTOR_AT_S13:.6f}")
    print("\n| Run | factor reported | peak no ARF | peak with ARF | peak ratio | rain booked ratio |")
    print("|---|---|---|---|---|---|")
    for name, run in found.items():
        if not name.endswith("_arf") and "_arf_" not in name:
            continue
        twin = found.get(name.replace("_arf", ""))
        said = run.get("area_reduction") or [{}]
        if twin is None or not twin.get("line"):
            continue
        rain = run["balance"]["rain_m3"] / twin["balance"]["rain_m3"]
        print(f"| {name} | {said[0].get('factor', float('nan')):.6f} | {peak(twin):.1f} | {peak(run):.1f} | {peak(run) / peak(twin):.4f} | {rain:.4f} |")
        if "network_S13" in run:
            print(f"|   S13 lumped outflow | | {twin['network_S13']['peak_m3s']:.1f} | {run['network_S13']['peak_m3s']:.1f} | {run['network_S13']['peak_m3s'] / twin['network_S13']['peak_m3s']:.4f} | |")
    print("\n| CPU run | GPU peak | CPU peak | CPU/GPU | wall s CPU |")
    print("|---|---|---|---|---|")
    for name, run in found.items():
        if name.endswith("_cpu"):
            twin = found.get(name[: -len("_cpu")])
            if twin:
                print(f"| {name} | {peak(twin):.2f} | {peak(run):.2f} | {peak(run) / peak(twin) - 1.0:+.4%} | {run['wall_s']} |")
    if len(sys.argv) > 2:
        other = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))["runs"]
        same = [n for n in found if n in other and peak(found[n]) == peak(other[n]) and found[n]["steps"] == other[n]["steps"]
                and found[n]["balance"]["storage_end_m3"] == other[n]["balance"]["storage_end_m3"]]  # fmt: skip
        differ = sorted(set(found) & set(other) - set(same))
        print(f"\nrepeated: {len(same)} of {len(set(found) & set(other))} identical in peak, steps and stored water; differ: {differ}")


if __name__ == "__main__":
    main()
