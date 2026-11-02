"""Wadi2D on his model's perimeter, one input changed at a time from a base that holds the W2 inputs.

Base: his perimeter, his Sea line as the only outlet, NSA5+COP30 blend, 30 m, n 0.05, project CN grid, FM_200yr at storm
area 300 km2 (209 mm), 30 h. Each variant changes one thing toward his Block2_FM_200Yr(F) model. usage: s07_jobs.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
G02 = Path(r"W:\2512-1 Liwa- Fizah Road\06-WORKING\03-Hydrology\07. HECRAS\Block02.p06\Block02.g02")
GGC5 = r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM_5.tif"

text = G02.read_text(encoding="latin-1").split("\n")
i = next(k for k, s in enumerate(text) if s.startswith("BC Line Name=Sea"))
j = next(k for k in range(i, len(text)) if text[k].startswith("BC Line Arc="))
n = int(text[j].split("=")[1])
vals: list[float] = []
k = j + 1
while len(vals) < 2 * n:
    s = text[k].rstrip("\r")
    vals += [float(s[a : a + 16]) for a in range(0, len(s), 16) if s[a : a + 16].strip()]
    k += 1
sea = np.array(vals).reshape(-1, 2)
print("Sea line", sea.shape, sea[0], sea[-1], "length km", np.hypot(*np.diff(sea, axis=0).T).sum() / 1e3)

per = json.loads((HERE / "his_perimeter.json").read_text(encoding="utf-8"))
gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "his perimeter"},
      "geometry": {"type": "Polygon", "coordinates": [per + [per[0]]]}}]}  # fmt: skip
(HERE / "domain_his.geojson").write_text(json.dumps(gj), encoding="utf-8")

base = json.loads((ROOT / "W2 full extent run" / "jobs" / "full_30m_200yr.json").read_text(encoding="utf-8"))
base["grid"]["domain"] = str(HERE / "domain_his.geojson")
base["grid"]["cache_dir"] = str(HERE / "cache")
base["boundaries"] = [{"kind": "normal", "slope": 0.0065, "coordinates": sea.tolist()}]
base["run"]["duration_s"] = 30 * 3600.0
base["run"]["checkpoint_every_s"] = 0.0
base["outputs"] = {"map_every_s": 3600.0, "series_every_s": 300.0, "live_every_s": 0.0, "lines": []}

V = {
    "t0_base": {},
    "t1_rain228": {"storm_area_km2": 105.0},
    "t2_n060": {"manning": 0.06},
    "t3_ggc": {"dem": GGC5},
    "t4_dx15": {"dx": 15.0},
    "t5_all": {"storm_area_km2": 105.0, "manning": 0.06, "dem": GGC5, "dx": 15.0},
}
(HERE / "jobs").mkdir(exist_ok=True)
for name, ch in V.items():
    job = json.loads(json.dumps(base))
    job["project"]["name"] = f"t4_{name}"
    if "storm_area_km2" in ch:
        job["storm"]["storm_area_km2"] = ch["storm_area_km2"]
    if "manning" in ch:
        job["terrain"]["manning"] = ch["manning"]
    if "dem" in ch:
        job["terrain"]["dem"] = ch["dem"]
    if "dx" in ch:
        job["grid"]["dx"] = ch["dx"]
    (HERE / "jobs" / f"{name}.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
print("written", list(V))
