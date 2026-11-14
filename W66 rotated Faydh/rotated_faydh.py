"""Faydh 01 turned 30 degrees: does the square mesh's dam-axis peak move with the lattice angle (W66, W57's settling test)?

The 0.5 m DEM, the domain polygon, the outflow boundary, the result lines and the Suggest breaklines file are all turned
30 degrees anticlockwise about the domain's centroid; the storm (uniform, hypothetical) needs nothing. The DEM is
resampled bilinearly through GDAL with the turn written into the source transform. Jobs are W49's race jobs (squares,
`race_faydh_top_fix`) and W56's centre jobs with every geometry turned, each run once through the engine CLI, one after
the other on the GPU. Peaks read as W56's `race_5m.shape` reads them.

    python "W66 rotated Faydh/rotated_faydh.py" [ground|check|build|run|report] [names ...]
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MAIN = Path(r"D:\Mojtaba\Renardet\Wadi2D")
GROUND = HERE / "ground"
WORK = HERE / "runs"
DEM = MAIN / r"W11 validation round two\t2_faydh\terrain\faydh_0p5m.tif"
DOMAIN = MAIN / r"W11 validation round two\t2_faydh\domain_wadi_20m.geojson"
BANKS = MAIN / r"W26 suggested breaklines\suggested\faydh\suggested_breaklines.gpkg"
SQ_JOBS = MAIN / r"W49 local hydraulic radius face table\race_faydh_top_fix"
CE_JOBS = HERE.parent / r"W56 aligned mesh at 5 m on Faydh\runs"
ANGLE = 30.0
# Unrotated peaks on the same job files (m3/s): squares W49 race_faydh_top_fix, centres W56 (after W52's centroid fix).
UNROTATED = {"sq20": 1737.29, "sq10": 1779.07, "sq5": 1796.25, "ce20": 1859.58, "ce10": 1833.33}
# r_* are turned; u_* are the unrotated jobs rerun on this commit, to show the engine still gives the recorded numbers.
NAMES = ("r_sq20", "r_ce20", "r_sq10", "r_ce10", "u_sq20", "u_ce20", "r_sq5")


def centre() -> tuple[float, float]:
    from shapely.geometry import shape
    g = shape(json.loads(DOMAIN.read_text(encoding="utf-8"))["features"][0]["geometry"])
    return g.centroid.x, g.centroid.y


def turn_xy(x, y, c, angle=ANGLE):
    a = math.radians(angle)
    dx, dy = np.asarray(x, float) - c[0], np.asarray(y, float) - c[1]
    return c[0] + dx * math.cos(a) - dy * math.sin(a), c[1] + dx * math.sin(a) + dy * math.cos(a)


def turn_coords(coords, c):
    """Turn nested coordinate lists (any depth), keeping a z if present."""
    if isinstance(coords[0], (int, float)):
        x, y = turn_xy(coords[0], coords[1], c)
        return [float(x), float(y), *coords[2:]]
    return [turn_coords(p, c) for p in coords]


def ground() -> None:
    import fiona
    import rasterio
    from affine import Affine
    from rasterio.warp import Resampling, reproject
    from shapely.geometry import shape

    GROUND.mkdir(parents=True, exist_ok=True)
    c = centre()
    # domain
    dom = json.loads(DOMAIN.read_text(encoding="utf-8"))
    for f in dom["features"]:
        f["geometry"]["coordinates"] = turn_coords(f["geometry"]["coordinates"], c)
    (GROUND / "domain_rot30.geojson").write_text(json.dumps(dom), encoding="utf-8")
    # breaklines file, both layers
    out = GROUND / "suggested_breaklines_rot30.gpkg"
    if out.exists():
        out.unlink()
    for layer in fiona.listlayers(BANKS):
        with fiona.open(BANKS, layer=layer) as src:
            meta = src.meta
            with fiona.open(out, "w", layer=layer, **meta) as dst:
                for feat in src:
                    g = feat["geometry"]
                    geom = {"type": g["type"], "coordinates": turn_coords(g["coordinates"], c)}
                    dst.write(fiona.Feature(geometry=fiona.Geometry.from_dict(geom), properties=dict(feat["properties"])))
    # DEM: the turn in the source transform, GDAL resamples to a north-up 0.5 m grid over the turned domain + 300 m
    poly = shape(dom["features"][0]["geometry"])
    x0, y0, x1, y1 = poly.bounds
    with rasterio.open(DEM) as src:
        res = src.transform.a
        x0, y0 = math.floor((x0 - 300) / res) * res, math.floor((y0 - 300) / res) * res
        x1, y1 = math.ceil((x1 + 300) / res) * res, math.ceil((y1 + 300) / res) * res
        w, h = int(round((x1 - x0) / res)), int(round((y1 - y0) / res))
        dst_t = Affine(res, 0, x0, 0, -res, y1)
        src_t = Affine.rotation(ANGLE, pivot=c) * src.transform
        data = src.read(1)
        nodata = src.nodata
        prof = src.profile.copy()
    out_arr = np.full((h, w), nodata, dtype=np.float32)
    t0 = time.perf_counter()
    reproject(data, out_arr, src_transform=src_t, src_crs=prof["crs"], src_nodata=nodata, dst_transform=dst_t,
              dst_crs=prof["crs"], dst_nodata=nodata, resampling=Resampling.bilinear, num_threads=16,
              warp_mem_limit=8192)
    print(f"DEM turned in {time.perf_counter() - t0:.0f} s, {w} x {h}", flush=True)
    prof.update(width=w, height=h, transform=dst_t, tiled=True, blockxsize=512, blockysize=512, compress="deflate",
                predictor=3, num_threads="all_cpus", BIGTIFF="YES")
    with rasterio.open(GROUND / "faydh_0p5m_rot30.tif", "w", **prof) as dst:
        dst.write(out_arr, 1)
    print("ground written to", GROUND, "centre", c, flush=True)


def check() -> dict:
    """Areas, lengths and ground under the turned geometry against the original."""
    import rasterio
    from shapely.geometry import shape

    c = centre()
    a0 = shape(json.loads(DOMAIN.read_text(encoding="utf-8"))["features"][0]["geometry"])
    a1 = shape(json.loads((GROUND / "domain_rot30.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"])
    job = json.loads((CE_JOBS / "ce20.json").read_text(encoding="utf-8"))
    axis = np.array(job["outputs"]["lines"][0]["coordinates"])
    rng = np.random.default_rng(66)
    x0, y0, x1, y1 = a0.bounds
    from shapely import contains_xy
    px = rng.uniform(x0, x1, 400000)
    py = rng.uniform(y0, y1, 400000)
    keep = contains_xy(a0, px, py)
    px, py = px[keep][:100000], py[keep][:100000]
    qx, qy = turn_xy(px, py, c)
    # dense points along the axis
    seg = [np.linspace(axis[i], axis[i + 1], 400) for i in range(len(axis) - 1)]
    ax = np.concatenate(seg)
    bx, by = turn_xy(ax[:, 0], ax[:, 1], c)
    with rasterio.open(DEM) as s0, rasterio.open(GROUND / "faydh_0p5m_rot30.tif") as s1:
        z0 = np.array([v[0] for v in s0.sample(zip(px, py))])
        z1 = np.array([v[0] for v in s1.sample(zip(qx, qy))])
        za0 = np.array([v[0] for v in s0.sample(zip(ax[:, 0], ax[:, 1]))])
        za1 = np.array([v[0] for v in s1.sample(zip(bx, by))])
        nod = s0.nodata
    ok = (z0 < 1e30) & (z1 < 1e30)
    d = z1[ok] - z0[ok]
    out = {
        "centre": c,
        "domain_km2": [a0.area / 1e6, a1.area / 1e6],
        "axis_length_m": [float(np.sum(np.hypot(*np.diff(axis, axis=0).T))),
                          float(np.sum(np.hypot(*np.diff(np.column_stack(turn_xy(axis[:, 0], axis[:, 1], c)), axis=0).T)))],
        "ground_points": int(ok.sum()), "nodata_pairs": int((~ok).sum()),
        "ground_diff_m": {"mean": float(d.mean()), "median_abs": float(np.median(np.abs(d))),
                          "p99_abs": float(np.quantile(np.abs(d), 0.99))},
        "axis_min_ground_m": [float(za0.min()), float(za1.min())],
        "axis_mean_ground_m": [float(za0.mean()), float(za1.mean())],
    }
    (HERE / "rotation_check.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return out


def build(names: list[str]) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    c = centre()
    for name in names:
        rot, base = name.startswith("r_"), name[2:]
        src = (SQ_JOBS if base.startswith("sq") else CE_JOBS) / f"{base}.json"
        job = json.loads(src.read_text(encoding="utf-8"))
        job["grid"]["cache_dir"] = str(WORK / "cache")
        job.setdefault("tables", {})["face_conveyance"] = "local_radius"
        if rot:
            job["grid"]["domain"] = str(GROUND / "domain_rot30.geojson")
            job["terrain"]["dem"] = str(GROUND / "faydh_0p5m_rot30.tif")
            for b in job["boundaries"]:
                b["coordinates"] = turn_coords(b["coordinates"], c)
            for line in job["outputs"]["lines"]:
                line["coordinates"] = turn_coords(line["coordinates"], c)
            if job.get("strips", {}).get("enabled"):
                job["strips"]["banks"] = str(GROUND / "suggested_breaklines_rot30.gpkg")
        (WORK / f"{name}.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    print("jobs written:", ", ".join(names), flush=True)


def run(name: str) -> None:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    t0 = time.perf_counter()
    done = subprocess.run([sys.executable, "-m", "wadi2d.engine.cli", "run", str(WORK / f"{name}.json"), "--out",
                           str(WORK / name)], capture_output=True, text=True, cwd=str(ROOT), env=env)
    wall = time.perf_counter() - t0
    (WORK / f"{name}.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    (WORK / f"{name}.wall").write_text(f"{wall:.1f}\n{done.returncode}\n", encoding="utf-8")
    print(f"{name}: exit {done.returncode} in {wall:.0f} s", flush=True)


def shape_of(folder: Path, line: str = "axis") -> dict:
    rows = (folder / "series" / f"line_{line}.csv").read_text(encoding="utf-8").splitlines()[1:]
    a = np.array([[float(v) for v in r.split(",")[:2]] for r in rows])
    t, q = a[:, 0], np.abs(a[:, 1])
    k = int(q.argmax())
    return {"peak": float(q[k]), "at_h": float(t[k] / 3600), "vol_Mm3": float(q.sum() * float(np.median(np.diff(t))) / 1e6)}


def report(names: list[str]) -> dict:
    out = {}
    for name in names:
        if not (WORK / name / "series" / "line_axis.csv").is_file():
            print(f"{name}: no series")
            continue
        r = shape_of(WORK / name)
        prog = (WORK / name / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        done = [json.loads(s) for s in prog if '"done"' in s[:14]]
        if done:
            r["tables_s"], r["loop_s"] = done[-1].get("tables_s"), done[-1].get("loop_s")
        r["unrotated"] = UNROTATED[name[2:]]
        r["vs_unrotated_pct"] = 100 * (r["peak"] / r["unrotated"] - 1)
        out[name] = r
        print(f"{name:7s} {r['peak']:9.1f} unrotated {r['unrotated']:9.1f} {r['vs_unrotated_pct']:+6.2f} %  "
              f"vol {r['vol_Mm3']:.3f} Mm3  at {r['at_h']:.2f} h  loop {r.get('loop_s') or 0:.0f} s")
    (HERE / "rotated_peaks.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def angles() -> dict:
    """Length-weighted angle of the Suggest thalwegs to the nearest lattice axis, before and after the turn."""
    import fiona

    rows = []
    with fiona.open(BANKS, layer="thalwegs") as src:
        for feat in src:
            area = feat["properties"]["area_km2"]
            for part in feat["geometry"]["coordinates"]:
                a = np.array(part)[:, :2]
                length = float(np.sum(np.hypot(*np.diff(a, axis=0).T)))
                step = max(1, len(a) // max(1, int(length / 100)))  # about 100 m chords
                for dx, dy in np.diff(a[::step], axis=0):
                    rows.append((area, math.hypot(dx, dy), math.degrees(math.atan2(dy, dx))))
    r = np.array(rows)
    out = {}
    for lo in (0, 30):
        k = r[:, 0] >= lo
        for rot in (0, ANGLE):
            m = np.mod(r[k, 2] + rot, 90)
            dev, w = np.minimum(m, 90 - m), r[k, 1]
            out[f"area>={lo}km2_rot{int(rot)}"] = {"length_km": float(w.sum() / 1e3),
                                                  "mean_deg_off_lattice": float(np.average(dev, weights=w)),
                                                  "share_within_10deg": float(w[dev < 10].sum() / w.sum())}
    (HERE / "thalweg_angles.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "report"
    names = [a for a in sys.argv[2:] if a in NAMES] or list(NAMES)
    if what == "ground":
        ground()
    elif what == "check":
        check()
    elif what == "build":
        build(names)
    elif what == "run":
        for name in names:
            run(name)
    elif what == "report":
        report(names)
    elif what == "angles":
        angles()
