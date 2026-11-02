"""Flat against sloped water surface at the 5 m pixel: class areas, ground newly wetted, and how high above the cell's own
water level that ground stands, which is the dry-freeboard check. Lifts the sloped maps to 20 m. Writes sloped_compare.json."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio

HERE = Path(__file__).resolve().parent
T = HERE / "terrain"
KM2 = 25e-6
F = 4


def read(name):
    with rasterio.open(T / name) as s:
        return s.read(1), s.profile


flat, prof = read("pixel_hazard_5m.tif")
sloped, _ = read("pixel_hazard_sloped_5m.tif")
out = {"flat_km2": {f"H{k}": float((flat == k).sum() * KM2) for k in range(1, 7)}, "sloped_km2": {f"H{k}": float((sloped == k).sum() * KM2) for k in range(1, 7)}}
print("flat  ", {k: round(v) for k, v in out["flat_km2"].items()})
print("sloped", {k: round(v) for k, v in out["sloped_km2"].items()})
added = (sloped > 0) & (flat == 0)
lost = (flat > 0) & (sloped == 0)
out["wet_only_when_sloped_km2"] = float(added.sum() * KM2)
out["wet_only_when_flat_km2"] = float(lost.sum() * KM2)
print("wet only sloped km2", round(out["wet_only_when_sloped_km2"], 1), "wet only flat km2", round(out["wet_only_when_flat_km2"], 1))
depth, _ = read("pixel_depth_sloped_5m.tif")
d = depth[added]
d = d[d > 0]
out["added_depth_pct"] = [float(v) for v in np.percentile(d, [50, 90, 99])]
print("depth on the newly wet ground, m, 50/90/99", np.round(out["added_depth_pct"], 2))
same = (flat > 0) & (sloped > 0)
out["same_class_share"] = float((flat[same] == sloped[same]).mean())
out["moved_up_share"] = float((sloped[same] > flat[same]).mean())
print("same class share", round(out["same_class_share"], 3), "moved up", round(out["moved_up_share"], 3))
(HERE / "sloped_compare.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
ny, nx = sloped.shape[0] // F, sloped.shape[1] // F
b = sloped[: ny * F, : nx * F].reshape(ny, F, nx, F).max(axis=(1, 3))
p = {"driver": "GTiff", "height": ny, "width": nx, "count": 1, "dtype": "uint8", "crs": prof["crs"], "transform": prof["transform"] * rasterio.Affine.scale(F, F), "nodata": 0, "compress": "deflate", "tiled": True, "BIGTIFF": "YES"}
with rasterio.open(T / "pixel_hazard_20m.tif", "w", **p) as o:
    o.write(b, 1)
c = depth[: ny * F, : nx * F].reshape(ny, F, nx, F).max(axis=(1, 3))
p.update(dtype="float32", nodata=-9999.0)
with rasterio.open(T / "pixel_depth_20m.tif", "w", **p) as o:
    o.write(c, 1)
