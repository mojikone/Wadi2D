"""W103 (c): the dock's own way against W79's hand-made runs 3 and 4, without the 2D solver.

For each of W79's two Hybrid jobs, the job the dock now writes from it (``rebuilt/<job>``, which must give the same
numbers) and the dock's own way (``rebuilt/hybrid_*_dock_way``: the lumped part of the area reduction a curve read at
each subbasin's entry area, W98, in place of the storm areas typed by hand; for Hybrid Lumped the lumped water kept on
the network, W88, in place of the six hand-placed inflows), the engine's own functions give:

- each lumped subbasin's area-reduction factor, as its rain is reduced (the storm over it, total depth over 251 mm);
- each hydrograph that enters the grid, its peak and volume (the lumped network as the run routes it, about a second);
- each entry's point, and for the network's automatic entries how far each lies from the hand-placed one and from the
  catchments left out of the mesh (an entry that lies in a left-out cell is moved by the run onto their edge).

Run from the repository root with the venv: ``.venv\\Scripts\\python "W103 Block 2 scenarios complete\\scripts\\
compare_dock_way.py"``. Read only on W79 and on his HMS project; writes ``results/`` beside this folder's scripts.
"""

from __future__ import annotations

import csv
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
import shapely

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from wadi2d import run as R  # noqa: E402
from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.forcing import build_storm, load_polygons  # noqa: E402

W79 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways\jobs")
W103 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W103 Block 2 scenarios complete\rebuilt")
OUT = HERE / "results"
CASES = {
    "Hybrid Lumped": {
        "W79": W79 / "rerun2_run3_hybrid_aligned.json",
        "dock, faithful": W103 / "rerun2_run3_hybrid_aligned" / "job.json",
        "dock way": W103 / "hybrid_lumped_dock_way" / "job.json",
    },
    "Hybrid 2D": {
        "W79": W79 / "rerun2_run4_hybrid_2d_routing_aligned.json",
        "dock, faithful": W103 / "rerun2_run4_hybrid_2d_routing_aligned" / "job.json",
        "dock way": W103 / "hybrid_2d_dock_way" / "job.json",
    },
}
DX_M = 20.0
"""The runs' cell: an entry farther than half a cell's diagonal from the left-out catchments is in no left-out cell."""


def crs_of(cfg: RunConfig) -> str:
    with rasterio.open(cfg.terrain.dem) as dem:
        return dem.crs.to_wkt()


def read(path: Path) -> dict:
    job = json.loads(path.read_text(encoding="utf-8"))
    cfg = RunConfig.model_validate(job)
    crs = crs_of(cfg)
    cfg, _generated = R._resolved(cfg, crs)  # an HMS job with lumped_entry network gets its automatic inflows here
    storm = build_storm(cfg)
    basin, hms_basin, decided = R._lumped_basin(cfg, crs)
    rain = R._lumped_rain(cfg, storm, basin, hms_basin, crs, decided)
    depth = cfg.storm.depth_mm
    lumped = [s.name for s in cfg.hydrology.subbasins if s.mode == "lumped"]
    factors = {name: rain.over(name).total_depth / depth for name in lumped}
    t0 = time.monotonic()
    flows = R._network(cfg, storm, crs)[0]
    seconds = time.monotonic() - t0
    element = {i.name: i.element for i in cfg.hydrology.inflows}
    entries = {}
    for name, point, times, q in flows:
        q = np.asarray(q, np.float64)
        t = np.asarray(times, np.float64)
        entries[name] = {
            "element": element.get(name, name),
            "x": float(point[0]), "y": float(point[1]),
            "peak_m3s": float(q.max()), "time_of_peak_h": float(t[int(q.argmax())] / 3600.0),
            "volume_m3": float(np.trapezoid(q, t)),
        }  # fmt: skip
    left = R.left_out_of(cfg, crs)
    area = left.area if left is not None and left.names else None
    for entry in entries.values():
        entry["from_left_out_m"] = None if area is None else float(shapely.Point(entry["x"], entry["y"]).distance(area))
    return {"cfg": cfg, "basin": basin, "factors": factors, "entries": entries, "network_s": seconds,
            "left_out": list(left.names) if left is not None else []}  # fmt: skip


def match(basin, hand: dict, auto: dict) -> dict[str, str]:
    """Each hand-placed entry with the automatic one whose element it drains to (or the same element)."""
    out = {}
    for name, entry in hand.items():
        for other, found in auto.items():
            if found["element"] == entry["element"] or entry["element"] in basin.upstream_of(found["element"]):
                out[name] = other
                break
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    summary = {}
    for case, paths in CASES.items():
        got = {label: read(path) for label, path in paths.items()}
        w79, faithful, way = got["W79"], got["dock, faithful"], got["dock way"]
        names = sorted(w79["factors"])
        factor_rows = [{
            "subbasin": n, "factor_W79": round(w79["factors"][n], 6), "factor_dock_faithful": round(faithful["factors"][n], 6),
            "factor_dock_way": round(way["factors"][n], 6), "dock_way_minus_W79": round(way["factors"][n] - w79["factors"][n], 6),
        } for n in names]  # fmt: skip
        with (OUT / f"factors_{case.replace(' ', '_')}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(factor_rows[0]))
            writer.writeheader()
            writer.writerows(factor_rows)
        pairs = match(w79["basin"], w79["entries"], way["entries"])
        entry_rows = []
        for name, hand in w79["entries"].items():
            same = faithful["entries"].get(name)
            auto_name = pairs.get(name)
            auto = way["entries"].get(auto_name) if auto_name else None
            entry_rows.append({
                "entry": name, "element_W79": hand["element"], "x_W79": round(hand["x"], 2), "y_W79": round(hand["y"], 2),
                "peak_W79": round(hand["peak_m3s"], 2), "volume_W79_Mm3": round(hand["volume_m3"] / 1e6, 4),
                "peak_dock_faithful": round(same["peak_m3s"], 2) if same else None,
                "volume_dock_faithful_Mm3": round(same["volume_m3"] / 1e6, 4) if same else None,
                "entry_dock_way": auto_name, "element_dock_way": auto["element"] if auto else None,
                "x_dock_way": round(auto["x"], 2) if auto else None, "y_dock_way": round(auto["y"], 2) if auto else None,
                "distance_m": round(math.hypot(auto["x"] - hand["x"], auto["y"] - hand["y"]), 1) if auto else None,
                "dock_way_from_left_out_m": round(auto["from_left_out_m"], 1) if auto and auto["from_left_out_m"] is not None else None,
                "peak_dock_way": round(auto["peak_m3s"], 2) if auto else None,
                "volume_dock_way_Mm3": round(auto["volume_m3"] / 1e6, 4) if auto else None,
                "peak_ratio": round(auto["peak_m3s"] / hand["peak_m3s"], 4) if auto and hand["peak_m3s"] else None,
                "volume_ratio": round(auto["volume_m3"] / hand["volume_m3"], 4) if auto and hand["volume_m3"] else None,
                "time_of_peak_W79_h": round(hand["time_of_peak_h"], 3), "time_of_peak_dock_way_h": round(auto["time_of_peak_h"], 3) if auto else None,
            })  # fmt: skip
        with (OUT / f"entries_{case.replace(' ', '_')}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(entry_rows[0]))
            writer.writeheader()
            writer.writerows(entry_rows)
        faithful_same = all(
            abs(faithful["entries"][n]["peak_m3s"] - e["peak_m3s"]) < 1e-9 and abs(faithful["entries"][n]["volume_m3"] - e["volume_m3"]) < 1e-6
            for n, e in w79["entries"].items() if n in faithful["entries"]
        ) and set(faithful["entries"]) == set(w79["entries"])  # fmt: skip
        summary[case] = {
            "lumped_subbasins": len(names),
            "faithful_factors_equal": all(abs(faithful["factors"][n] - w79["factors"][n]) < 1e-12 for n in names),
            "faithful_entries_equal": faithful_same,
            "dock_way_factor_difference": {"min": min(r["dock_way_minus_W79"] for r in factor_rows), "max": max(r["dock_way_minus_W79"] for r in factor_rows)},
            "entries_W79": len(w79["entries"]), "entries_dock_way": len(way["entries"]),
            "left_out_W79": len(w79["left_out"]), "left_out_dock_way": len(way["left_out"]),
            "network_seconds": {label: round(g["network_s"], 2) for label, g in got.items()},
            "entries": entry_rows,
        }  # fmt: skip
        print(f"== {case}: {json.dumps({k: v for k, v in summary[case].items() if k != 'entries'})}")
        for row in entry_rows:
            print("  ", json.dumps(row))
    (OUT / "compare_dock_way.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
