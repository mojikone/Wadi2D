"""Real Block 2 ground, sensible levels this time: CLI preview, then a short solver run with water in the channel."""
import csv
import json
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np
import rasterio

HERE = Path(__file__).parent / "prove3"
HERE.mkdir(exist_ok=True)
DEM = r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM_5.tif"
PY = sys.executable
A = np.array([435800.0, 2727300.0])
B = np.array([438600.0, 2726700.0])
L = float(np.hypot(*(B - A)))
st = np.arange(0.0, L + 1.0, 100.0)


def ground(xs, ys):
    with rasterio.open(DEM) as src:
        return np.array([v[0] for v in src.sample(zip(xs, ys))], dtype=float)


g = ground(A[0] + (B - A)[0] * st / L, A[1] + (B - A)[1] * st / L)
fit = np.polyfit(st, g, 1)
bed = np.polyval(fit, st) - 2.0
with (HERE / "sections.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["station", "bed_z", "width", "left_top_z", "right_top_z", "left_slope", "right_slope", "left_crest_width", "right_crest_width", "left_outer_slope", "right_outer_slope"])
    for s, b in zip(st[::3], bed[::3]):
        w.writerow([s, round(b, 3), 30.0 if s < 1500 else 40.0, round(b + 3.0, 3), round(b + 2.5, 3), 2.0, 2.0, 4.0, 4.0, 2.5, 2.5])
n = np.array([[436200.0, 2727800.0], [436900.0, 2727650.0], [437500.0, 2727700.0]])
gn = ground(n[:, 0], n[:, 1])
sd = np.array([[436000.0, 2726300.0], [437000.0, 2726200.0], [438000.0, 2726250.0]])
gs = ground(sd[:, 0], sd[:, 1])
print("north ground", gn, "south ground", gs)
slope = float((gs[0] - gs[-1]) / 2006.0)
extent = [435500.0, 2726000.0, 438900.0, 2728000.0]
job = {
    "project": {"name": "prove3"},
    "grid": {"dx": 10.0, "extent": extent, "cache_dir": str(HERE / "cache")},
    "terrain": {
        "dem": DEM, "manning": 0.04,
        "objects": [
            {"kind": "channel_dyke", "name": "Mixed channel", "coordinates": [A.tolist(), B.tolist()],
             "section": {"table": str(HERE / "sections.csv")},
             "openings": [{"start": 900.0, "end": 1000.0, "side": "left"}],
             "lining_n": 0.02, "start_end": "taper", "end_end": "taper", "taper_length": 100.0},
            {"kind": "embankment", "name": "North dyke", "coordinates": n.tolist(), "z": (gn + 4.0).tolist(),
             "section": {"width": 5.0, "left_slope": 2.0, "right_slope": 3.0}, "openings": [{"start": 400.0, "end": 460.0}]},
            {"kind": "channel", "name": "South drain", "coordinates": sd.tolist(),
             "section": {"bed_start_z": float(gs[0] - 2.0), "bed_slope": slope, "width": 36.0, "left_slope": 1.5, "right_slope": 1.5},
             "start_end": "taper", "end_end": "taper"},
        ],
    },
    "hydrology": {"curve_number": 85.0},
    "storm": {"kind": "uniform", "depth_mm": 80.0, "duration_min": 60.0},
    "boundaries": [{"kind": "normal", "coordinates": [[438895.0, 2726000.0], [438895.0, 2728000.0]], "slope": 0.012}],
    "outputs": {"map_every_s": 0.0, "live_every_s": 0.0, "terrain_map": True,
                "lines": [{"name": "channel", "coordinates": [[437100.0, 2726900.0], [437270.0, 2727100.0]]}]},
    "run": {"duration_s": 5400.0, "backend": sys.argv[1] if len(sys.argv) > 1 else "cpu"},
}
(HERE / "job.json").write_text(json.dumps(job, indent=1))
r = subprocess.run([PY, "-m", "wadi2d.engine.cli", "terrain", str(HERE / "job.json"), "--out", str(HERE / "terrain")], capture_output=True, text=True)
print("terrain exit", r.returncode, r.stderr[-800:])
said = json.loads(r.stdout)
for note in said["notes"]:
    print(" NOTE", note)
print(json.dumps(said["volumes"], indent=0))
data = json.loads((HERE / "terrain" / "preview.json").read_text())
for d in data:
    print(d["name"], round(d["length"]), {k: {s: d[k].count(s) for s in set(d[k])} for k in ("left_state", "right_state")})
d = data[0]
print("left flips", sum(a != b for a, b in zip(d["left_state"], d["left_state"][1:])), "right flips", sum(a != b for a, b in zip(d["right_state"], d["right_state"][1:])))
out = HERE / "run"
import shutil
shutil.rmtree(out, ignore_errors=True)
r = subprocess.run([PY, "-m", "wadi2d.engine.cli", "run", str(HERE / "job.json"), "--out", str(out)], capture_output=True, text=True)
print("run exit", r.returncode, r.stderr[-400:])
ev = [json.loads(s) for s in (out / "progress.jsonl").read_text().splitlines()]
for e in ev:
    if e["ev"] in ("start", "done", "terrain", "error"):
        print({k: v for k, v in e.items() if k in ("ev", "backend", "cells", "status", "code", "message", "balance", "volumes")})
print("warns", sum(e["ev"] == "warn" for e in ev))
print(sorted(p.name for p in (out / "terrain").glob("*")))
with h5py.File(out / "results.h5", "r") as f:
    print("peak Q at the channel", float(np.abs(f["series/lines/channel/discharge_m3s"][()]).max()))
    d = f["maxima"]["depth"][()]
    print("max depth", float(d.max()))
