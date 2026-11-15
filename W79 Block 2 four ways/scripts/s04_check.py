"""The check of a finished run before the next starts, and each dam's inflow and outflow in it.

Usage: s04_check.py <run number> [run folder name]. The folder defaults to the run's own; runs/run1_full_2d, the
superseded squares run, is read with ``1 run1_full_2d`` (its job file is its config.resolved.json). Reads the run folder and writes ``w79_check.json`` beside it:

- it finished (the engine's ``done`` event, code 0, not partial);
- the mass balance (relative error of the engine's books);
- every warning the run raised, the domain-edge check's among them (W78: streams across a closed edge, pools against it);
- the setup it ran against its description (lumped elements, inflows, terrain objects, where each entry went);
- each dam's inflow and outflow: peak, time to peak from the storm's start, volume over the run.

Dam inflow and outflow by run:
- 1 and 4 (dams as 2D pools): outflow is the dam line (W1's line along the crest); inflow is the line round the pool's
  upstream edge, plus, in run 4, the lumped hydrographs that enter on the grid inside that line (their series of
  record, ``series/network_<subbasin>.csv``). In run 1 the rain that falls inside the line, on the pool and its
  margin, is in neither: its size is given per dam.
- 2 and 3 (lumped reservoirs): the reservoir's own inflow and outflow in the lumped network's series.
A line's sign is set so that its run volume is positive: a line reads positive to its right, and W1's lines were not
all drawn the same way round.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Point, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w79 import DAMS, INPUTS, JOBS, RESERVOIR, RUN_NAMES, RUNS, load_json, write_json  # noqa: E402

from wadi2d.io.results import safe_name  # noqa: E402


def read_series(path: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    with path.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    head, data = rows[0], np.array(rows[1:], float)
    return data[:, 0], {h: data[:, i] for i, h in enumerate(head) if i}


def stats(t: np.ndarray, q: np.ndarray) -> dict:
    return {
        "peak_m3s": float(q.max()), "time_to_peak_h": float(t[int(q.argmax())] / 3600.0),
        "volume_Mm3": float(np.trapezoid(q, t) / 1e6),
    }


def progress(folder: Path) -> tuple[dict, list[str], list[dict]]:
    done, warns, entries = {}, [], []
    for line in (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines():
        ev = json.loads(line)
        if ev.get("ev") == "done":
            done = ev
        elif ev.get("ev") == "warn":
            warns.append(ev.get("message", ""))
    if (folder / "entries.json").is_file():
        entries = load_json(folder / "entries.json")
    return done, warns, entries


def pools() -> dict[str, shapely.Geometry]:
    out = {}
    for f in load_json(INPUTS / "dams.geojson")["features"]:
        if f["properties"]["kind"].startswith("pool_"):
            out[f["properties"]["dam"]] = shape(f["geometry"]).buffer(60.0)
    return out


def line_flow(folder: Path, name: str) -> tuple[np.ndarray, np.ndarray, float]:
    t, cols = read_series(folder / "series" / f"line_{safe_name(name)}.csv")
    q = cols["discharge_m3s"]
    sign = 1.0 if np.trapezoid(q, t) >= 0.0 else -1.0
    return t, sign * q, sign


def grid_dams(number: int, folder: Path, entries: list[dict]) -> dict:
    out = {}
    pool = pools()
    for dam in DAMS:
        t, q_out, s_out = line_flow(folder, dam)
        t_in, q_ring, s_in = line_flow(folder, f"{dam} inflow")
        q_in = q_ring.copy()
        inside = []
        for e in entries:
            if pool[dam].contains(Point(e["point"])):
                tn, cols = read_series(folder / "series" / f"network_{safe_name(e['name'])}.csv")
                q_in = q_in + np.interp(t_in, tn, cols["outflow_m3s"])
                inside.append(e["name"])
        out[dam] = {
            "inflow": stats(t_in, q_in), "outflow": stats(t, q_out),
            "inflow_source": "line round the pool" + (f" + lumped entries inside it: {', '.join(inside)}" if inside else ""),
            "outflow_source": "dam line", "ring_sign": s_in, "dam_line_sign": s_out, "ring_alone": stats(t_in, q_ring),
            "pool_area_km2": float(pool[dam].area / 1e6),
        }
    return out


def lumped_dams(folder: Path) -> dict:
    out = {}
    for dam in DAMS:
        t, cols = read_series(folder / "series" / f"network_{safe_name(RESERVOIR[dam])}.csv")
        out[dam] = {"inflow": stats(t, cols["inflow_m3s"]), "outflow": stats(t, cols["outflow_m3s"]),
                    "inflow_source": "lumped reservoir inflow", "outflow_source": "lumped reservoir outflow",
                    "max_pool_m": float(cols["pool_m"].max()), "max_storage_Mm3": float(cols["storage_m3"].max() / 1e6)}
        line = folder / "series" / f"line_{safe_name(dam)}.csv"
        if line.is_file():
            tl, q, _ = line_flow(folder, dam)
            out[dam]["grid_dam_line_peak_m3s"] = float(q.max())
    return out


def setup(number: int, folder: Path) -> dict:
    own = JOBS / f"{folder.name}.json"
    job = load_json(own if own.is_file() else folder / "config.resolved.json")
    h = job["hydrology"]
    subs = h.get("subbasins", [])
    return {
        "lumped": sum(1 for s in subs if s["mode"] == "lumped"),
        "lumped_entering_at_outlet": sum(1 for s in subs if s["mode"] == "lumped" and s.get("outlet")),
        "rain_on_grid_subbasins": sum(1 for s in subs if s["mode"] == "2d"),
        "inflows": [(i["name"], i.get("element")) for i in h.get("inflows", [])],
        "crest_lines": sum(1 for o in job["terrain"]["objects"] if o["kind"] == "crest_line"),
        "spillways": sum(1 for o in job["terrain"]["objects"] if o["kind"] == "spillway"),
        "storm_area_km2": job["storm"]["storm_area_km2"], "depth_mm": job["storm"]["depth_mm"],
    }


def main(number: int, name: str | None = None) -> None:
    name = name or RUN_NAMES[number]
    folder = RUNS / name
    report = {"run": number, "name": name, "setup": setup(number, folder),
              "strips": load_json(folder / "config.resolved.json").get("strips", {}).get("generator") if number != 2 else None}
    if number == 2:
        report["finished"] = True
        report["note"] = load_json(folder / "run2_summary.json")
        report["dams"] = lumped_dams(folder)
    else:
        done, warns, entries = progress(folder)
        bal = done.get("balance", {})
        report.update({
            "finished": done.get("status") == "finished" and done.get("code") == 0 and not done.get("partial"),
            "status": done.get("status"), "code": done.get("code"), "steps": done.get("steps"),
            "loop_s": done.get("loop_s"), "tables_s": done.get("tables_s"), "products": done.get("products"),
            "relative_mass_error": bal.get("relative_error"), "balance": bal, "warnings": warns,
            "entries": entries,
        })
        report["dams"] = lumped_dams(folder) if number == 3 else grid_dams(number, folder, entries)
    write_json(folder / "w79_check.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("entries", "balance")}, indent=1)[:6000])


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else None)
