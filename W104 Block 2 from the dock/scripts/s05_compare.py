"""The dam inflow and outflow peaks of the four W104 runs, against W79's four, and each run's stages.

Run with the project's venv after the runs: ``s05_compare.py``. Reads ``runs/<model>/`` and writes
``dam_peaks.csv`` and ``dam_peaks.json`` here. How each figure is read, as W79 read its own:

- a dam that is a lumped reservoir (Lumped, Hybrid Lumped): the reservoir's inflow and outflow in the lumped network's
  series (``series/network_<dam>.csv``);
- a dam that is a 2D pool (2D, Hybrid 2D): the outflow on the dam line; the inflow by the pool's own balance, the
  change of the water in the pool polygon between two saved maps plus the dam-line outflow between them, a 15-min
  mean (W79's ``s04_check.py``, the same pool polygons: W79's pool at the spillway crest + 0.3 m, buffered 60 m).

Also each run's ARF factors where the run says them, its mass balance and the engine's stage seconds.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from shapely.geometry import shape

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parent
RUNS = HERE / "runs"
DAMS = ("Bidah 03", "Faydh 01", "R5A", "R2A", "Z4C")
MODELS = {"Lumped": "lumped", "2D": "grid", "HybridLumped": "lumped", "Hybrid2D": "grid"}
W79 = {  # W79 README, the final runs (dam_peaks.csv there): in / out, m3/s
    "2D": {"Bidah 03": (581, 0), "Faydh 01": (2314, 0), "R5A": (2071, 608), "R2A": (3958, 1151), "Z4C": (3240, 3455)},
    "Lumped": {"Bidah 03": (455, 0), "Faydh 01": (1240, 0), "R5A": (1144, 754), "R2A": (1736, 818), "Z4C": (2101, 2025)},
    "HybridLumped": {"Bidah 03": (455, 0), "Faydh 01": (1240, 0), "R5A": (1144, 754), "R2A": (1736, 818), "Z4C": (2101, 2025)},
    "Hybrid2D": {"Bidah 03": (444, 0), "Faydh 01": (1221, 0), "R5A": (1115, 671), "R2A": (1516, 857), "Z4C": (1941, 2018)},
}


def safe(name: str) -> str:
    from wadi2d.io.results import safe_name

    return safe_name(name)


def read_series(path: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    with path.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    data = np.array(rows[1:], float)
    return data[:, 0], {h: data[:, i] for i, h in enumerate(rows[0]) if i}


def stats(t: np.ndarray, q: np.ndarray) -> dict:
    return {"peak_m3s": float(q.max()), "time_to_peak_h": float(t[int(q.argmax())] / 3600.0),
            "volume_Mm3": float(np.trapezoid(q, t) / 1e6)}  # fmt: skip


def pools() -> dict:
    features = json.loads((REPO / "W79 Block 2 four ways" / "inputs" / "dams.geojson").read_text(encoding="utf-8"))
    return {f["properties"]["dam"]: shape(f["geometry"]).buffer(60.0) for f in features["features"]
            if f["properties"]["kind"].startswith("pool_")}  # fmt: skip


def pool_storage(folder: Path, pool: dict) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """W79's: the squares' mean depth times their area plus the aligned cells' (by centroid), at every saved map."""
    import geopandas as gpd
    import h5py
    from affine import Affine
    from rasterio import features

    with h5py.File(folder / "results.h5", "r") as f:
        mask = f["mask"][:].astype(bool)
        x0, y0, dx = (float(f.attrs[k]) for k in ("x0", "y0", "dx"))
        names = sorted(f["maps"].keys())
        lab = features.rasterize([(pool[d], i + 1) for i, d in enumerate(DAMS)], out_shape=mask.shape,
                                 transform=Affine(dx, 0, x0, 0, -dx, y0), fill=0, dtype="uint8")  # fmt: skip
        strip = folder / "maps" / "strip_mesh.gpkg"
        cells = gpd.read_file(strip, layer="strip_cells", columns=["cell", "area_m2"]) if strip.is_file() else None
        if cells is not None:
            c = cells.geometry.centroid
            sj = np.clip(np.floor((y0 - c.y.to_numpy()) / dx).astype(int), 0, mask.shape[0] - 1)
            si = np.clip(np.floor((c.x.to_numpy() - x0) / dx).astype(int), 0, mask.shape[1] - 1)
            slab, sidx, sarea = lab[sj, si], cells["cell"].to_numpy(), cells["area_m2"].to_numpy()
        where = {d: np.nonzero(mask & (lab == i + 1)) for i, d in enumerate(DAMS)}
        t = np.array([0.0] + [float(int(n[1:])) for n in names])
        out = {d: [0.0] for d in DAMS}
        for n in names:
            depth = f["maps"][n]["mean_depth"][:]
            sdepth = f["maps"][n]["strip_mean_depth"][0] if "strip_mean_depth" in f["maps"][n] else None
            for i, d in enumerate(DAMS):
                v = float(depth[where[d]].sum()) * dx * dx
                if sdepth is not None and cells is not None:
                    on = slab == i + 1
                    v += float((sdepth[sidx[on]] * sarea[on]).sum())
                out[d].append(v)
    return t, {d: np.array(v) for d, v in out.items()}


def balance_inflow(t, storage, t_out, q_out) -> dict:
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
            "volume_Mm3": float((storage[-1] - storage[0] + np.trapezoid(q_out, t_out)) / 1e6)}  # fmt: skip


def line_flow(folder: Path, name: str):
    t, cols = read_series(folder / "series" / f"line_{safe(name)}.csv")
    q = cols["discharge_m3s"]
    return t, (1.0 if np.trapezoid(q, t) >= 0.0 else -1.0) * q


def network(folder: Path, dam: str) -> Path | None:
    found = sorted((folder / "series").glob(f"network_{safe(dam)}*.csv"))
    exact = [p for p in found if p.stem == f"network_{safe(dam)}"]
    return (exact or found or [None])[0]


def dams_of(model: str, folder: Path) -> dict:
    out = {}
    if MODELS[model] == "lumped":
        for dam in DAMS:
            path = network(folder, dam)
            if path is None:
                continue
            t, cols = read_series(path)
            out[dam] = {"inflow": stats(t, cols["inflow_m3s"]), "outflow": stats(t, cols["outflow_m3s"]),
                        "read": f"lumped reservoir {path.stem[8:]}"}  # fmt: skip
        return out
    t_maps, stored = pool_storage(folder, pools())
    for dam in DAMS:
        t, q = line_flow(folder, dam)
        out[dam] = {"inflow": balance_inflow(t_maps, stored[dam], t, q), "outflow": stats(t, q),
                    "read": "pool balance (15-min mean) / dam line"}  # fmt: skip
    return out


def run_facts(folder: Path) -> dict:
    facts = {}
    for line in (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines():
        ev = json.loads(line)
        if ev.get("ev") == "done":
            b = ev.get("balance") or {}
            facts.update({k: ev.get(k) for k in ("status", "code", "steps", "loop_s", "tables_s", "wet_area_km2")})
            facts["mass_error"] = b.get("relative_error")
            facts["rain_Mm3"] = (b.get("rain_m3") or 0) / 1e6
            facts["inflow_Mm3"] = (b.get("inflow_m3") or 0) / 1e6
            facts["outflow_Mm3"] = (b.get("outflow_m3") or 0) / 1e6
        elif ev.get("ev") == "start":
            facts["cells"], facts["tiles"] = ev.get("cells"), ev.get("tiles")
        elif ev.get("ev") == "left_out":
            facts["left_out_km2"], facts["left_out_subbasins"] = ev.get("area_km2"), len(ev.get("subbasins", []))
        elif ev.get("ev") == "output" and ev.get("kind") in ("lumped_entry_areas", "subbasin_storm_areas"):
            facts[ev["kind"]] = {k: v for k, v in ev.items() if k not in ("ev", "kind")}
    return facts


def main() -> None:
    table, rows = {}, []
    for model in MODELS:
        folder = RUNS / model
        if not (folder / "progress.jsonl").is_file():
            continue
        dams = dams_of(model, folder)
        table[model] = {"dams": dams, "run": run_facts(folder)}
        for dam, d in dams.items():
            old_in, old_out = W79[model][dam]
            rows.append([model, dam, round(d["inflow"]["peak_m3s"], 1), round(d["outflow"]["peak_m3s"], 1), old_in, old_out,
                         round(d["inflow"]["peak_m3s"] / old_in - 1.0, 3) if old_in else None,
                         round(d["inflow"]["time_to_peak_h"], 2), round(d["inflow"]["volume_Mm3"], 2), d["read"]])  # fmt: skip
    with (HERE / "dam_peaks.csv").open("w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["model", "dam", "in_m3s", "out_m3s", "w79_in_m3s", "w79_out_m3s", "in_vs_w79", "in_peak_h", "in_Mm3", "read"])
        out.writerows(rows)
    (HERE / "dam_peaks.json").write_text(json.dumps(table, indent=1), encoding="utf-8")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
