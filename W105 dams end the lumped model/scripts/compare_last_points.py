"""W105 (b): the dock's own way with the last points against W79's hand-made runs 3 and 4, without the 2D solver.

The dock's own way is W103's (``rebuilt/hybrid_*_dock_way/job.json``: the lumped part of the area reduction a curve, for
Hybrid Lumped the lumped water kept on the network), with ``hydrology.last_points`` the five dams and HAT-J4 (the field
the dock now writes when HAT-J4 is added to the dams it finds). For each case the engine's own functions give:

- each lumped subbasin's area-reduction factor, as its rain is reduced (the storm over it, total depth over 251 mm);
- each hydrograph that enters the grid, its peak, volume and time of peak (the lumped network as the run routes it);
- for Hybrid Lumped, each entry's point on run 3's own mesh: the grid and aligned strip run 3 cached on 15 Nov
  (``runs/cache``, read only, loaded by their stored keys), with the engine's ``snap_entries``. W79's own job on that
  mesh must give the point run 3 recorded for HAT-J4 (``entries.json``), which shows it is the mesh run 3 ran on;
- the series of record: the elements above a dam in Hybrid Lumped at their own drainage area (HMS's depth-area
  practice) and the same catchments in Hybrid 2D at their dam's.

Run from the repository root with the venv: ``.venv\\Scripts\\python "W105 dams end the lumped model\\scripts\\
compare_last_points.py"``. Read only on W79, W103 and his HMS project; writes ``results/`` beside this folder's scripts.
No GPU.
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
from wadi2d.engine.left_out import snap_entries  # noqa: E402
from wadi2d.engine.network_entries import hms_icons  # noqa: E402
from wadi2d.forcing import build_storm  # noqa: E402
from wadi2d.io.cache import load_strip, load_tables  # noqa: E402

DATA = Path(r"D:\Mojtaba\Renardet\Wadi2D")
W79 = DATA / "W79 Block 2 four ways"
W103 = DATA / "W103 Block 2 scenarios complete" / "rebuilt"
RUN3_GRID = W79 / "runs" / "cache" / "grid_c172b8bd5f5c50470c234ba3.h5"
RUN3_STRIP = W79 / "runs" / "cache" / "strip_1d0940e6ae4e3f7f682146bf.pkl"
"""The tables and strip run 3 ran on (its progress.jsonl, after the pit fills)."""
RUN3_ENTRIES = W79 / "runs" / "rerun2_run3_hybrid_aligned" / "entries.json"
LAST_POINTS = ["Bidah 03 Reservoir", "Faydh 01 Reservoir", "R5A Reservoir", "R2A Reservoir", "Z4C Reservoir", "HAT-J4"]
DOCK = HERE / "dock_data" / "rebuilt"
"""The jobs the real dock wrote with HAT-J4 added (``dock_last_points.py``); W103's with the field laid on when absent."""


def _dock_way(folder: str, w103: str) -> Path:
    written = DOCK / folder / "job.json"
    return written if written.is_file() else W103 / w103 / "job.json"


CASES = {
    "Hybrid Lumped": (W79 / "jobs" / "rerun2_run3_hybrid_aligned.json", _dock_way("hybrid_lumped_last_points", "hybrid_lumped_dock_way")),
    "Hybrid 2D": (W79 / "jobs" / "rerun2_run4_hybrid_2d_routing_aligned.json", _dock_way("hybrid_2d_last_points", "hybrid_2d_dock_way")),
}
DX_M = 20.0
OUT = HERE / "results"
_INPUTS = json.loads((W79 / "inputs" / "inputs.json").read_text(encoding="utf-8"))["dams"]
DAMS = {f"{name} Reservoir": dam for name, dam in _INPUTS.items()}
"""W79's dam lines and chutes by the HMS reservoir's name."""


def crs_of(cfg: RunConfig) -> str:
    with rasterio.open(cfg.terrain.dem) as dem:
        return dem.crs.to_wkt()


def dock_way(path: Path, points: list[str] | None) -> RunConfig:
    """The dock's job; ``points`` laid on when it names none (W103's), None takes them away (the dams alone)."""
    job = json.loads(path.read_text(encoding="utf-8"))
    if points is None:
        job["hydrology"].pop("last_points", None)
    elif "last_points" not in job["hydrology"]:
        job["hydrology"]["last_points"] = points
    if sorted(job["hydrology"].get("last_points", points) or []) != sorted(points or []):
        raise SystemExit(f"{path} names other last points: {job['hydrology']['last_points']}")
    return RunConfig.model_validate(job)


def read(cfg: RunConfig) -> dict:
    crs = crs_of(cfg)
    cfg, _generated = R._resolved(cfg, crs)
    storm = build_storm(cfg)
    basin, hms_basin, decided = R._lumped_basin(cfg, crs)
    rain = R._lumped_rain(cfg, storm, basin, hms_basin, crs, decided)
    depth = cfg.storm.depth_mm
    lumped = [s.name for s in cfg.hydrology.subbasins if s.mode == "lumped"]
    factors = {name: rain.over(name).total_depth / depth for name in lumped}
    t0 = time.monotonic()
    flows, _live, series = R._network(cfg, storm, crs)
    seconds = time.monotonic() - t0
    element = {i.name: i.element for i in cfg.hydrology.inflows}
    entries = {}
    for name, point, times, q in flows:
        q, t = np.asarray(q, np.float64), np.asarray(times, np.float64)
        entries[name] = {
            "element": element.get(name, name), "x": float(point[0]), "y": float(point[1]),
            "peak_m3s": float(q.max()), "time_of_peak_h": float(t[int(q.argmax())] / 3600.0),
            "volume_m3": float(np.trapezoid(q, t)),
        }  # fmt: skip
    return {"cfg": cfg, "crs": crs, "basin": basin, "hms_basin": hms_basin, "factors": factors, "flows": flows,
            "entries": entries, "series": series, "network_s": seconds}  # fmt: skip


def run3_mesh():
    """Run 3's tables and strip from its cache, by the keys they were saved under; None when they will not load."""
    tables = load_tables(RUN3_GRID, RUN3_GRID.stem.removeprefix("grid_"))
    held = load_strip(RUN3_STRIP, RUN3_STRIP.stem.removeprefix("strip_"))
    if tables is None or held is None:
        return None
    tables.strip = held[1]
    return tables


def placed(got: dict, tables) -> dict[str, tuple[float, float]]:
    """Each entry's point on the mesh, as the run's ``_placed_entries`` moves it first (W88, W105)."""
    left = R.left_out_of(got["cfg"], got["crs"])
    tables.left_out = left
    moved = {s.name: s for s in snap_entries(got["cfg"], tables, got["flows"], left)}
    return {name: (moved[name].point if name in moved else (e["x"], e["y"])) for name, e in got["entries"].items()}, left


def main() -> None:
    OUT.mkdir(exist_ok=True)
    summary: dict = {"last_points": LAST_POINTS, "jobs": {case: [str(a), str(b)] for case, (a, b) in CASES.items()}}
    t0 = time.monotonic()
    tables = run3_mesh()
    summary["run3_mesh_loaded"] = tables is not None
    summary["run3_mesh_load_s"] = round(time.monotonic() - t0, 1)
    kept: dict = {}
    for case, (hand_path, way_path) in CASES.items():
        hand = read(RunConfig.model_validate(json.loads(hand_path.read_text(encoding="utf-8"))))
        way = read(dock_way(way_path, LAST_POINTS))
        dams = read(dock_way(way_path, None))  # the default: the dams alone
        names = sorted(hand["factors"])
        factor_rows = [{
            "subbasin": n, "factor_W79": round(hand["factors"][n], 6), "factor_dock_way": round(way["factors"][n], 6),
            "difference": round(way["factors"][n] - hand["factors"][n], 6),
            "factor_dams_only": round(dams["factors"][n], 6),
        } for n in names]  # fmt: skip
        write_csv(OUT / f"factors_{case.replace(' ', '_')}.csv", factor_rows)
        by_element = {e["element"]: (name, e) for name, e in way["entries"].items()}
        points = {}
        if case == "Hybrid Lumped" and tables is not None:
            points["hand"], left_hand = placed(hand, tables)
            points["way"], left_way = placed(way, tables)
            summary["left_out_same"] = sorted(left_hand.names) == sorted(left_way.names)
            recorded = {e["name"]: e["point"] for e in json.loads(RUN3_ENTRIES.read_text(encoding="utf-8"))}
            summary["run3_recorded_point_reproduced"] = {
                name: math.hypot(points["hand"][name][0] - p[0], points["hand"][name][1] - p[1]) for name, p in recorded.items()
            }  # fmt: skip
            area = left_way.area
            icons = hms_icons(way["hms_basin"])
        entry_rows = []
        for name, e in hand["entries"].items():
            auto_name, auto = by_element.get(e["element"], (None, None))
            row = {
                "entry": name, "element": e["element"],
                "peak_W79": round(e["peak_m3s"], 3), "peak_dock_way": round(auto["peak_m3s"], 3) if auto else None,
                "volume_W79_Mm3": round(e["volume_m3"] / 1e6, 5),
                "volume_dock_way_Mm3": round(auto["volume_m3"] / 1e6, 5) if auto else None,
                "time_of_peak_W79_h": round(e["time_of_peak_h"], 3),
                "time_of_peak_dock_way_h": round(auto["time_of_peak_h"], 3) if auto else None,
                "peak_difference_m3s": round(auto["peak_m3s"] - e["peak_m3s"], 6) if auto else None,
                "volume_ratio": round(auto["volume_m3"] / e["volume_m3"], 6) if auto and e["volume_m3"] else None,
            }  # fmt: skip
            if points and auto:
                hx, hy = points["hand"][name]
                ax, ay = points["way"][auto_name]
                ix, iy = icons[e["element"]]
                row |= {
                    "x_W79": round(hx, 2), "y_W79": round(hy, 2), "x_dock_way": round(ax, 2), "y_dock_way": round(ay, 2),
                    "distance_m": round(math.hypot(ax - hx, ay - hy), 1), "distance_cells": round(math.hypot(ax - hx, ay - hy) / DX_M, 2),
                    "W79_from_left_out_m": round(shapely.Point(hx, hy).distance(area), 1),
                    "dock_way_from_left_out_m": round(shapely.Point(ax, ay).distance(area), 1),
                    "icon_to_dock_way_m": round(math.hypot(ax - ix, ay - iy), 1),
                }  # fmt: skip
                dam = DAMS.get(e["element"])
                if dam is not None:  # W79's dam lines and chutes (inputs.json), which run 3's job does not carry
                    axis = shapely.LineString(dam["axis"])
                    chutes = [shapely.LineString(s["coordinates"]) for s in dam["spillways"]]
                    row |= {
                        "W79_to_dam_axis_m": round(shapely.Point(hx, hy).distance(axis), 1),
                        "dock_way_to_dam_axis_m": round(shapely.Point(ax, ay).distance(axis), 1),
                        "dock_way_to_chutes_m": [round(shapely.Point(ax, ay).distance(c), 1) for c in chutes],
                        "W79_to_chutes_m": [round(shapely.Point(hx, hy).distance(c), 1) for c in chutes],
                    }  # fmt: skip
            entry_rows.append(row)
        write_csv(OUT / f"entries_{case.replace(' ', '_')}.csv", entry_rows)
        record = way["series"].record if way["series"] is not None else None
        summary[case] = {
            "lumped_subbasins": len(names),
            "factor_difference": {"min": min(r["difference"] for r in factor_rows), "max": max(r["difference"] for r in factor_rows)},
            "entries_W79": len(hand["entries"]), "entries_dock_way": len(way["entries"]),
            "entries_dams_only": sorted(e["element"] for e in dams["entries"].values()),
            "network_seconds": {"W79": round(hand["network_s"], 2), "dock way": round(way["network_s"], 2)},
            "entries": entry_rows,
            "record": record,
        }  # fmt: skip
        print(f"== {case}: {json.dumps({k: v for k, v in summary[case].items() if k not in ('entries', 'record')})}")
        for row in entry_rows:
            print("  ", json.dumps(row))
        kept[case] = way
    summary["own_and_dam_factors"] = own_and_dam(summary, kept)
    (OUT / "compare_last_points.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in CASES}, indent=1))


def own_and_dam(summary: dict, kept: dict) -> list[dict]:
    """The elements above each dam that Hybrid Lumped reports at their own drainage area (its series of record), beside
    the factor and the hydrograph the same subbasins take in Hybrid 2D, their dam's."""
    lumped = summary["Hybrid Lumped"]["record"] or {}
    reruns = kept["Hybrid Lumped"]["series"].own_area
    two_d = {row["subbasin"]: row for row in (summary["Hybrid 2D"]["record"] or {}).get("subbasins", [])}
    entered = kept["Hybrid 2D"]["entries"]
    rows = []
    for element in lumped.get("elements", []):
        name = element["element"]
        own = np.asarray(reruns[name].outflow[name]) if name in reruns else None
        rows.append({
            "element": name, "enters_at": element["enters_at"],
            "own_area_km2": element["own_area_km2"], "own_factor": element["own_factor"],
            "own_area_peak_m3s": round(float(own.max()), 2) if own is not None else None,
            "hybrid_2d_area_km2": two_d[name]["storm_area_km2"] if name in two_d else None,
            "hybrid_2d_factor": two_d[name]["factor"] if name in two_d else None,
            "hybrid_2d_peak_m3s": round(entered[name]["peak_m3s"], 2) if name in entered else None,
            "hybrid_2d_read_at": two_d[name]["read_at"] if name in two_d else None,
        })  # fmt: skip
    write_csv(OUT / "own_area_and_dam_factor.csv", rows)
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
