"""Grid convergence on the Bidah wadi: S13 and the fan below it, natural ground, the same storm, 40-20-10-5 m, and
20 m with pixel_stride 1, 2, 4. Rain on every cell, per-cell CN, uniform Manning 0.05, 30 h."""
import json
import sys

import numpy as np
import rasterio

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import ACC, AXES, CACHE, CN, DEM, OUT, HMS, polygons, ring_of, storm, write_job
from dams import BIDAH, write_domain

import shapely

polys = polygons()
ring = ring_of(["S13"], polys)
dom = write_domain(BIDAH)

# points on the main stem, by accumulation inside S13, then one on the fan below the dam
pts = []
with rasterio.open(ACC) as s:
    poly = polys["S13"]
    w = rasterio.windows.from_bounds(*poly.bounds, s.transform).round_offsets().round_lengths()
    a = s.read(1, window=w, masked=True).filled(0.0) * 25e-6
    t = s.window_transform(w)
    inside = rasterio.features.geometry_mask([poly.buffer(-60.0)], a.shape, t, invert=True)
    for target in (5.0, 10.0, 15.0, 19.0):
        m = np.where(inside & (a >= target), a, np.inf)
        j, i = np.unravel_index(int(np.argmin(m)), a.shape)
        x, y = t * (i + 0.5, j + 0.5)
        pts.append({"name": f"wadi_{target:g}km2", "x": float(x), "y": float(y)})
    # fan: largest accumulation at x = 439600
    box = shapely.box(439500.0, 2726000.0, 439700.0, 2728500.0)
    w2 = rasterio.windows.from_bounds(*box.bounds, s.transform).round_offsets().round_lengths()
    b = s.read(1, window=w2, masked=True).filled(0.0)
    t2 = s.window_transform(w2)
    j, i = np.unravel_index(int(np.argmax(b)), b.shape)
    x, y = t2 * (i + 0.5, j + 0.5)
    pts.append({"name": "fan_below_dam", "x": float(x), "y": float(y)})
print(pts)
lines = [{"name": "Bidah axis", "coordinates": AXES["Bidah 03"]}, {"name": "Bidah ring", "coordinates": ring}]
names = []
for dx, stride in ((40.0, 1), (20.0, 1), (10.0, 1), (5.0, 1), (20.0, 2), (20.0, 4)):
    name = f"conv_dx{dx:g}_s{stride}"
    j = {
        "project": {"name": name, "description": "Bidah wadi grid convergence"},
        "grid": {"dx": dx, "domain": str(dom), "cache_dir": str(CACHE)},
        "terrain": {"dem": str(DEM), "pixel_stride": stride, "manning": 0.05, "cn_raster": str(CN)},
        "storm": storm(20.971),
        "hydrology": {"curve_number": 88.0},
        "boundaries": BIDAH.boundaries,
        "outputs": {"map_every_s": 0.0, "series_every_s": 60.0, "live_every_s": 0.0, "lines": lines, "points": pts},
        "run": {"duration_s": 108000.0, "backend": "gpu", "source_every_s": 30.0, "checkpoint_every_s": 0.0},
    }
    write_job(j, name)
    names.append(name)
print(" ".join(names))
