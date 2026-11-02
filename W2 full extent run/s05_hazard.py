"""AIDR H1 to H6 from the run's three maxima, with the limits and the rule of the Majlas dam-break script (ras_results.py).

A cell takes the highest class any threshold gives, so the class of the maxima is the worst class over the flood: each
of the three tests is monotonic, and hazard.tif holds depth x speed taken at one moment, updated every 4 steps. Depth is
the level above the cell's lowest point, as in that hazard map. Cells of mean depth under DEPTH_MIN stay out, so a film on
a steep cell is not painted. Writes terrain/hazard_class.tif and hazard_stats.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

HERE = Path(__file__).resolve().parent
MAPS = HERE / "runs" / "full_30m_200yr" / "maps"
LIMITS = [(0.3, 0.3, 2.0), (0.6, 0.5, 2.0), (0.6, 1.2, 2.0), (1.0, 2.0, 2.0), (4.0, 4.0, 4.0)]  # D x V, depth, speed: H1 to H5
DEPTH_MIN = 0.05  # m
MIN_PATCH_HA = 0.0


def read(name):
    with rasterio.open(MAPS / f"{name}.tif") as s:
        return s.read(1, masked=True).filled(0.0).astype("float32"), s.profile


d, profile = read("max_depth")
v, _ = read("max_speed")
dv, _ = read("hazard")
mean, _ = read("max_mean_depth")
cls = np.ones(d.shape, np.uint8)
for i, (dv_lim, d_lim, v_lim) in enumerate(LIMITS, start=1):
    above = (dv > dv_lim) | (d > d_lim) | (v > v_lim)
    cls = np.where(above & (cls == i), i + 1, cls).astype(np.uint8)
cls[mean <= DEPTH_MIN] = 0
# the same class test with cell-mean depth, to size how far the low-point depth lifts the classes
mean_cls = np.ones(d.shape, np.uint8)
dv_mean = dv * np.divide(mean, d, out=np.zeros_like(mean), where=d > 0)
for i, (dv_lim, d_lim, v_lim) in enumerate(LIMITS, start=1):
    above = (dv_mean > dv_lim) | (mean > d_lim) | (v > v_lim)
    mean_cls = np.where(above & (mean_cls == i), i + 1, mean_cls).astype(np.uint8)
mean_cls[mean <= DEPTH_MIN] = 0
km2 = abs(profile["transform"].a * profile["transform"].e) * 1e-6
stats = {f"H{k}": float((cls == k).sum() * km2) for k in range(1, 7)}
stats_mean = {f"H{k}": float((mean_cls == k).sum() * km2) for k in range(1, 7)}
print("low-point depth, km2 ", {k: round(a, 1) for k, a in stats.items()})
print("cell-mean depth, km2 ", {k: round(a, 1) for k, a in stats_mean.items()})
print("max: depth", d.max(), "speed", v.max(), "dv", dv.max())
high = ndimage.binary_opening(cls >= 5, iterations=1)
lab, n = ndimage.label(high, structure=np.ones((3, 3)))
print("H5 and H6 patches after opening", n)
prof = dict(profile, dtype="uint8", nodata=0, compress="deflate", predictor=1)
with rasterio.open(HERE / "terrain" / "hazard_class.tif", "w", **prof) as o:
    o.write(cls, 1)
with rasterio.open(HERE / "terrain" / "depth_30m.tif", "w", **dict(profile, dtype="float32", nodata=-9999.0, compress="deflate")) as o:
    o.write(np.where(mean > 0, mean, -9999.0).astype("float32"), 1)
(HERE / "hazard_stats.json").write_text(json.dumps({"low_point_depth_km2": stats, "cell_mean_depth_km2": stats_mean, "limits": LIMITS, "depth_min_m": DEPTH_MIN}, indent=1), encoding="utf-8")
