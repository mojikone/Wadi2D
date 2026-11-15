"""The check of a finished run before the next starts, and each dam's inflow and outflow in it.

Usage: s04_check.py <run number> [run folder name]. The folder defaults to the run's own; runs/run1_full_2d, the
superseded squares run, is read with ``1 run1_full_2d`` (its job file is its config.resolved.json). Reads the run folder and writes ``w79_check.json`` beside it:

- it finished (the engine's ``done`` event, code 0, not partial);
- the mass balance (relative error of the engine's books);
- every warning the run raised, the domain-edge check's among them (W78: streams across a closed edge, pools against it);
- the setup it ran against its description (lumped elements, inflows, terrain objects, where each entry went);
- each dam's inflow and outflow: peak, time to peak from the storm's start, volume over the run.

Dam inflow and outflow by run:
- 1 and 4 (dams as 2D pools): outflow is the dam line (W1's line along the crest). Inflow is the pool's own balance:
  the change of the water in the pool polygon between two saved maps (squares and aligned cells, from results.h5) plus
  the dam-line outflow in between, a 15-min mean; its volume is exact, its peak a 15-min mean. In run 1 it holds the
  rain that falls on the pool. The line round the pool's upstream edge (plus, in run 4, the lumped entries inside it)
  is kept as ``inflow_by_ring``: it over-reads where the line crosses a wadi more than once (run 4: R5A +3.6 Mm3,
  R2A +2.9, Faydh 01 +0.5 against the pool balance, which closes on the lumped hydrographs within 0.3 %).
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


def leaving(warns: list[str], least_km2: float) -> list[str]:
    """The edge check's streams that leave through a closed edge (W78), of ``least_km2`` or more."""
    import re

    out = []
    for w in warns:
        m = re.search(r"a stream draining ([0-9.]+) km2 leaves the domain at \(([0-9]+), ([0-9]+)\)", w)
        if m and float(m.group(1)) >= least_km2 and (least_km2 > 0.0 or float(m.group(1)) < 1.0):
            out.append(f"{m.group(1)} km2 at ({m.group(2)}, {m.group(3)})")
    return out


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


def pool_storage(folder: Path, pool: dict[str, shapely.Geometry]) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Water in each pool polygon at every saved map, m3: the squares' mean depth times their area plus the aligned
    cells' (by centroid), from results.h5; the start of the run, dry, is put in front."""
    import geopandas as gpd
    import h5py
    from affine import Affine
    from rasterio import features

    with h5py.File(folder / "results.h5", "r") as f:
        mask = f["mask"][:].astype(bool)
        x0, y0, dx = (float(f.attrs[k]) for k in ("x0", "y0", "dx"))
        names = sorted(f["maps"].keys())
        lab = features.rasterize([(pool[d], i + 1) for i, d in enumerate(DAMS)], out_shape=mask.shape,
                                 transform=Affine(dx, 0, x0, 0, -dx, y0), fill=0, dtype="uint8")
        cells = gpd.read_file(folder / "maps" / "strip_mesh.gpkg", layer="strip_cells", columns=["cell", "area_m2"])
        c = cells.geometry.centroid
        sj = np.clip(np.floor((y0 - c.y.to_numpy()) / dx).astype(int), 0, mask.shape[0] - 1)
        si = np.clip(np.floor((c.x.to_numpy() - x0) / dx).astype(int), 0, mask.shape[1] - 1)
        slab, sidx, sarea = lab[sj, si], cells["cell"].to_numpy(), cells["area_m2"].to_numpy()
        where = {d: np.nonzero(mask & (lab == i + 1)) for i, d in enumerate(DAMS)}
        swhere = {d: slab == i + 1 for i, d in enumerate(DAMS)}
        t = np.array([0.0] + [float(int(n[1:])) for n in names])
        out = {d: [0.0] for d in DAMS}
        for n in names:
            depth = f["maps"][n]["mean_depth"][:]
            strip = f["maps"][n]["strip_mean_depth"][0] if "strip_mean_depth" in f["maps"][n] else None
            for d in DAMS:
                v = float(depth[where[d]].sum()) * dx * dx
                if strip is not None:
                    v += float((strip[sidx[swhere[d]]] * sarea[swhere[d]]).sum())
                out[d].append(v)
    return t, {d: np.array(v) for d, v in out.items()}


def balance_inflow(t: np.ndarray, storage: np.ndarray, t_out: np.ndarray, q_out: np.ndarray) -> dict:
    """The pool's inflow by its own balance: the change of the water in the pool between two saved maps plus what left
    over the dam line in between, as a mean flow over each interval (15 min). It needs no line across the wadi."""
    flow, mid = [], []
    for a, b in zip(t[:-1], t[1:], strict=True):
        if b <= a:
            continue
        inside = (t_out >= a) & (t_out <= b)
        left = np.trapezoid(q_out[inside], t_out[inside]) if inside.sum() > 1 else 0.0
        flow.append((storage[len(mid) + 1] - storage[len(mid)] + left) / (b - a))
        mid.append(b)
    flow, mid = np.array(flow), np.array(mid)
    k = int(flow.argmax())
    return {"peak_m3s": float(flow[k]), "time_to_peak_h": float(mid[k] / 3600.0),
            "volume_Mm3": float((storage[-1] - storage[0] + np.trapezoid(q_out, t_out)) / 1e6),
            "stored_at_end_Mm3": float(storage[-1] / 1e6), "most_stored_Mm3": float(storage.max() / 1e6)}


def grid_dams(number: int, folder: Path, entries: list[dict]) -> dict:
    out = {}
    pool = pools()
    t_maps, stored = pool_storage(folder, pool)
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
            "inflow": balance_inflow(t_maps, stored[dam], t, q_out), "outflow": stats(t, q_out),
            "inflow_source": "pool balance: change of the water in the pool + dam-line outflow, 15-min means",
            "inflow_by_ring": stats(t_in, q_in),
            "ring_source": "line round the pool" + (f" + lumped entries inside it: {', '.join(inside)}" if inside else ""),
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
        "subbasin_storm_areas_km2": {s["name"]: s["storm_area_km2"] for s in subs if s.get("storm_area_km2")},
        "pixel_stride": job["terrain"]["pixel_stride"],
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
            "edge_streams_leaving_1km2": leaving(warns, 1.0),
            "edge_streams_leaving_small": leaving(warns, 0.0),
        })
        report["dams"] = lumped_dams(folder) if number == 3 else grid_dams(number, folder, entries)
    write_json(folder / "w79_check.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("entries", "balance")}, indent=1)[:6000])


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else None)
