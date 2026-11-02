"""Pixel depth and AIDR hazard of the hybrid run, by the same code as the full-extent run, and lifted to 10 m for the map."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import rasterio

HERE = Path(__file__).resolve().parent
RUN = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("hz", HERE.parent.parent / "W2 full extent run" / "s06_pixel_hazard.py")
hz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hz)
hz.HERE = HERE
hz.RUN = RUN
hz.MAPS = RUN / "maps"
hz.DEM = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM_5.tif")
hz.SCALE = 4  # 20 m cells on 5 m pixels
(HERE / "terrain").mkdir(exist_ok=True)
sys.argv = [sys.argv[0]]  # main takes a frame limit, not the run folder
hz.main()

T = HERE / "terrain"
F = 2
for name, out, dtype, nodata in (("pixel_hazard_sloped_5m.tif", "hazard_10m.tif", "uint8", 0), ("pixel_depth_sloped_5m.tif", "depth_10m.tif", "float32", -9999.0)):
    with rasterio.open(T / name) as s:
        a = s.read(1)
        prof = {"driver": "GTiff", "count": 1, "crs": s.crs, "transform": s.transform * rasterio.Affine.scale(F, F), "nodata": nodata, "dtype": dtype, "compress": "deflate", "tiled": True, "BIGTIFF": "YES"}
    ny, nx = a.shape[0] // F, a.shape[1] // F
    b = a[: ny * F, : nx * F].reshape(ny, F, nx, F).max(axis=(1, 3))
    with rasterio.open(T / out, "w", height=ny, width=nx, **prof) as o:
        o.write(b, 1)
    print(out, b.shape, np.count_nonzero(b > 0))
