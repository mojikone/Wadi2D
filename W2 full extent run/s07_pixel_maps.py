"""Lift the 5 m pixel maps to 20 m by maximum, so a thin channel survives at map scale. Writes terrain/pixel_*_20m.tif."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio

HERE = Path(__file__).resolve().parent
T = HERE / "terrain"
F = 4


def lift(name: str, out: str, dtype: str, nodata: float) -> None:
    with rasterio.open(T / name) as s:
        a = s.read(1)
        tr, crs = s.transform, s.crs
    ny, nx = a.shape[0] // F, a.shape[1] // F
    b = a[: ny * F, : nx * F].reshape(ny, F, nx, F).max(axis=(1, 3))
    prof = {"driver": "GTiff", "height": ny, "width": nx, "count": 1, "dtype": dtype, "crs": crs, "transform": tr * rasterio.Affine.scale(F, F), "nodata": nodata, "compress": "deflate", "tiled": True, "BIGTIFF": "YES"}
    with rasterio.open(T / out, "w", **prof) as o:
        o.write(b, 1)
    print(out, b.shape)


lift("pixel_hazard_5m.tif", "pixel_hazard_20m.tif", "uint8", 0)
lift("pixel_depth_5m.tif", "pixel_depth_20m.tif", "float32", -9999.0)
print(json.dumps(json.loads((HERE / "pixel_hazard_stats.json").read_text())["class_km2"]))
