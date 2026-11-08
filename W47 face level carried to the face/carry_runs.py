"""Option A, the upwind depth carry, on the slope cases (W47, 2026-11-08): the W46 jobs rerun on this branch's kernels
into ``depth_carry/``, each with its own cache, nothing of W46 overwritten.

* straight: the straight synthetic valley, 300 m3/s steady (ramped over an hour), 1 %, squares at 20, 10, 5 m and the
  centre mesh at 20 m; the stored water at the end against the 5 m squares.
* steady: Faydh's main stem, 4 to 20 km, 300 m3/s steady, squares at 20, 10, 5, 2 m and the strip at 20 and 10 m,
  frames saved; the final surface and the water held in the 20 m strip's footprint against the 2 m squares.
* flood: the same reach under the flash flood with no rain; the peak at 6, 10, 14 and 18 km (median of three lines)
  against the 2 m squares.
* race: the rain-on-grid race to the dam axis, 16 h: 20 m squares, W45 rings, the centre mesh at 20 and 10 m,
  squares at 10 and 5 m.

    .venv\\Scripts\\python "W47 face level carried to the face\\carry_runs.py" [straight steady flood race report]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
OUT = HERE / "depth_carry"
W45 = ROOT / "W45 aligned mesh engine" / "race_faydh"
W46 = ROOT / "W46 centre-based mesh generator"
SETS = {
    "straight": {m: W46 / "probe_wave" / "straight" / f"straight_steady_{m}.json" for m in ("sq20", "ce20", "sq10", "sq5")},
    "steady": {m: W46 / "race_faydh" / "reach_long_steady_ramp" / f"{m}.json" for m in ("sq20", "ce20", "sq10", "ce10", "sq5", "sq2")},
    "flood": {m: W46 / "race_faydh" / "reach_long" / f"{m}.json" for m in ("sq20", "ce20", "sq10", "ce10", "sq5", "sq2")},
    "race": {
        "sq20": W45 / "faydh20_none_gpu.json", "rings20": W45 / "faydh20_strips_gpu.json",
        "ce20": W46 / "race_faydh" / "faydh20_centres_gpu.json", "sq10": W46 / "race_faydh" / "faydh10_none_gpu.json",
        "ce10": W46 / "race_faydh" / "faydh10_centres_gpu.json", "sq5": W46 / "race_faydh" / "faydh5_none_gpu.json",
    },
}
BEFORE = {
    # the same numbers on the kernel before the carry, from W46's record
    "straight_stored_vs_sq5": {"sq20": -0.025, "ce20": -0.025, "sq10": -0.010},
    "steady_water_vs_sq2": {"sq20": 0.010, "sq10": -0.011, "sq5": -0.007, "ce20": -0.093, "ce10": -0.042},
    "flood_k18_vs_sq2": {"sq20": -0.050, "sq10": -0.007, "sq5": 0.002, "ce20": 0.042, "ce10": 0.037},
    "race_axis": {"sq20": 1835.2, "rings20": 1879.9, "ce20": 1987.0, "sq10": 1871.3, "ce10": 1918.8, "sq5": 1887.1},
}


def job(kind: str, name: str) -> Path:
    data = json.loads(SETS[kind][name].read_text(encoding="utf-8"))
    work = OUT / kind
    work.mkdir(parents=True, exist_ok=True)
    data["grid"]["cache_dir"] = str(work / "cache")
    if kind == "steady":
        data["outputs"]["map_every_s"] = 10_800.0  # frames at 3 and 6 h: the final state, which the maxima are not
    path = work / f"{name}.json"
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return path


def run(kind: str) -> None:
    exe = ROOT / ".venv" / "Scripts" / "wadi2d.exe"
    for name in SETS[kind]:
        path = job(kind, name)
        t0 = time.perf_counter()
        done = subprocess.run([str(exe), "run", str(path), "--out", str(path.with_suffix(""))], capture_output=True, text=True)
        path.with_suffix(".log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
        print(f"{kind}/{name}: exit {done.returncode} in {time.perf_counter() - t0:.0f} s", flush=True)


def finished(folder: Path) -> dict | None:
    prog = folder / "progress.jsonl"
    if not prog.is_file():
        return None
    done = [json.loads(s) for s in prog.read_text(encoding="utf-8").splitlines() if '"done"' in s[:14]]
    return done[-1] if done else None


def peak(folder: Path, line: str) -> float:
    rows = (folder / "series" / f"line_{line}.csv").read_text(encoding="utf-8").splitlines()[1:]
    return float(np.abs(np.array([float(r.split(",")[1]) for r in rows])).max())


def report() -> dict:
    out: dict = {}
    # straight valley: stored water at the end against the 5 m squares
    w = OUT / "straight"
    stored = {n: (finished(w / n) or {}).get("balance", {}).get("storage_end_m3") for n in SETS["straight"]}
    if stored.get("sq5"):
        out["straight_stored_vs_sq5"] = {n: v / stored["sq5"] - 1 for n, v in stored.items() if v and n != "sq5"}
    # the reach under the flash flood: the 18 km peak, median of three lines, against the 2 m squares
    w = OUT / "flood"
    if finished(w / "sq2"):
        med = {n: {km: float(np.median([peak(w / n, f"k{km:02d}{t}") for t in "abc"])) for km in (6, 10, 14, 18)} for n in SETS["flood"] if finished(w / n)}
        out["flood_vs_sq2"] = {n: {km: v / med["sq2"][km] - 1 for km, v in r.items()} for n, r in med.items() if n != "sq2"}
    # the steady reach: the final surface and the water in the 20 m strip's footprint, against the 2 m squares
    w = OUT / "steady"
    if finished(w / "sq2") and finished(w / "ce20"):
        sys.path.insert(0, str(HERE))
        import steady_surfaces as ss  # noqa: PLC0415

        out["steady"] = surfaces(ss, w)
    # the race
    w = OUT / "race"
    axis = {n: peak(w / n, "axis") for n in SETS["race"] if finished(w / n)}
    out["race_axis"] = axis
    if "sq5" in axis:
        out["race_vs_sq5"] = {n: v / axis["sq5"] - 1 for n, v in axis.items() if n != "sq5"}
    if "sq20" in axis and "ce20" in axis:
        out["race_ce20_vs_sq20"] = axis["ce20"] / axis["sq20"] - 1
    (OUT / "carry_runs.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return out


def surfaces(ss, folder: Path) -> dict:
    """The final steady surfaces inside the 20 m strip's footprint against the 2 m squares (steady_surfaces.py's rule)."""
    import fiona
    import rasterio
    import shapely
    from rasterio import features
    from rasterio.windows import from_bounds

    geoms = []
    with fiona.open(folder / "ce20" / "maps" / "strip_mesh.gpkg", layer="strip_cells") as src:
        for feat in src:
            geoms.append(shapely.geometry.shape(feat["geometry"]))
    xmin, ymin, xmax, ymax = shapely.total_bounds(np.array(geoms, dtype=object))
    with rasterio.open(ss.DEM) as src:
        win = from_bounds(xmin - 2, ymin - 2, xmax + 2, ymax + 2, src.transform).round_offsets().round_lengths()
        z = src.read(1, window=win).astype(np.float64)
        tr = src.window_transform(win)
        p = src.res[0]
        z[z > 1e30] = np.nan
    inside = features.rasterize(((g, 1) for g in geoms), out_shape=z.shape, transform=tr, fill=0, dtype="uint8") == 1
    xs = tr.c + (np.arange(z.shape[1]) + 0.5) * tr.a
    ys = tr.f + (np.arange(z.shape[0]) + 0.5) * tr.e
    res = {}
    surf = {}
    for name in SETS["steady"]:
        run_dir = folder / name
        if not finished(run_dir):
            continue
        level, ltr, _t = ss.final_lattice_level(run_dir)
        cols = np.clip(((xs - ltr.c) / ltr.a).astype(int), 0, level.shape[1] - 1)
        rows = np.clip(((ys - ltr.f) / ltr.e).astype(int), 0, level.shape[0] - 1)
        s = level[rows[:, None], cols[None, :]]
        strip = run_dir / "maps" / "strip_mesh.gpkg"
        if strip.is_file():
            g, lev = [], []
            with fiona.open(strip, layer="strip_cells") as src:
                for feat in src:
                    g.append(shapely.geometry.shape(feat["geometry"]))
                    lev.append(feat["properties"]["level_end_m"])
            owner = features.rasterize(((gg, k) for k, gg in enumerate(g)), out_shape=z.shape, transform=tr, fill=-1, dtype="int32")
            s = np.where(owner >= 0, np.asarray(lev)[np.clip(owner, 0, None)], s)
        surf[name] = s
    ref = surf["sq2"]
    vr = np.nansum(np.clip(ref - z, 0, None)[inside]) * p * p
    for name, s in surf.items():
        if name == "sq2":
            continue
        wet = inside & ((s > z + 0.01) | (ref > z + 0.01))
        v = np.nansum(np.clip(s - z, 0, None)[inside]) * p * p
        res[name] = {"surface_mean_m": float(np.nanmean((s - ref)[wet])), "water": float(v / vr - 1)}
    return res


if __name__ == "__main__":
    what = sys.argv[1:] or ["straight", "steady", "flood", "race", "report"]
    for kind in what:
        if kind in SETS:
            run(kind)
    if "report" in what:
        report()
