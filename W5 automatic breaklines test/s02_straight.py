"""Second pass: the same detection, keeping only long straight objects. Disc radius 60 m. Roads are long and straight;
fan bars and gully ridges are not. Elongation is length over width of the object's fitted ellipse."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyogrio
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from scipy import ndimage
from skimage.measure import label, regionprops
from skimage.morphology import disk, skeletonize

from s01_highway import CORRIDOR_M, DEM, FRAME, PIX, REACH_M, ROAD

HERE = Path(__file__).resolve().parent
RADIUS_M = 60.0
HEIGHTS_M = (0.3, 0.5, 0.75)
LENGTHS_M = (300.0, 500.0, 1000.0)
ELONGATION = (5.0, 10.0)

road = pyogrio.read_dataframe(ROAD).to_crs(32640).geometry.union_all().intersection(FRAME)
zone = road.buffer(CORRIDOR_M)
with rasterio.open(DEM) as s:
    w = from_bounds(*zone.bounds, s.transform).round_offsets().round_lengths()
    z = s.read(1, window=w).astype("float32")
    tr = s.window_transform(w)
inside = ~geometry_mask([zone.__geo_interface__], z.shape, tr)
near_road = ~geometry_mask([road.buffer(REACH_M).__geo_interface__], z.shape, tr)
samples = [road.interpolate(d) for d in np.arange(0.0, road.length, 20.0)]
rc = np.array([rasterio.transform.rowcol(tr, p.x, p.y) for p in samples])
top = z - ndimage.grey_opening(z, footprint=disk(int(RADIUS_M / PIX)))
out = []
for height in HEIGHTS_M:
    lab = label((top >= height) & inside, connectivity=2)
    props = regionprops(lab)
    major = np.zeros(lab.max() + 1)
    minor = np.ones(lab.max() + 1)
    for p in props:
        major[p.label] = p.axis_major_length * PIX
        minor[p.label] = max(p.axis_minor_length * PIX, PIX)
    for length in LENGTHS_M:
        for ratio in ELONGATION:
            keep = (major >= length) & (major / minor >= ratio)
            keep[0] = False
            lines = skeletonize(keep[lab])
            d = ndimage.distance_transform_edt(~lines) * PIX
            hit = d[rc[:, 0], rc[:, 1]] <= REACH_M
            row = {"height_m": height, "min_length_m": length, "elongation": ratio, "recall": round(float(hit.mean()), 3),
                   "km_on_highway": round((lines & near_road).sum() * PIX * 1.1 / 1000, 1),
                   "km_elsewhere": round((lines & ~near_road).sum() * PIX * 1.1 / 1000, 1)}  # fmt: skip
            out.append(row)
            print(row, flush=True)
(HERE / "results_straight.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
