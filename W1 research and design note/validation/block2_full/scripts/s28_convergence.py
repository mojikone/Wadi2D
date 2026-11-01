"""Grid convergence table: peak at the lines, levels at the points, flood extent on a common 2 m raster.

Extent: a DEM pixel at 2 m is flooded when the cell's max level stands 0.1 m or more over it, so every grid is judged on
the same pixels; the overlap F = (A and B) / (A or B) is against the 5 m run. Inside the S13 polygon and the fan box.
"""
import csv
import json
import sys

import numpy as np
import rasterio
import rasterio.features
from rasterio.enums import Resampling
from rasterio.transform import from_origin

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from analyze import done_event, line_stats
from common import DEM, OUT
from dams import BIDAH

names = ["conv_dx40_s1", "conv_dx20_s1", "conv_dx10_s1", "conv_dx5_s1", "conv_dx20_s2", "conv_dx20_s4"]
b = (437300.0, 2725700.0, 440300.0, 2728700.0)
with rasterio.open(DEM) as src:
    w = rasterio.windows.from_bounds(*b, src.transform).round_offsets().round_lengths()
    h, wd = int(w.height // 4), int(w.width // 4)
    w = rasterio.windows.Window(w.col_off, w.row_off, wd * 4, h * 4)
    z = src.read(1, window=w, out_shape=(h, wd), resampling=Resampling.nearest, masked=True).astype(np.float64).filled(np.nan)
    t0 = src.window_transform(w)
tr = from_origin(t0.c, t0.f, 2.0, 2.0)
ys = t0.f - (np.arange(h) + 0.5) * 2.0
xs = t0.c + (np.arange(wd) + 0.5) * 2.0
masks = {}
rows = {}
for n in names:
    run = OUT / "runs" / n
    if not (run / "series").exists():
        print(n, "missing")
        continue
    with rasterio.open(run / "maps" / "max_level.tif") as m:
        lv = m.read(1, masked=True).filled(np.nan)
        inv = ~m.transform
        c = np.floor(inv.a * xs + inv.c).astype(int)
        r = np.floor(inv.e * ys + inv.f).astype(int)
        ok_c = (c >= 0) & (c < m.width)
        ok_r = (r >= 0) & (r < m.height)
    cell = np.full((h, wd), np.nan)
    cell[np.ix_(ok_r, ok_c)] = lv[np.ix_(r[ok_r], c[ok_c])]
    mask = np.nan_to_num(cell - z, nan=-1.0) >= 0.1
    masks[n] = mask
    e = done_event(run)
    d, s = e["done"], e["start"]
    pts = {}
    for path in sorted((run / "series").glob("point_*.csv")):
        data = list(csv.reader(path.open()))
        head = data[0]
        a = np.array(data[1:], dtype=np.float64)
        pts[path.stem[6:]] = {"level": float(a[:, head.index("level_m")].max()), "mean_depth": float(a[:, head.index("mean_depth_m")].max())}
    rows[n] = {"cells": s["cells"], "tables_s": s["tables_s"], "loop_s": d["loop_s"], "steps": d["steps"], "wet": d["wet_area_km2"],
               "axis": line_stats(run, "Bidah axis"), "ring": line_stats(run, "Bidah ring"), "points": pts,
               "extent_km2": float(mask.sum() * 4e-6), "err": d["balance"]["relative_error"]}
ref = masks.get("conv_dx5_s1")
for n, r in rows.items():
    if ref is not None:
        r["F_vs_5m"] = float((masks[n] & ref).sum() / max((masks[n] | ref).sum(), 1))
    p = " ".join(f"{k.split('_')[-1]}:{v['level']:.2f}" for k, v in r["points"].items())
    print(f"{n:14s} cells {r['cells']:8d} tab {r['tables_s']:6.1f} loop {r['loop_s']:7.1f} steps {r['steps']:8d} | axis {r['axis']['peak']:6.1f} @{r['axis']['t_h']:5.2f} ring {r['ring']['peak']:6.1f} vol {r['ring']['vol_m3']/1e6:5.3f} | extent {r['extent_km2']:6.3f} F {r.get('F_vs_5m', 0):.3f} wet {r['wet']:.2f} | {p} err {r['err']:.1e}")
(OUT / "convergence.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
