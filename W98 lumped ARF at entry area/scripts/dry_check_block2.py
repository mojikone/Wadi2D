"""W98 dry check: Block 2's Hybrid Lumped job (W79 rerun2 run 3) with its storm moved to storm.area_reduction, the
lumped part a curve (his project's ARF FM table), the 2D part at 100 km2 (his choice of 2026-11-15), and every
subbasin's storm_area_km2 taken out. The engine finds each lumped subbasin's entry element and area; this lists them
against the areas the job gave by hand. No 2D solver, no lumped run.

Run from the repository root: ``.venv\\Scripts\\python "W98 lumped ARF at entry area\\scripts\\dry_check_block2.py"``.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.engine.entry_area import needs_own_run, subbasin_entry_areas  # noqa: E402
from wadi2d.run import _entering, _entry_map, _lumped_basin, _ran  # noqa: E402

JOB = ROOT / "W79 Block 2 four ways" / "jobs" / "rerun2_run3_hybrid_aligned.json"
OUT = Path(__file__).resolve().parents[1] / "results"
GRID_AREA_KM2 = 100.0
HAND_ROUNDING = 0.005
"""The job's hand areas carry two decimals."""


def job() -> tuple[RunConfig, dict[str, float]]:
    data = json.loads(JOB.read_text(encoding="utf-8"))
    storm = data["storm"]
    curve = storm.pop("arf")
    storm.pop("storm_area_km2")
    storm["area_reduction"] = {
        "lumped": {"form": "curve", "table": curve},
        "grid": {"form": "area", "table": curve, "area_km2": GRID_AREA_KM2},
    }
    by_hand = {}
    for sub in data["hydrology"]["subbasins"]:
        area = sub.pop("storm_area_km2", None)
        if area is not None:
            by_hand[sub["name"]] = area
    return RunConfig.model_validate(data), by_hand


def main() -> None:
    cfg, by_hand = job()
    basin, _hms, decided = _lumped_basin(cfg, "")
    entry = _entry_map(cfg, basin, decided)
    areas = subbasin_entry_areas(basin, entry)
    table = cfg.storm.area_reduction.lumped.table
    lumped = [s.name for s in cfg.hydrology.subbasins if s.mode == "lumped"]
    rows = []
    for name in lumped:
        enters, area = areas.get(name, (None, basin.subbasins[name].area_km2))
        hand = by_hand.get(name)
        rows.append({
            "subbasin": name, "own_area_km2": round(basin.subbasins[name].area_km2, 4), "enters_at": enters,
            "entry_area_km2": round(area, 4), "factor": round(_factor(table, area), 6),
            "job_by_hand_km2": hand, "differs_km2": None if hand is None else round(area - hand, 4),
        })  # fmt: skip
    wanted = _entering(cfg.hydrology)
    written = _ran(basin, wanted, None)
    reruns = [n for n in basin.topological_order() if n in written and needs_own_run(basin, n, entry)]
    OUT.mkdir(exist_ok=True)
    with (OUT / "block2_entry_areas.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    by_entry: dict[str, list[str]] = {}
    for row in rows:
        by_entry.setdefault(str(row["enters_at"]), []).append(row["subbasin"])
    summary = {
        "job": str(JOB.relative_to(ROOT)),
        "lumped_subbasins": len(rows),
        "entries": {
            e: {"area_km2": round(basin.drainage_area(e), 4), "factor": round(_factor(table, basin.drainage_area(e)), 6),
                "subbasins": len(subs), "own_area_sum_km2": round(sum(basin.subbasins[s].area_km2 for s in subs), 4)}
            for e, subs in by_entry.items() if e != "None"
        },  # fmt: skip
        "largest_difference_against_the_job_km2": max(abs(r["differs_km2"] or 0.0) for r in rows),
        "beyond_the_job_s_two_decimals": [r["subbasin"] for r in rows if abs(r["differs_km2"] or 0.0) > HAND_ROUNDING],
        "not_in_the_job_by_hand": [r["subbasin"] for r in rows if r["job_by_hand_km2"] is None],
        "elements_reported_at_their_own_area": len(reruns),
        "reruns": reruns,
    }
    summary["network"] = _network_peaks(cfg)
    (OUT / "block2_dry_check.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    for row in rows:
        print(f"{row['subbasin']:8s} {row['own_area_km2']:9.3f} -> {row['enters_at']:20s} {row['entry_area_km2']:9.3f} "
              f"f={row['factor']:.4f} by hand {row['job_by_hand_km2']}")  # fmt: skip
    print(json.dumps({k: v for k, v in summary.items() if k != "reruns"}, indent=1))


def _network_peaks(cfg: RunConfig) -> dict:
    """The lumped network the run would route, the entry-area run and the own-area reruns, timed; no 2D solver. Each
    entry's inflow and outflow peaks, m3/s, against W79 rerun2 run 3, which gave the same areas by hand."""
    import time

    from wadi2d.forcing import build_storm
    from wadi2d.run import _network

    t0 = time.monotonic()
    _table, _live, series = _network(cfg, build_storm(cfg))
    seconds = time.monotonic() - t0
    peaks = {}
    for name in ("Bidah 03 Reservoir", "Faydh 01 Reservoir", "R5A Reservoir", "R2A Reservoir", "Z4C Reservoir", "HAT-J4"):
        peaks[name] = {"inflow_m3s": round(float(series.run.inflow[name].max()), 1),
                       "outflow_m3s": round(float(series.run.outflow[name].max()), 1)}  # fmt: skip
    own = {name: round(float(run.outflow[name].max()), 1) for name, run in series.own_area.items()}
    grid = {name: round(float(series.run.outflow[name].max()), 1) for name in series.own_area}
    return {"seconds": round(seconds, 2), "entries": peaks, "reruns_own_area_peak_m3s": own, "reruns_entry_area_peak_m3s": grid}


def _factor(table, area: float) -> float:
    from wadi2d.storm.split_arf import arf_from_config

    return arf_from_config(table).factor(area)


if __name__ == "__main__":
    main()
