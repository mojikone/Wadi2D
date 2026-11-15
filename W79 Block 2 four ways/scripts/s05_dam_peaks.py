"""dam_peaks.csv: each dam's inflow and outflow peak, time to peak and volume, per run, from each run's w79_check.json,
with the area-reduction factor the dam's catchment took and the area it was read at.

Times are hours from the storm's start; volumes over the 48 h run. How each figure was read is in the source columns
(s04_check.py says why). The factor: run 1 the storm's one area (100 km2); run 2 the reservoir's own drainage area (its
depth-area run, network_peaks.csv); runs 3 and 4 the storm area given to the subbasins above the dam."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w79 import DAMS, HERE, JOBS, RESERVOIR, RUN_NAMES, RUN_TITLES, RUNS, SET, load_json  # noqa: E402

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.forcing import arf_table  # noqa: E402

FIELDS = [
    "run", "method", "dam", "arf_area_km2", "arf_factor",
    "inflow_peak_m3s", "inflow_time_to_peak_h", "inflow_volume_Mm3",
    "outflow_peak_m3s", "outflow_time_to_peak_h", "outflow_volume_Mm3",
    "inflow_source", "outflow_source", "ring_inflow_peak_m3s", "ring_inflow_volume_Mm3",
]


def arf_by_dam(number: int, name: str) -> dict[str, float]:
    """The area each dam's catchment read the ARF table at, in this run."""
    if number == 2:
        with (RUNS / name / "network_peaks.csv").open(encoding="utf-8") as f:
            by = {r["element"]: float(r["storm_area_km2"]) for r in csv.DictReader(f)}
        return {dam: by[RESERVOIR[dam]] for dam in DAMS}
    job = load_json(JOBS / f"{name}.json")
    check = load_json(RUNS / name / "w79_check.json")["setup"].get("subbasin_storm_areas_km2", {})
    if number == 1 or not check:
        return {dam: job["storm"]["storm_area_km2"] for dam in DAMS}
    from s02_jobs import reaches_dam

    out = {}
    for sub, area in check.items():
        out.setdefault(reaches_dam(sub), set()).add(area)
    assert all(len(v) == 1 for v in out.values()), out
    return {dam: out[dam].pop() for dam in DAMS}


def main() -> None:
    rows = []
    for number, name in RUN_NAMES.items():
        path = RUNS / name / "w79_check.json"
        if not path.is_file():
            print("no check for", name)
            continue
        check = load_json(path)
        table = arf_table(RunConfig.model_validate(load_json(JOBS / f"{name}.json")).storm)
        areas = arf_by_dam(number, name)
        for dam in DAMS:
            d = check["dams"][dam]
            rows.append({
                "run": number, "method": RUN_TITLES[number], "dam": dam,
                "arf_area_km2": round(areas[dam], 3), "arf_factor": round(table.factor(areas[dam]), 4),
                "inflow_peak_m3s": round(d["inflow"]["peak_m3s"], 1),
                "inflow_time_to_peak_h": round(d["inflow"]["time_to_peak_h"], 2),
                "inflow_volume_Mm3": round(d["inflow"]["volume_Mm3"], 3),
                "outflow_peak_m3s": round(d["outflow"]["peak_m3s"], 1),
                "outflow_time_to_peak_h": round(d["outflow"]["time_to_peak_h"], 2) if d["outflow"]["peak_m3s"] > 0.05 else "",
                "outflow_volume_Mm3": round(d["outflow"]["volume_Mm3"], 3),
                "inflow_source": d["inflow_source"], "outflow_source": d["outflow_source"],
                "ring_inflow_peak_m3s": round(d["inflow_by_ring"]["peak_m3s"], 1) if "inflow_by_ring" in d else "",
                "ring_inflow_volume_Mm3": round(d["inflow_by_ring"]["volume_Mm3"], 3) if "inflow_by_ring" in d else "",
            })
    out = HERE / ("dam_peaks_rerun.csv" if SET == "rerun" else "dam_peaks.csv")  # the final set is the live table
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
