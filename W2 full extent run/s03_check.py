"""Checks on the full-extent run: balance, warnings, dam peaks, wall pockets, extent against the 200-yr layer, map input.
Writes s03_check.json and terrain/depth_90m.tif, the cell-mean maximum depth lifted to 90 m by maximum for the overview map."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features
from rasterio.enums import Resampling
from rasterio.warp import reproject
from scipy import ndimage

HERE = Path(__file__).resolve().parent
RUN = HERE / "runs" / "full_30m_200yr"
HIS = r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Raster\Block2_Depth_200Year.tif"
OPEN_CELLS = 3  # closed-edge test: cells this close to an outlet line do not count

rows = [json.loads(s) for s in (RUN / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
done = next(r for r in rows if r.get("ev") == "done")
warns = [r.get("message") for r in rows if r.get("ev") == "warn"]
out: dict = {"done": {k: done.get(k) for k in ("status", "code", "steps", "loop_s", "tables_s", "wet_area_km2", "dt_min")}, "balance": done["balance"], "warnings": warns}
b = done["balance"]
print("status", done["status"], "wall min", round(done["loop_s"] / 60, 1), "wet km2", done["wet_area_km2"], "dt_min", done["dt_min"])
print("rain Mm3", round(b["rain_m3"] / 1e6, 1), "out", round(b["outflow_m3"] / 1e6, 1), "stored", round(b["storage_end_m3"] / 1e6, 1), "rel err", b["relative_error"])
print("warnings", warns)

peaks = {}
for f in sorted((RUN / "series").glob("line_*.csv")):
    with f.open() as h:
        data = np.array([[float(v) for v in r] for r in list(csv.reader(h))[1:]])
    k = int(np.argmax(data[:, 1]))
    peaks[f.stem[5:]] = {"peak": float(data[k, 1]), "t_h": float(data[k, 0] / 3600), "volume_Mm3": float(np.trapezoid(data[:, 1], data[:, 0]) / 1e6)}
    print(f"  {f.stem[5:]:12s} peak {data[k, 1]:9.1f} m3/s at {data[k, 0] / 3600:5.2f} h, volume {peaks[f.stem[5:]]['volume_Mm3']:7.2f} Mm3")
out["peaks"] = peaks

with rasterio.open(RUN / "maps" / "max_mean_depth.tif") as d:
    a = d.read(1, masked=True)
    tr, crs = d.transform, d.crs
    print("raster", d.width, d.height, d.bounds)
    depth = a.filled(0.0)
    cells = ~np.ma.getmaskarray(a)
km2 = abs(tr.a * tr.e) * 1e-6
areas = {t: float((depth >= t).sum() * km2) for t in (0.1, 0.3, 0.5, 1.0, 3.0)}
print("area by mean depth, km2", {k: round(v, 1) for k, v in areas.items()})
out["area_km2"] = areas

# water stacked against closed walls
lines = json.loads((HERE / "boundaries.geojson").read_text(encoding="utf-8"))["features"]
open_mask = rasterio.features.rasterize([f["geometry"] for f in lines], out_shape=depth.shape, transform=tr, fill=0, default_value=1, dtype="uint8", all_touched=True).astype(bool)
open_mask = ndimage.binary_dilation(open_mask, iterations=OPEN_CELLS)
edge = cells & ~ndimage.binary_erosion(cells, iterations=2) & ~open_mask
for t in (1.0, 3.0, 10.0):
    print(f"closed-edge cells over {t} m: {(edge & (depth >= t)).sum()} of {edge.sum()}")
hit = edge & (depth >= 3.0)
lab, n = ndimage.label(hit, structure=np.ones((3, 3)))
worst = []
for k in np.argsort(ndimage.sum(hit, lab, range(1, n + 1)))[::-1][:6] + 1:
    r, c = np.where(lab == k)
    x, y = rasterio.transform.xy(tr, r, c)
    worst.append({"cells": int(r.size), "x": [min(x), max(x)], "y": [min(y), max(y)], "max_m": float(depth[r, c].max())})
print("largest wall pockets", json.dumps(worst)[:600])
out["wall_pockets"] = worst
out["wall_cells_over_3m"] = int(hit.sum())

# extent against his 200-yr layer, on his layer's own frame, 30 m
with rasterio.open(HIS) as h:
    his = np.full(depth.shape, np.nan, "float32")
    reproject(rasterio.band(h, 1), his, dst_transform=tr, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.average)
his = np.where(his > 50.0, np.nan, his)
ok = cells & np.isfinite(his)
print(f"his layer on this grid: {np.isfinite(his).sum() * km2:,.1f} km2, inside the model {ok.sum() * km2:,.1f} km2")
frame = ndimage.binary_dilation(np.isfinite(his), iterations=200)
for t in (0.1, 0.3, 0.5):
    h_w, m_w = np.nan_to_num(his) >= t, depth >= t
    both = (h_w & m_w & frame).sum()
    union = ((h_w | m_w) & frame).sum()
    print(f"depth >= {t}: his {h_w.sum() * km2:,.0f}, Wadi2D {(m_w & frame).sum() * km2:,.0f}, both {both * km2:,.0f} km2, F {both / union:.3f}, his also wet in Wadi2D {both / h_w.sum():.3f}")
    out[f"extent_{t}"] = {"his": float(h_w.sum() * km2), "wadi": float((m_w & frame).sum() * km2), "both": float(both * km2), "F": float(both / union)}

# 90 m overview raster, maximum of the cell means
f = 3
ny, nx = depth.shape[0] // f, depth.shape[1] // f
small = depth[: ny * f, : nx * f].reshape(ny, f, nx, f).max(axis=(1, 3)).astype("float32")
inside = cells[: ny * f, : nx * f].reshape(ny, f, nx, f).any(axis=(1, 3))
small[~inside | (small <= 0)] = -9999.0
prof = {"driver": "GTiff", "height": ny, "width": nx, "count": 1, "dtype": "float32", "crs": crs, "transform": tr * rasterio.Affine.scale(f, f), "nodata": -9999.0, "compress": "deflate"}
with rasterio.open(HERE / "terrain" / "depth_90m.tif", "w", **prof) as o:
    o.write(small, 1)
(HERE / "s03_check.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
