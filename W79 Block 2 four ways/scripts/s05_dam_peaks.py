"""dam_peaks.csv: each dam's inflow and outflow peak, time to peak and volume, per run, from each run's w79_check.json.

Times are hours from the storm's start; volumes over the 48 h run. How each figure was read is in the source columns
(s04_check.py says why)."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w79 import DAMS, HERE, RUN_NAMES, RUN_TITLES, RUNS, load_json  # noqa: E402

FIELDS = [
    "run", "method", "dam",
    "inflow_peak_m3s", "inflow_time_to_peak_h", "inflow_volume_Mm3",
    "outflow_peak_m3s", "outflow_time_to_peak_h", "outflow_volume_Mm3",
    "inflow_source", "outflow_source",
]


def main() -> None:
    rows = []
    for number, name in RUN_NAMES.items():
        path = RUNS / name / "w79_check.json"
        if not path.is_file():
            print("no check for", name)
            continue
        check = load_json(path)
        for dam in DAMS:
            d = check["dams"][dam]
            rows.append({
                "run": number, "method": RUN_TITLES[number], "dam": dam,
                "inflow_peak_m3s": round(d["inflow"]["peak_m3s"], 1),
                "inflow_time_to_peak_h": round(d["inflow"]["time_to_peak_h"], 2),
                "inflow_volume_Mm3": round(d["inflow"]["volume_Mm3"], 3),
                "outflow_peak_m3s": round(d["outflow"]["peak_m3s"], 1),
                "outflow_time_to_peak_h": round(d["outflow"]["time_to_peak_h"], 2) if d["outflow"]["peak_m3s"] > 0.05 else "",
                "outflow_volume_Mm3": round(d["outflow"]["volume_Mm3"], 3),
                "inflow_source": d["inflow_source"], "outflow_source": d["outflow_source"],
            })
    out = HERE / "dam_peaks.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print("wrote", out, len(rows), "rows")
    for dam in DAMS:
        line = [f"{dam:9s}"]
        for r in rows:
            if r["dam"] == dam:
                line.append(f"r{r['run']} {r['inflow_peak_m3s']:7.1f} / {r['outflow_peak_m3s']:7.1f}")
        print("  ".join(line))


if __name__ == "__main__":
    main()
